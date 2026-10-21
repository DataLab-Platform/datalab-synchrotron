"""DataLab Desktop plugin adapter."""

from __future__ import annotations

import os.path as osp

import guidata.dataset as gds
from datalab.config import _
from datalab.plugins import PluginBase, PluginCapability, PluginInfo
from qtpy.compat import getopenfilename

from .. import PLUGIN_DESCRIPTION, PLUGIN_ID, PLUGIN_NAME, __version__
from ..core import SpecFile, is_spec_file, plan_scan_import, select_scans
from ..formats import unregister_formats
from ..mappings import register_mappings, unregister_mappings


def _import_parameters(spec: SpecFile) -> gds.DataSet:
    """Return the import parameters of a SPEC file, with its columns as choices."""
    labels: list[str] = []
    for info in spec.scans:
        labels.extend(label for label in info.labels if label not in labels)
    first = next((info.labels for info in spec.scans if info.labels), ("",))
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
        capabilities=(PluginCapability.IO,),
        documentation_url="https://github.com/DataLab-Platform/datalab-synchrotron",
    )

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
            plan = plan_scan_import(
                spec,
                select_scans(spec, param.scans),
                param.x,
                list(param.counters),
                param.mca,
            )
        except ValueError as exc:
            self.show_error(str(exc))
            return 0
        count = 0
        for group in plan.groups:
            group_id = self.proxy.add_group(group.title, panel="signal")
            for signal in group.signals:
                self.proxy.add_object(signal, group_id=group_id, set_current=False)
                count += 1
        if plan.skipped:
            self.show_warning(
                _("Some scans were not imported:") + "\n" + "\n".join(plan.skipped)
            )
        return count

    def create_actions(self) -> None:
        """Create the import action of the signal panel."""
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
