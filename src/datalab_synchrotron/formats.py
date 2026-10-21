"""Sigima file formats, registered when this module is imported.

**File > Open** reads a ``.spec`` file as one signal per scan: the last column
(usually the detector counts) versus the first one (usually the scanned motor).
Other columns and MCA spectra are imported with the plugin's import action.
"""

from __future__ import annotations

from sigima.io.base import FormatInfo
from sigima.io.signal.base import SignalFormatBase, SignalIORegistry
from sigima.objects import SignalObj

from .core import SpecFile, scan_signals

__all__ = ["SpecSignalFormat", "unregister_formats"]


class SpecSignalFormat(SignalFormatBase):
    """SPEC data files"""

    FORMAT_INFO = FormatInfo(
        name="SPEC files",
        extensions="*.spec",
        readable=True,
        writeable=False,
    )

    def read(self, filename: str, worker=None) -> list[SignalObj]:
        """Read the last column versus the first one, for each scan."""
        spec = SpecFile(filename)
        signals: list[SignalObj] = []
        for info in spec.scans:
            if len(info.labels) < 2 or info.point_count == 0:
                continue
            scan = spec.read_scan(info.key)
            signals.extend(scan_signals(spec, scan, info.labels[0], info.labels[-1:]))
        if not signals:
            raise ValueError(f"'{filename}' holds no scan with data columns")
        return signals


def unregister_formats() -> None:
    """Remove this module's formats from Sigima (when the plugin is unloaded)."""
    # Sigima registers one instance per format class, without removal API
    instances = SignalIORegistry._io_format_instances  # pylint: disable=W0212
    instances[:] = [fmt for fmt in instances if type(fmt).__module__ != __name__]
