"""DataLab Desktop plugin adapter."""

from __future__ import annotations

import collections
import os.path as osp

import guidata.dataset as gds
from datalab.config import _
from datalab.plugins import PluginBase, PluginCapability, PluginInfo
from datalab.plugins.examples import PluginExample, PluginExampleData
from datalab.plugins.recipes import RecipeOutcome
from datalab.utils.qthelpers import create_progress_bar
from qtpy import QtWidgets as QW
from qtpy.compat import getopenfilename

from .. import PLUGIN_DESCRIPTION, PLUGIN_ID, PLUGIN_NAME, __version__
from ..core import (
    SkippedScan,
    SpecFile,
    check_scan_selection,
    import_scan,
    is_spec_file,
    select_scans,
    summarize_skipped,
)
from ..formats import unregister_formats
from ..mappings import register_mappings, unregister_mappings
from ..workflow import (
    ABSORPTION_RECIPE,
    CU_FOIL_EXAMPLE,
    NORMALIZATION_RECIPE,
    materialize_example,
)
from ..workflow import EXAMPLES as WORKFLOW_EXAMPLES
from ..workflow import RECIPES as WORKFLOW_RECIPES

#: Number of signals added to the workspace at once by the SPEC import
ADD_BATCH_SIZE = 200


def _import_parameters(spec: SpecFile) -> gds.DataSet:
    """Return the import parameters of a SPEC file, with its columns as choices."""
    labels: list[str] = []
    for info in spec.scans:
        labels.extend(label for label in info.labels if label not in labels)
    # Default columns: those of the most frequent scan structure
    structures = collections.Counter(info.labels for info in spec.scans if info.labels)
    first = structures.most_common(1)[0][0] if structures else ("",)
    choices = [(label, label) for label in labels] or [("", "-")]
    numbers = sorted({info.number for info in spec.scans})
    scan_help = (
        f"{len(spec.scans)} scans, numbered {numbers[0]} to {numbers[-1]}: "
        "'all', or e.g. '1, 3.2, 10-12' (3.2: second scan numbered 3)"
    )

    class SpecImportParameters(gds.DataSet):
        """Import SPEC scans"""

        scans = gds.StringItem(_("Scans"), default="all", help=scan_help)
        x = gds.ChoiceItem(_("X column"), choices, default=first[0])
        counters = gds.MultipleChoiceItem(
            _("Counters"), choices, default=[first[-1]]
        ).vertical(3)
        mca = gds.BoolItem(_("MCA spectra"), default=False)

    return SpecImportParameters(title=osp.basename(spec.path))


