"""Sigima file formats, registered when this module is imported.

**File > Open** reads a ``.spec`` file as one signal per scan: the last column
(usually the detector counts) versus the first one (usually the scanned motor).
Scans that cannot be read are left out. Other columns, MCA spectra and mesh
scans are imported with the plugin's import action. It reads an ``.xdi`` file as
one signal per column versus the energy.
"""

from __future__ import annotations

from sigima.io.base import FormatInfo
from sigima.io.signal.base import SignalFormatBase, SignalIORegistry
from sigima.objects import SignalObj

from .core import SpecFile, read_xdi, scan_signals, xdi_signals

__all__ = [
    "SpecSignalFormat",
    "XdiSignalFormat",
    "register_formats",
    "unregister_formats",
]


class SpecSignalFormat(SignalFormatBase):
    """SPEC data files"""

    FORMAT_INFO = FormatInfo(
        name="SPEC files",
        extensions="*.spec",
        readable=True,
        writeable=False,
    )

    def read(self, filename: str, worker=None) -> list[SignalObj]:
        """Read the last column versus the first one, for each scan.

        Raises:
            ValueError: if no scan could be read
        """
        spec = SpecFile(filename)
        signals: list[SignalObj] = []
        errors: list[str] = []
        for info in spec.scans:
            if len(info.labels) < 2 or info.point_count == 0:
                continue
            try:
                scan = spec.read_scan(info.key)
                signals.extend(
                    scan_signals(spec, scan, info.labels[0], info.labels[-1:])
                )
            except Exception as exc:  # pylint: disable=broad-except
                # Data of third-party files: read the other scans
                errors.append(f"scan {info.key}: {exc}")
        if not signals:
            reason = f" ({errors[0]})" if errors else ""
            raise ValueError(f"'{filename}' holds no readable scan{reason}")
        return signals


class XdiSignalFormat(SignalFormatBase):
    """XDI (XAS Data Interchange) files"""

    FORMAT_INFO = FormatInfo(
        name="XDI files",
        extensions="*.xdi",
        readable=True,
        writeable=False,
    )

    def read(self, filename: str, worker=None) -> list[SignalObj]:
        """Read every column versus the first one (energy)."""
        return xdi_signals(read_xdi(filename))


#: Format classes of this module
FORMAT_CLASSES = (SpecSignalFormat, XdiSignalFormat)


def register_formats() -> None:
    """Register this module's formats in Sigima, if they were unregistered."""
    for format_class in FORMAT_CLASSES:
        SignalIORegistry.register_format(format_class)


def unregister_formats() -> None:
    """Remove this module's formats from Sigima (when the plugin is unloaded).

    Formats defined by earlier imports of this module (plugin reloads) are removed
    too.
    """
    classes = {
        fmt.__class__
        for fmt in SignalIORegistry.get_formats()
        if fmt.__class__.__module__ == __name__
    }
    for format_class in classes:
        SignalIORegistry.unregister_format(format_class)
