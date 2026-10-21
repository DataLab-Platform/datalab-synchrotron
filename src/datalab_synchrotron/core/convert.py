"""Conversion of SPEC scans to signals recording their origin."""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from sigima.objects import (
    SignalObj,
    create_signal,
    make_experimental_source,
    set_experimental_source,
)

from .spec import SpecFile, SpecScan

__all__ = ["mca_signals", "scan_signals"]


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
