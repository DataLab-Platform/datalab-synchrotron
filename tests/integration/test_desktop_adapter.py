"""DataLab Desktop adapter: SPEC and HDF5 imports, and plugin unloading."""

from __future__ import annotations

from pathlib import Path

import h5py
import numpy as np
import pytest
from datalab.control.proxy import LocalProxy
from datalab.env import execenv
from datalab.plugins import PluginCapability
from datalab.tests import datalab_test_app_context
from sigima.objects import get_experimental_source
from sigimax.h5.mapping import registered_mappings
from support.spec_files import write_spec

from datalab_synchrotron import PLUGIN_ID
from datalab_synchrotron.adapters import desktop
from datalab_synchrotron.mappings import packaged_mappings


def test_plugin_descriptor() -> None:
    """The entry point declares an I/O and processing plugin with its recipes."""
    assert desktop.SynchrotronPlugin.get_plugin_id() == PLUGIN_ID
    assert desktop.SynchrotronPlugin.PLUGIN_INFO.capabilities == frozenset(
        {PluginCapability.IO, PluginCapability.PROCESSING}
    )
    assert [recipe.local_id for recipe in desktop.SynchrotronPlugin.get_recipes()] == [
        "xas-absorption",
        "xas-normalization",
    ]


def test_import_spec_scans(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Selected scans are imported in one group each, with their origin."""
    filename = write_spec(tmp_path / "beamtime.dat")
    original = desktop._import_parameters  # pylint: disable=protected-access

    def parameters(spec):
        param = original(spec)
        param.scans, param.x, param.counters = "1", "Theta", ["Detector counts"]
        monkeypatch.setattr(param, "edit", lambda **_kwargs: True)
        return param

    monkeypatch.setattr(desktop, "_import_parameters", parameters)
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
    without axes, Latin-1 and blank units."""
    with h5py.File(filename, "w") as h5file:
        entry = h5file.create_group("scan_00062")
        entry.attrs["NX_class"] = b"NXentry"
        scan = entry.create_group("scan_data")
        scan.attrs["NX_class"] = b"NXdata"
        scan["time_1"] = np.array([1.511, 2.126, 2.74])
        scan["time_1"].attrs["long_name"] = b"Time"
        scan["time_1"].attrs["units"] = b"s"
        for index, units in ((1, b" "), (2, b"\xb5m")):
            scan[f"data_{index}"] = np.arange(3.0) + index
            scan[f"data_{index}"].attrs["signal"] = np.int32(index)
            scan[f"data_{index}"].attrs["units"] = np.bytes_(units)
            scan[f"data_{index}"].attrs["long_name"] = f"counter{index}".encode()
    return str(filename)


def test_scan_counters_mapping(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """While the plugin is loaded, every scan counter is imported versus time."""
    filename = _write_scan_file(tmp_path / "scan.nxs")
    # Sigima formats cannot be registered again: they stay for the other tests
    monkeypatch.setattr(desktop, "unregister_formats", lambda: None)
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
    finally:
        plugin.unregister_hooks()
    names = {mapping.name for mapping in registered_mappings()}
    assert not names & {mapping.name for mapping in packaged_mappings()}
