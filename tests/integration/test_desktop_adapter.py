"""DataLab Desktop adapter: SPEC and HDF5 imports, and plugin unloading."""

from __future__ import annotations

from contextlib import nullcontext
from importlib import resources
from pathlib import Path

import h5py
import numpy as np
import pytest
from datalab.control.proxy import LocalProxy
from datalab.env import execenv
from datalab.plugins import PluginCapability
from datalab.tests import datalab_test_app_context
from sigima.io.signal.base import SignalIORegistry
from sigima.objects import get_experimental_source
from sigimax.h5.mapping import registered_mappings
from support.spec_files import MORE_TEXT, write_spec

from datalab_synchrotron import PLUGIN_ID, formats
from datalab_synchrotron.adapters import desktop
from datalab_synchrotron.core import SpecFile
from datalab_synchrotron.mappings import packaged_mappings, unregister_mappings


def test_plugin_descriptor() -> None:
    """The entry point declares an application, I/O and processing plugin with its
    recipes."""
    assert desktop.SynchrotronPlugin.get_plugin_id() == PLUGIN_ID
    assert desktop.SynchrotronPlugin.PLUGIN_INFO.capabilities == frozenset(
        {
            PluginCapability.APPLICATION,
            PluginCapability.IO,
            PluginCapability.PROCESSING,
        }
    )
    assert [recipe.local_id for recipe in desktop.SynchrotronPlugin.get_recipes()] == [
        "xas-absorption",
        "xas-normalization",
    ]


def test_icons_and_welcome_tiles() -> None:
    """The welcome page shows the application, SPEC import and example tiles, with
    icons shipped with the package."""
    plugin_class = desktop.SynchrotronPlugin
    tiles = plugin_class.get_welcome_tiles()
    assert [(tile.id, tile.launcher) for tile in tiles] == [
        ("application", None),
        ("import-spec", "import_spec_scans"),
        ("cu-foil-example", "open_cu_foil_example"),
    ]
    assert plugin_class.PLUGIN_INFO.icon == desktop.PLUGIN_ICON
    for icon in {desktop.PLUGIN_ICON, *(tile.icon for tile in tiles)}:
        package, path = icon.split(":")
        assert resources.files(package).joinpath(path).is_file()


def _patch_parameters(
    monkeypatch: pytest.MonkeyPatch,
    scans: str,
    x: str,
    counters: list[str],
    mca: list[str] | None = None,
    mesh: bool = True,
) -> None:
    """Answer the SPEC import dialog with the given parameters."""
    original = desktop._import_parameters  # pylint: disable=protected-access

    def parameters(spec):
        param = original(spec)
        param.scans, param.x, param.counters = scans, x, counters
        param.mca, param.mesh = mca or [], mesh
        monkeypatch.setattr(param, "edit", lambda **_kwargs: True)
        return param

    monkeypatch.setattr(desktop, "_import_parameters", parameters)


def test_import_parameters(tmp_path: Path) -> None:
    """The dialog proposes the MCA devices of the file, and hides the MCA and mesh
    items when the file has neither MCA spectra nor mesh scans."""
    param = desktop._import_parameters(  # pylint: disable=protected-access
        SpecFile(write_spec(tmp_path / "more.spec", text=MORE_TEXT))
    )
    items = {item.get_name(): item for item in param.get_items()}
    mca, mesh = items["mca"], items["mesh"]
    assert [value for value, *_label in mca.get_prop("data", "choices")] == [
        "mca1",
        "mca2",
    ]
    assert not mca.get_prop_value("display", param, "hide")
    assert not mesh.get_prop_value("display", param, "hide")
    plain = desktop._import_parameters(  # pylint: disable=protected-access
        SpecFile(write_spec(tmp_path / "plain.spec", text=MORE_TEXT.split("#S 2")[0]))
    )
    for item in plain.get_items():
        if item.get_name() in ("mca", "mesh"):
            assert item.get_prop_value("display", plain, "hide")


def test_import_spec_scans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Selected scans are imported in one group each, with their origin."""
    filename = write_spec(tmp_path / "beamtime.dat")
    _patch_parameters(monkeypatch, "1", "Theta", ["Detector counts"])
    warnings: list[str] = []
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as main,
    ):
        plugin = desktop.SynchrotronPlugin()
        plugin.main, plugin.proxy = main, LocalProxy(main)
        monkeypatch.setattr(plugin, "show_warning", warnings.append)
        assert plugin.import_spec_scans(filename) == 2
        groups = main.signalpanel.objmodel.get_groups()
        assert [group.title for group in groups[-2:]] == [
            "Scan 1.1 - ascan  th 1 0.6 4 0.1",
            "Scan 1.2 - ascan  th 0 1 2 0.1",
        ]
        (signal,) = groups[-1].get_objects()
        assert get_experimental_source(signal)["entry"] == "1.2"
        assert not warnings


def test_skipped_scans_report(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Scans lacking the selected columns are reported in one line per reason."""
    filename = write_spec(tmp_path / "beamtime.dat")
    _patch_parameters(monkeypatch, "all", "Theta", ["Detector counts"])
    warnings: list[str] = []
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as main,
    ):
        plugin = desktop.SynchrotronPlugin()
        plugin.main, plugin.proxy = main, LocalProxy(main)
        monkeypatch.setattr(plugin, "show_warning", warnings.append)
        assert plugin.import_spec_scans(filename) == 2
    assert warnings == [
        "Selected data was not imported from 3 of 5 scans:\n"
        "No column Theta, Detector counts (3 scans: 2.1, 3.1, 4.1)"
    ]


