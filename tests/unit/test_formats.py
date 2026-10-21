"""SPEC file format registered in Sigima by the plugin."""

from __future__ import annotations

from pathlib import Path

import sigima.io
from sigima.io.signal.base import SignalIORegistry
from support.spec_files import write_spec

from datalab_synchrotron import formats


def _spec_formats() -> list:
    return [
        fmt
        for fmt in SignalIORegistry.get_formats()
        if isinstance(fmt, formats.SpecSignalFormat)
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


def test_unregister_formats() -> None:
    """Unloading the plugin removes its formats from Sigima."""
    assert len(_spec_formats()) == 1
    formats.unregister_formats()
    try:
        assert not _spec_formats()
    finally:
        SignalIORegistry.get_formats().append(formats.SpecSignalFormat())
