"""Conversion of SPEC scans and XDI files to signals recording their origin."""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Sequence
from pathlib import PurePath

import numpy as np
from sigima.objects import (
    SignalObj,
    create_signal,
    make_experimental_source,
    set_experimental_source,
)

from .spec import SpecFile, SpecScan
from .xdi import XdiFile

__all__ = [
    "ScanGroup",
    "ScanImport",
    "mca_signals",
    "plan_scan_import",
    "scan_signals",
    "select_scans",
]


def _source(spec: SpecFile, scan: SpecScan, selection: dict, conversions) -> dict:
    """Return the experimental source of a signal read from a scan."""
    details = {"command": scan.info.command, "date": scan.info.date}
    if scan.motors:
        details["motors"] = dict(scan.motors)
    if scan.problems:
        details["skipped_lines"] = len(scan.problems)
    return make_experimental_source(
        "spec",
        spec.path,
        entry=scan.info.key,
        selection=selection,
        conversions=conversions or None,
        details=details,
    )


def scan_signals(
    spec: SpecFile, scan: SpecScan, x: str, counters: Sequence[str]
) -> list[SignalObj]:
    """Return one signal per counter of a scan, versus the X column.

    Points keep their acquisition order, even if X is not monotonic.

    Raises:
        ValueError: if a column does not exist
    """
    xdata = scan.column(x)
    signals = []
    for counter in counters:
        signal = create_signal(
            f"{counter} (scan {scan.info.key})",
            xdata.copy(),
            scan.column(counter).copy(),
            labels=(x, counter),
        )
        selection = {"x": x, "y": counter}
        set_experimental_source(signal, _source(spec, scan, selection, None))
        signals.append(signal)
    return signals


def mca_signals(
    spec: SpecFile, scan: SpecScan, indices: Sequence[int] | None = None
) -> list[SignalObj]:
    """Return MCA spectra of a scan, on calibrated X if the scan declares it.

    The X axis is the channel number, or ``a + b * channel + c * channel**2``
    with the ``#@CALIB`` coefficients of the scan.
    """
    signals = []
    for index in range(len(scan.mca)) if indices is None else indices:
        channels = scan.mca_channels_axis(index)
        conversions = []
        xlabel = "Channel"
        if scan.mca_calibration is not None:
            a, b, c = scan.mca_calibration
            x = a + b * channels + c * channels**2
            conversions.append(f"channels -> a + b*ch + c*ch^2 with {a}, {b}, {c}")
            xlabel = "Calibrated channel"
        else:
            x = channels
        signal = create_signal(
            f"MCA {index} (scan {scan.info.key})",
            np.asarray(x, dtype=float),
            scan.mca[index].astype(float),
            labels=(xlabel, "Counts"),
        )
        set_experimental_source(
            signal, _source(spec, scan, {"mca": index}, conversions)
        )
        signals.append(signal)
    return signals


@dataclasses.dataclass(frozen=True)
class ScanGroup:
    """Signals read from one scan, imported in a group of their own."""

    title: str
    signals: tuple[SignalObj, ...]


@dataclasses.dataclass(frozen=True)
class ScanImport:
    """Signals to import, one group per scan, and the scans that were skipped."""

    groups: tuple[ScanGroup, ...]
    skipped: tuple[str, ...]


def select_scans(spec: SpecFile, text: str) -> list[str]:
    """Return the keys of the scans selected by a text.

    Args:
        spec: SPEC file
        text: ``all``, or comma-separated scan numbers (all their occurrences),
         ``<number>.<occurrence>`` keys and ``<first>-<last>`` number ranges,
         e.g. ``1, 3.2, 10-12``

    Raises:
        ValueError: if the text is invalid or selects no scan
    """
    if text.strip().lower() in ("", "all"):
        return [info.key for info in spec.scans]
    selected: set[str] = set()
    for token in (part.strip() for part in text.split(",")):
        match = re.fullmatch(r"(\d+)(?:\.(\d+)|-(\d+))?", token)
        if match is None:
            raise ValueError(f"Invalid scan selection '{token}' (e.g. 1, 3.2, 10-12)")
        first = int(match.group(1))
        last = int(match.group(3)) if match.group(3) else first
        keys = [
            info.key
            for info in spec.scans
            if first <= info.number <= last
            and (match.group(2) is None or info.occurrence == int(match.group(2)))
        ]
        if not keys:
            raise ValueError(f"No scan matches '{token}'")
        selected.update(keys)
    return [info.key for info in spec.scans if info.key in selected]


def plan_scan_import(
    spec: SpecFile,
    keys: Sequence[str],
    x: str,
    counters: Sequence[str],
    include_mca: bool = False,
) -> ScanImport:
    """Return the signals to import from scans, one group per scan.

    Scans of the same structure are never merged: each scan is its own group.
    Scans lacking a selected column are skipped, with the reason.

    Raises:
        ValueError: if nothing is selected for import
    """
    counters = [counter for counter in counters if counter != x]
    if not counters and not include_mca:
        raise ValueError("Select at least one counter or the MCA spectra")
    groups: list[ScanGroup] = []
    skipped: list[str] = []
    for key in keys:
        scan = spec.read_scan(key)
        signals: list[SignalObj] = []
        missing = [name for name in (x, *counters) if name not in scan.info.labels]
        if counters and missing:
            skipped.append(f"scan {key}: no column {', '.join(missing)}")
        elif counters and scan.data.shape[0] == 0:
            skipped.append(f"scan {key}: no data")
        elif counters:
            signals.extend(scan_signals(spec, scan, x, counters))
        if include_mca:
            signals.extend(mca_signals(spec, scan))
        if signals:
            title = f"Scan {key} - {scan.info.command}".strip(" -")
            groups.append(ScanGroup(title, tuple(signals)))
    if not groups:
        raise ValueError("No signal to import: " + "; ".join(skipped))
    return ScanImport(tuple(groups), tuple(skipped))


#: XDI header fields recorded in the origin of the signals
_XDI_DETAILS = {
    "element": "Element.symbol",
    "edge": "Element.edge",
    "facility": "Facility.name",
    "beamline": "Beamline.name",
    "monochromator": "Mono.name",
    "sample": "Sample.name",
    "start_time": "Scan.start_time",
}


def xdi_signals(xdi: XdiFile, columns: Sequence[str] | None = None) -> list[SignalObj]:
    """Return one signal per column of an XDI file, versus the first column.

    Args:
        xdi: XDI file
        columns: column names (default: all columns but the first one)

    Raises:
        KeyError: if a column does not exist
    """
    xcol = xdi.columns[0]
    if columns is None:
        columns = [column.name for column in xdi.columns[1:]]
    details = {key: xdi.field(name) for key, name in _XDI_DETAILS.items()}
    details["element"], details["edge"] = xdi.element, xdi.edge
    details = {key: value for key, value in details.items() if value}
    if xdi.skipped_lines:
        details["skipped_lines"] = len(xdi.skipped_lines)
    signals = []
    for name in columns:
        column = xdi.columns[xdi.column_index(name)]
        signal = create_signal(
            f"{column.name} ({PurePath(xdi.path).name})",
            xdi.data[:, 0].copy(),
            xdi.column(name).copy(),
            units=(xcol.units, column.units),
            labels=(xcol.name, column.name),
        )
        source = make_experimental_source(
            "xdi",
            xdi.path,
            selection={"x": xcol.name, "y": column.name},
            details=details or None,
        )
        set_experimental_source(signal, source)
        signals.append(signal)
    return signals
