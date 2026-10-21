"""SPEC and XDI file formats registered in Sigima by the plugin."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import sigima.io
from sigima.io.signal.base import SignalIORegistry
from sigima.objects import get_experimental_source
from support.spec_files import write_spec
from support.xas_corpus import spectrum

from datalab_synchrotron import formats


def _spec_formats() -> list:
    return [
        fmt
        for fmt in SignalIORegistry.get_formats()
        if isinstance(fmt, (formats.SpecSignalFormat, formats.XdiSignalFormat))
    ]


def test_open_spec_file(tmp_path: Path) -> None:
    """File > Open reads the last column versus the first one of each scan."""
    signals = sigima.io.read_signals(write_spec(tmp_path / "scans.spec"))
    assert [signal.title for signal in signals] == [
        "Detector counts (scan 1.1)",
        "Detector counts (scan 1.2)",
        "It (scan 2.1)",
        "It (scan 4.1)",
    ]


def test_open_xdi_file() -> None:
    """File > Open reads every column versus the energy, with units and origin."""
    item = spectrum("cu_foil")
    signals = sigima.io.read_signals(str(item.path))
    assert [signal.title for signal in signals] == [
        f"{name} (cu_metal_rt.xdi)" for name in ("i0", "itrans", "mutrans")
    ]
    assert (signals[0].xlabel, signals[0].xunit) == ("energy", "eV")
    np.testing.assert_array_equal(signals[2].y, item.columns()["mutrans"])
    source = get_experimental_source(signals[0])
    assert source["kind"] == "xdi"
    assert source["details"]["element"] == "Cu"
    assert source["details"]["beamline"] == "APS 13ID"


def test_unregister_formats() -> None:
    """Unloading the plugin removes its formats from Sigima."""
    assert len(_spec_formats()) == 2
    formats.unregister_formats()
    try:
        assert not _spec_formats()
    finally:
        registered = SignalIORegistry.get_formats()
        registered.extend((formats.SpecSignalFormat(), formats.XdiSignalFormat()))