class SynchrotronPlugin(PluginBase):
    """Expose beamline data readers to DataLab Desktop."""

    PLUGIN_INFO = PluginInfo(
        id=PLUGIN_ID,
        name=PLUGIN_NAME,
        version=__version__,
        description=PLUGIN_DESCRIPTION,
        capabilities=(PluginCapability.IO, PluginCapability.PROCESSING),
        documentation_url="https://github.com/DataLab-Platform/datalab-synchrotron",
    )
    RECIPES = WORKFLOW_RECIPES
    EXAMPLES = WORKFLOW_EXAMPLES

    @classmethod
    def materialize_example(cls, example_id: str) -> PluginExampleData | None:
        """Read an example from the plugin's data files."""
        cls.get_example(example_id)
        return materialize_example(example_id)

    def open_cu_foil_example(self) -> PluginExample | None:
        """Open the copper foil example and select its counters."""
        return self.launch_example(CU_FOIL_EXAMPLE.id)

    def register_hooks(self) -> None:
        """Apply the shipped HDF5 data mappings."""
        register_mappings()

    def unregister_hooks(self) -> None:
        """Remove the file formats and data mappings added by the plugin."""
        unregister_formats()
        unregister_mappings()

    def import_spec_scans(self, filename: str | None = None) -> int:
        """Import scans of a SPEC file, one group per scan.

        Args:
            filename: SPEC file (default: ask the user)

        Returns:
            Number of imported signals
        """
        if filename is None:
            filename, _filter = getopenfilename(
                self.main,
                _("Import SPEC scans"),
                "",
                _("SPEC files (*.spec *.dat);;All files (*)"),
            )
            if not filename:
                return 0
        if not is_spec_file(filename):
            self.show_error(_("'%s' is not a SPEC file") % filename)
            return 0
        try:
            spec = SpecFile(filename)
            param = _import_parameters(spec)
            if not param.edit(parent=self.main):
                return 0
            keys = select_scans(spec, param.scans)
            counters = list(param.counters)
            check_scan_selection(param.x, counters, param.mca)
        except ValueError as exc:
            self.show_error(str(exc))
            return 0
        count, skipped, cancelled = self._add_scans(
            spec, keys, param.x, counters, param.mca
        )
        report = summarize_skipped(skipped)
        if cancelled:
            self.show_info(
                _("Import cancelled: %d signal(s) imported.") % count
                + "".join("\n" + line for line in report)
            )
        elif count == 0:
            self.show_error(_("No signal was imported:") + "\n" + "\n".join(report))
        elif skipped:
            self.show_warning(
                _("Selected columns were not imported from %d of %d scans:")
                % (len(skipped), len(keys))
                + "\n"
                + "\n".join(report)
            )
        return count

    def _add_scans(
        self,
        spec: SpecFile,
        keys: list[str],
        x: str,
        counters: list[str],
        include_mca: bool,
    ) -> tuple[int, list[SkippedScan], bool]:
        """Read and add scans one at a time, in a group each, until cancelled.

        Returns:
            Number of added signals, skipped scans, and True if cancelled
        """
        count, skipped = 0, []
        title = _("Importing SPEC scans")
        progress_bar = create_progress_bar(self.main, title, max_=len(keys))
        with progress_bar as progress, self.proxy.context_no_refresh():
            for index, key in enumerate(keys):
                progress.setValue(index)
                progress.setLabelText(
                    _("Reading scan %s (%d of %d)") % (key, index + 1, len(keys))
                )
                QW.QApplication.processEvents()
                if progress.wasCanceled():
                    return count, skipped, True
                group, reason = import_scan(spec, key, x, counters, include_mca)
                if reason is not None:
                    skipped.append(reason)
                if group is None:
                    continue
                group_id = self.proxy.add_group(group.title, panel="signal")
                signals = group.signals
                for start in range(0, len(signals), ADD_BATCH_SIZE):
                    progress.setLabelText(
                        _("Adding signals of scan %s (%d of %d)")
                        % (key, start, len(signals))
                    )
                    QW.QApplication.processEvents()
                    if progress.wasCanceled():
                        return count, skipped, True
                    batch = signals[start : start + ADD_BATCH_SIZE]
                    self.signalpanel.add_objects(
                        batch, group_id=group_id, set_current=False
                    )
                    count += len(batch)
            progress.setValue(len(keys))
        return count, skipped, False

    def run_absorption(self) -> RecipeOutcome | None:
        """Compute the absorption from the selected monitor and detector."""
        return self.start_recipe(ABSORPTION_RECIPE.recipe_id)

    def run_normalization(self) -> RecipeOutcome | None:
        """Normalize the selected absorption spectra."""
        return self.start_recipe(NORMALIZATION_RECIPE.recipe_id)

    def create_actions(self) -> None:
        """Create the import and analysis actions of the signal panel."""
        handler = self.signalpanel.acthandler
        with handler.new_menu(PLUGIN_NAME.replace("&", "&&")):
            self.import_spec_action = handler.new_action(
                _("Import SPEC scans..."),
                triggered=lambda: self.import_spec_scans(),
                tip=_(
                    "Import columns and MCA spectra of SPEC scans, one group per scan"
                ),
                select_condition="always",
            )
            self.cu_foil_example_action = handler.new_action(
                _("Open copper foil example"),
                triggered=self.open_cu_foil_example,
                tip=_("Open the counters of a copper foil measured in transmission"),
                select_condition="always",
            )
            self.absorption_action = handler.new_action(
                _("Absorption from counters..."),
                triggered=self.run_absorption,
                tip=_("Compute mu(E) from monitor and detector counts"),
                select_condition="at_least_one",
                separator=True,
            )
            self.normalization_action = handler.new_action(
                _("Edge normalization..."),
                triggered=self.run_normalization,
                tip=_("Find E0 and normalize absorption spectra to a unit edge step"),
                select_condition="at_least_one",
            )