def test_import_mca_and_mesh_images(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """MCA spectra and mesh scans are imported as images, in a group of the image
    panel named after the scan."""
    filename = write_spec(tmp_path / "more.spec", text=MORE_TEXT)
    _patch_parameters(monkeypatch, "2-3", "Energy", ["counts"], ["mca2"])
    warnings: list[str] = []
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as main,
    ):
        plugin = desktop.SynchrotronPlugin()
        plugin.main, plugin.proxy = main, LocalProxy(main)
        monkeypatch.setattr(plugin, "show_warning", warnings.append)
        assert plugin.import_spec_scans(filename) == 2
        image_groups = main.imagepanel.objmodel.get_groups()
        assert [group.title for group in image_groups[-2:]] == [
            "Scan 2.1 - ascan en 690 692 2 1",
            "Scan 3.1 - mesh  samx 0 2 2  samy 11 10 1  1",
        ]
        (mca,) = image_groups[-2].get_objects()
        assert mca.title == "mca2 (scan 2.1)" and mca.data.shape == (3, 4)
        (mesh,) = image_groups[-1].get_objects()
        assert mesh.title == "counts (scan 3.1)"
    assert warnings == [
        "Selected data was not imported from 1 of 2 scans:\nNo column counts (scan 2.1)"
    ]


class _CancellingProgress:
    """Progress dialog whose Cancel button is pressed at the n-th check."""

    def __init__(self, checks: int) -> None:
        self.checks = checks

    def setValue(self, _value: int) -> None:  # pylint: disable=invalid-name
        """Ignore progress."""

    def setLabelText(self, _text: str) -> None:  # pylint: disable=invalid-name
        """Ignore labels."""

    def wasCanceled(self) -> bool:  # pylint: disable=invalid-name
        """Return True from the n-th check on."""
        self.checks -= 1
        return self.checks <= 0


