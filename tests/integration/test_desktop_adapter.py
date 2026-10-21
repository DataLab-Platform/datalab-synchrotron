"""DataLab Desktop adapter: SPEC import into the workspace and plugin unloading."""

from __future__ import annotations

from pathlib import Path

import pytest
from datalab.control.proxy import LocalProxy
from datalab.env import execenv
from datalab.plugins import PluginCapability
from datalab.tests import datalab_test_app_context
from sigima.objects import get_experimental_source
from support.spec_files import write_spec

from datalab_synchrotron import PLUGIN_ID
from datalab_synchrotron.adapters import desktop


def test_plugin_descriptor() -> None:
    """The entry point declares an I/O plugin."""
    assert desktop.SynchrotronPlugin.get_plugin_id() == PLUGIN_ID
    assert desktop.SynchrotronPlugin.PLUGIN_INFO.capabilities == frozenset(
        {PluginCapability.IO}
    )


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