def test_cancel_spec_import(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Objects are added in batches, and the import stops when cancelled."""
    filename = write_spec(tmp_path / "beamtime.dat")
    _patch_parameters(monkeypatch, "4", "Energy", ["I0", "It"])
    monkeypatch.setattr(desktop, "ADD_BATCH_SIZE", 1)
    progress = _CancellingProgress(checks=3)
    monkeypatch.setattr(
        desktop, "create_progress_bar", lambda *_args, **_kw: nullcontext(progress)
    )
    infos: list[str] = []
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as main,
    ):
        plugin = desktop.SynchrotronPlugin()
        plugin.main, plugin.proxy = main, LocalProxy(main)
        monkeypatch.setattr(plugin, "show_info", infos.append)
        # Checks: before reading scan 4.1, before its 1st and 2nd batch of 1 signal
        assert plugin.import_spec_scans(filename) == 1
        assert len(main.signalpanel.objmodel.get_groups()[-1].get_objects()) == 1
    assert infos == ["Import cancelled: 1 object(s) imported."]


def test_not_a_spec_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Other files are refused before any dialog."""
    other = tmp_path / "table.dat"
    other.write_text("x,y\n1,2\n", encoding="utf-8")
    plugin = desktop.SynchrotronPlugin()
    errors: list[str] = []
    monkeypatch.setattr(plugin, "show_error", errors.append)
    assert plugin.import_spec_scans(str(other)) == 0
    assert errors == [f"'{other}' is not a SPEC file"]


def _write_scan_file(filename: Path) -> str:
    """Write a time scan laid out as beamline scan files: legacy NXdata counters
    without axes, Latin-1 and blank units, and a detector writing a spectrum per
    point."""
    with h5py.File(filename, "w") as h5file:
        entry = h5file.create_group("scan_00062")
        entry.attrs["NX_class"] = b"NXentry"
        scan = entry.create_group("scan_data")
        scan.attrs["NX_class"] = b"NXdata"
        scan["time_1"] = np.array([1.511, 2.126, 2.74])
        scan["time_1"].attrs["long_name"] = b"Time"
        scan["time_1"].attrs["units"] = b"s"
        scan["time_1"].attrs["axis"] = np.int32(0)
        for index, units in ((1, b" "), (2, b"\xb5m")):
            scan[f"data_{index}"] = np.arange(3.0) + index
            scan[f"data_{index}"].attrs["signal"] = np.int32(index)
            scan[f"data_{index}"].attrs["units"] = np.bytes_(units)
            scan[f"data_{index}"].attrs["long_name"] = f"counter{index}".encode()
        scan["data_3"] = np.arange(3 * 8, dtype=np.int32).reshape(3, 8)
        scan["data_3"].attrs["signal"] = np.int32(3)
    return str(filename)


def test_scan_counters_mapping(tmp_path: Path) -> None:
    """While the plugin is loaded, every scan counter is imported versus time."""
    filename = _write_scan_file(tmp_path / "scan.nxs")
    plugin = desktop.SynchrotronPlugin()
    plugin.register_hooks()
    try:
        with (
            execenv.context(unattended=True),
            datalab_test_app_context(console=False, exec_loop=False) as main,
        ):
            main.import_h5_file(filename, reset_all=True)
            sources = {
                id(obj): get_experimental_source(obj) or {}
                for obj in main.signalpanel.objmodel.get_all_objects()
            }
            mapped = {
                sources[id(obj)]["selection"]["signal"]: obj
                for obj in main.signalpanel.objmodel.get_all_objects()
                if sources[id(obj)].get("kind") == "hdf5"
            }
            assert set(mapped) == {"data_1", "data_2"}
            signal = mapped["data_2"]
            assert signal.title.startswith("data_2")
            np.testing.assert_array_equal(signal.x, [1.511, 2.126, 2.74])
            assert (signal.xlabel, signal.xunit) == ("Time", "s")
            assert (signal.ylabel, signal.yunit) == ("counter2", "\u00b5m")
            assert mapped["data_1"].yunit == ""
            source = get_experimental_source(signal)
            assert source["details"] == {"mapping": "Scan counters"}
            # The detector writing a spectrum per point is an image versus time
            (detector,) = [
                obj
                for obj in main.imagepanel.objmodel.get_all_objects()
                if (get_experimental_source(obj) or {}).get("kind") == "hdf5"
            ]
            assert detector.data.shape == (3, 8)
            np.testing.assert_array_equal(detector.ycoords, [1.511, 2.126, 2.74])
            assert (detector.ylabel, detector.yunit) == ("Time", "s")
    finally:
        plugin.unregister_hooks()
    names = {mapping.name for mapping in registered_mappings()}
    assert not names & {mapping.name for mapping in packaged_mappings()}
    assert not [fmt for fmt in SignalIORegistry.get_formats() if _is_plugin(fmt)]
    # Loading the plugin again registers its formats again (kept for other tests)
    plugin.register_hooks()
    try:
        plugin_formats = [
            fmt for fmt in SignalIORegistry.get_formats() if _is_plugin(fmt)
        ]
        assert len(plugin_formats) == 2
    finally:
        unregister_mappings()


def _is_plugin(fmt) -> bool:
    """Return True if a format handler is defined by the plugin."""
    return fmt.__class__.__module__ == formats.__name__


def _write_step_scan(filename: Path) -> str:
    """Write a step scan laid out as recent SOLEIL scan files: legacy axis and
    primary attributes, time stamps with axis 0, counters and detectors of several
    ranks all designated as signals."""
    with h5py.File(filename, "w") as h5file:
        entry = h5file.create_group("scan_0494")
        entry.attrs["NX_class"] = b"NXentry"
        scan = entry.create_group("scan_data")
        scan.attrs["NX_class"] = b"NXdata"
        scan["actuator_1_1"] = np.array([-8.0, -7.8, -7.6])
        scan["actuator_1_1"].attrs.update(axis=np.int32(1), primary=np.int32(1))
        scan["actuator_1_1"].attrs["long_name"] = b"i06-c-c08/ex/dif-mt_rx.2/position"
        scan["actuator_1_1"].attrs["units"] = b"\xb0"
        scan["sensors_rel_timestamps"] = np.array([0.0, 1.1, 2.2])
        scan["sensors_rel_timestamps"].attrs["axis"] = np.int32(0)
        scan["data_01"] = np.array([5.0, 9.0, 4.0])
        scan["data_02"] = np.arange(3 * 16, dtype=np.int32).reshape(3, 16)
        scan["data_03"] = np.zeros((3, 4, 5), dtype=np.int32)
        for name in ("data_01", "data_02", "data_03"):
            scan[name].attrs["signal"] = np.int32(1)
    return str(filename)


def test_step_scan(tmp_path: Path) -> None:
    """Step scans are imported by DataLab's HDF5 browser without data mapping:
    counters versus the scanned motor, and detectors with the motor along Y."""
    filename = _write_step_scan(tmp_path / "step.nxs")
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as main,
    ):
        main.import_h5_file(filename, reset_all=True)
        signals = [
            obj
            for obj in main.signalpanel.objmodel.get_all_objects()
            if (get_experimental_source(obj) or {}).get("kind") == "nexus"
        ]
        (counter,) = signals
        np.testing.assert_array_equal(counter.x, [-8.0, -7.8, -7.6])
        assert counter.xunit == "\u00b0"
        (detector,) = [
            obj
            for obj in main.imagepanel.objmodel.get_all_objects()
            if (get_experimental_source(obj) or {}).get("kind") == "nexus"
        ]
        assert detector.data.shape == (3, 16)
        assert detector.ylabel == "i06-c-c08/ex/dif-mt_rx.2/position"
