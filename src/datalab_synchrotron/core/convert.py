"""Conversion of SPEC scans and XDI files to signals and images recording their
origin.

The header information of the files (SPEC scan headers, XDI fields and comments)
is kept as object metadata, while the ``experimental_source`` metadata entry
identifies where the data comes from.
"""

from __future__ import annotations

import dataclasses
import re
from collections.abc import Sequence
from pathlib import PurePath

import numpy as np
from sigima.objects import (
    ImageObj,
    SignalObj,
    create_image,
    create_signal,
    make_experimental_source,
    set_experimental_source,
)

from .spec import SpecFile, SpecScan, SpecScanInfo
from .xdi import XdiColumn, XdiFile

__all__ = [
    "HC_EV_ANGSTROM",
    "MESH_POSITION_TOLERANCE",
    "MeshShape",
    "ScanGroup",
    "ScanImport",
    "SkippedScan",
    "check_scan_selection",
    "import_scan",
    "mca_images",
    "mesh_images",
    "mesh_point_indices",
    "mesh_shape",
    "plan_scan_import",
    "scan_metadata",
    "scan_signals",
    "select_scans",
    "summarize_skipped",
    "xdi_energy",
    "xdi_metadata",
    "xdi_signals",
]

#: Planck constant times the speed of light, in eV.Å (exact SI values)
HC_EV_ANGSTROM = 12398.419843320026

#: Relative tolerance on the steps of evenly spaced image coordinates
_UNIFORM_RTOL = 1e-9

#: Largest median deviation from the grid, in steps of each motor, of the motor
#: positions of the points following data lines that could not be read in a mesh
#: scan (well below half a step, so that positions off the grid do not fit
#: several numbers of missing points, which leaves the placement unsure)
MESH_POSITION_TOLERANCE = 0.35

#: Largest number of points a data line that could not be read may have held
#: (e.g. two lines written without a newline)
_POINTS_PER_UNREAD_LINE = 2

#: Why the counters of a mesh scan are imported as signals instead of images
_MESH_UNSURE = "points cannot be placed after lines that could not be read"


def _source(
    spec: SpecFile, scan: SpecScan, selection: dict, conversions: Sequence[str]
) -> dict:
    """Return the experimental source of an object read from a scan."""
    details = {"command": scan.info.command, "date": scan.info.date}
    if scan.motors:
        details["motors"] = dict(scan.motors)
    if scan.problems:
        details["skipped_lines"] = len(scan.problems)
    if scan.ignored:
        details["ignored_lines"] = dict(scan.ignored)
    return make_experimental_source(
        "spec",
        spec.path,
        entry=scan.info.key,
        selection=selection,
        conversions=list(conversions) or None,
        details=details,
    )


def _value_and_note(text: str) -> tuple[float, str]:
    """Return the number and the parenthesized note of a header line, e.g.
    ``60  (Clock)``."""
    match = re.match(r"(\S+)\s*(?:\((.*)\))?", text)
    if match is None:
        raise ValueError(f"No value in '{text}'")
    return float(match.group(1)), (match.group(2) or "").strip()


def scan_metadata(scan: SpecScan) -> dict[str, object]:
    """Return the scan header information kept as object metadata.

    Keys: ``SPEC count time`` and ``SPEC count time unit`` (``#T``), ``SPEC monitor
    count`` and ``SPEC monitor counter`` (``#M``), ``SPEC hkl`` (``#Q``), ``SPEC
    geometry G<n>`` (``#G<n>``), ``SPEC comments`` (``#C`` lines, one per line),
    and ``SPEC MD <name>`` (``#MD <name> = <value>`` lines written by Bluesky).
    Header lines that cannot be read are left out.
    """
    metadata: dict[str, object] = {}
    comments: list[str] = []
    for line in scan.header[1:]:
        tag, _sep, text = line.strip().partition(" ")
        text = text.strip()
        try:
            if tag in ("#T", "#M") and text:
                value, note = _value_and_note(text)
                name, note_name = (
                    ("count time", "count time unit")
                    if tag == "#T"
                    else ("monitor count", "monitor counter")
                )
                metadata[f"SPEC {name}"] = value
                if note:
                    metadata[f"SPEC {note_name}"] = note
            elif tag == "#Q" and text:
                metadata["SPEC hkl"] = np.array([float(word) for word in text.split()])
            elif re.fullmatch(r"#G\d+", tag) and text:
                metadata[f"SPEC geometry {tag[1:]}"] = np.array(
                    [float(word) for word in text.split()]
                )
            elif tag == "#C" and text:
                comments.append(text)
            elif tag == "#MD" and "=" in text:
                name, value = text.split("=", 1)
                if name.strip():
                    metadata[f"SPEC MD {name.strip()}"] = value.strip()
        except ValueError:
            continue
    if comments:
        metadata["SPEC comments"] = "\n".join(comments)
    return metadata


def _finish(obj: SignalObj | ImageObj, source: dict, metadata: dict) -> None:
    """Record the header metadata and the origin of an object."""
    obj.metadata.update(metadata)
    set_experimental_source(obj, source)


def scan_signals(
    spec: SpecFile,
    scan: SpecScan,
    x: str,
    counters: Sequence[str],
    conversions: Sequence[str] = (),
) -> list[SignalObj]:
    """Return one signal per counter of a scan, versus the X column.

    Points keep their acquisition order, even if X is not monotonic.

    Args:
        spec: SPEC file
        scan: scan read from the file
        x: X column
        counters: counter columns
        conversions: notes recorded in the origin of the signals

    Raises:
        ValueError: if a column does not exist
    """
    xdata = scan.column(x)
    metadata = scan_metadata(scan)
    signals = []
    for counter in counters:
        signal = create_signal(
            f"{counter} (scan {scan.info.key})",
            xdata.copy(),
            scan.column(counter).copy(),
            labels=(x, counter),
        )
        source = _source(spec, scan, {"x": x, "y": counter}, conversions)
        _finish(signal, source, metadata)
        signals.append(signal)
    return signals


def _is_strictly_monotonic(values: np.ndarray) -> bool:
    """Return True if values are finite and strictly increasing or decreasing."""
    if not np.all(np.isfinite(values)):
        return False
    steps = np.diff(values)
    return bool(np.all(steps > 0) or np.all(steps < 0))


def _image(
    title: str,
    data: np.ndarray,
    coords: tuple[np.ndarray, np.ndarray],
    labels: tuple[str, str, str],
    conversions: list[str],
) -> ImageObj:
    """Return an image with increasing coordinates, uniform if evenly spaced.

    Args:
        title: image title
        data: image values, one row per Y coordinate
        coords: strictly monotonic X and Y coordinates
        labels: X, Y and Z labels
        conversions: conversions applied to the values, completed with the axes
         reversed to increasing order
    """
    xvals, yvals = (np.asarray(values, dtype=float) for values in coords)
    for axis, (values, label) in enumerate(((yvals, labels[1]), (xvals, labels[0]))):
        if values.size > 1 and values[-1] < values[0]:
            data = np.flip(data, axis=axis)
            conversions.append(f"axis '{label}': reversed to increasing order")
    xvals, yvals = np.sort(xvals), np.sort(yvals)
    image = create_image(title, np.ascontiguousarray(data), labels=labels)
    steps = [np.diff(values) for values in (xvals, yvals)]
    if all(
        step.size < 2 or np.allclose(step, step[0], rtol=_UNIFORM_RTOL, atol=0.0)
        for step in steps
    ):
        dx, dy = (float(step[0]) if step.size else 1.0 for step in steps)
        image.set_uniform_coords(dx, dy, float(xvals[0]), float(yvals[0]))
    else:
        image.set_coords(xvals, yvals)
    return image


def mca_images(
    spec: SpecFile, scan: SpecScan, x: str = "", devices: Sequence[str] | None = None
) -> list[ImageObj]:
    """Return the MCA spectra of a scan as one image per device.

    Each row holds the spectrum of a point. The X axis is the channel number, or
    ``a + b * channel + c * channel**2`` with the ``#@CALIB`` coefficients of the
    device, if they give strictly monotonic values. The Y axis is the X column
    of the scan, if it holds one strictly monotonic value per spectrum, else the
    point number.

    Args:
        spec: SPEC file
        scan: scan read from the file
        x: X column of the scan (empty: point numbers)
        devices: MCA devices (default: all devices of the scan)

    Raises:
        ValueError: if a device has no spectrum, or spectra of several sizes
    """
    metadata = scan_metadata(scan)
    images = []
    for device in scan.mca if devices is None else devices:
        spectra = scan.mca.get(device, ())
        channels = scan.channel_numbers(device)
        conversions = [f"spectra -> image rows ({len(spectra)} spectra)"]
        xvals, xlabel = channels, "Channel"
        calibration = scan.calibration(device)
        if calibration is not None:
            a, b, c = calibration
            calibrated = a + b * channels + c * channels**2
            if _is_strictly_monotonic(calibrated):
                xvals, xlabel = calibrated, "Calibrated channel"
                conversions.append(f"channels -> a + b*ch + c*ch^2 with {a}, {b}, {c}")
            else:
                conversions.append("calibration not monotonic: channel numbers kept")
        yvals, ylabel = np.arange(len(spectra), dtype=float), "Point"
        if x in scan.info.labels:
            column = scan.column(x)
            if column.size == len(spectra) and _is_strictly_monotonic(column):
                yvals, ylabel = column, x
        image = _image(
            f"{device} (scan {scan.info.key})",
            np.vstack(spectra),
            (xvals, yvals),
            (xlabel, ylabel, "Counts"),
            conversions,
        )
        selection = {"mca": device, "y": ylabel if ylabel == x else "point"}
        _finish(image, _source(spec, scan, selection, conversions), metadata)
        images.append(image)
    return images


@dataclasses.dataclass(frozen=True)
class MeshShape:
    """Grid of a mesh scan, as given by its command.

    Args:
        columns: number of points along the first motor (fastest)
        rows: number of points along the second motor
        steps: steps of the first and second motors
        start: start positions of the first and second motors, relative to their
         positions before the scan if ``relative`` is True
        relative: True for ``dmesh`` commands (start positions relative to the
         positions of the motors before the scan)
    """

    columns: int
    rows: int
    steps: tuple[float, float]
    start: tuple[float, float] = (0.0, 0.0)
    relative: bool = False


def mesh_shape(info: SpecScanInfo) -> MeshShape | None:
    """Return the grid of a mesh scan, or None if the scan is not a mesh scan.

    Mesh scans are written by ``mesh`` and ``dmesh`` commands:
    ``mesh <motor1> <start1> <end1> <intervals1> <motor2> <start2> <end2>
    <intervals2> <time>``, the first motor moving fastest; their first two
    columns hold the positions of the two motors.
    """
    words = info.command.split()
    if len(words) < 9 or words[0] not in ("mesh", "dmesh") or len(info.labels) < 2:
        return None
    try:
        start1, end1, count1 = float(words[2]), float(words[3]), int(words[4])
        start2, end2, count2 = float(words[6]), float(words[7]), int(words[8])
    except ValueError:
        return None
    if count1 < 0 or count2 < 0:
        return None
    steps = (
        (end1 - start1) / count1 if count1 else 1.0,
        (end2 - start2) / count2 if count2 else 1.0,
    )
    if 0.0 in steps:
        return None
    return MeshShape(
        count1 + 1, count2 + 1, steps, (start1, start2), words[0] == "dmesh"
    )


def _grid_cells(indices: np.ndarray, columns: int) -> np.ndarray:
    """Return the column and row of grid indices, one point per row."""
    return np.column_stack((indices % columns, indices // columns)).astype(float)


def mesh_point_indices(scan: SpecScan, shape: MeshShape) -> np.ndarray | None:
    """Return the grid index of each point of a mesh scan, or None if unsure.

    Points are placed in acquisition order, the first motor moving fastest.
    Where data lines could not be read before the last point, each line may have
    held 0 to 2 points: the number of missing points is the only one for which
    the motor positions of the points that follow, up to the next lines that
    could not be read, fit the grid within :data:`MESH_POSITION_TOLERANCE` steps
    on each motor (median deviation). The grid is the one of the points already
    placed (median of their deviations), or starts at the start of the command
    for lines before the first point. Lines before the first point of a
    ``dmesh`` scan, whose absolute start is unknown, leave the placement unsure.

    Args:
        scan: mesh scan, whose first two columns hold the positions of the motors
        shape: grid of the scan

    Returns:
        Grid index of each point (row-major, ``row * columns + column``), indices
        beyond the grid standing for points beyond the mesh, or None if the
        motor positions do not tell how many points are missing
    """
    npoints = scan.data.shape[0]
    lines: dict[int, int] = {}
    for row in scan.problem_rows:
        if row < npoints:
            lines[row] = lines.get(row, 0) + 1
    if not lines:
        return np.arange(npoints)
    if 0 in lines and shape.relative:
        return None
    steps = np.asarray(shape.steps, dtype=float)
    positions = scan.data[:, :2] / steps
    starts = sorted(set(lines) | {0})
    indices = np.empty(npoints, dtype=int)
    for first, stop in zip(starts, starts[1:] + [npoints]):
        offsets = np.arange(stop - first)
        if first not in lines:
            indices[first:stop] = offsets
            continue
        if first == 0:
            origin, base = np.asarray(shape.start, dtype=float) / steps, 0
        else:
            placed = _grid_cells(indices[:first], shape.columns)
            origin = np.median(positions[:first] - placed, axis=0)
            base = int(indices[first - 1]) + 1
        segment = positions[first:stop] - origin
        fits = [
            missing
            for missing in range(_POINTS_PER_UNREAD_LINE * lines[first] + 1)
            if np.median(
                np.abs(segment - _grid_cells(base + missing + offsets, shape.columns)),
                axis=0,
            ).max()
            <= MESH_POSITION_TOLERANCE
        ]
        if len(fits) != 1:
            return None
        indices[first:stop] = base + fits[0] + offsets
    return indices


def mesh_images(
    spec: SpecFile, scan: SpecScan, counters: Sequence[str]
) -> list[ImageObj]:
    """Return one image per counter of a mesh scan.

    Coordinates follow the steps of the command from the motor positions of the
    first point. Points are placed as told by :func:`mesh_point_indices`;
    points missing in an interrupted scan, or lost in lines that could not be
    read, are NaN.

    Raises:
        ValueError: if the scan is not a mesh scan, has no data, has no column
         of a counter, or if its points cannot be placed after lines that could
         not be read
    """
    shape = mesh_shape(scan.info)
    if shape is None:
        raise ValueError(f"Scan {scan.info.key} is not a mesh scan")
    size = shape.rows * shape.columns
    npoints = scan.data.shape[0]
    if npoints == 0:
        raise ValueError(f"Scan {scan.info.key} has no data")
    indices = mesh_point_indices(scan, shape)
    if indices is None:
        raise ValueError(f"Scan {scan.info.key}: {_MESH_UNSURE}")
    inside = indices < size
    placed = int(np.count_nonzero(inside))
    row0, column0 = divmod(int(indices[0]), shape.columns)
    xlabel, ylabel = scan.info.labels[:2]
    xvals = scan.data[0, 0] + shape.steps[0] * (np.arange(shape.columns) - column0)
    yvals = scan.data[0, 1] + shape.steps[1] * (np.arange(shape.rows) - row0)
    notes = [
        f"points -> {shape.rows} x {shape.columns} image ('{xlabel}' along rows), "
        "coordinates from the first point and the command steps"
    ]
    unread = sum(row < npoints for row in scan.problem_rows)
    if unread:
        notes.append(
            f"{unread} lines that could not be read: points placed from the motor "
            "positions"
        )
    if placed < size:
        notes.append(f"incomplete mesh: {size - placed} points set to NaN")
    if placed < npoints:
        notes.append(f"{npoints - placed} points beyond the mesh ignored")
    metadata = scan_metadata(scan)
    images = []
    for counter in counters:
        grid = np.full(size, np.nan)
        grid[indices[inside]] = scan.column(counter)[inside]
        conversions = list(notes)
        image = _image(
            f"{counter} (scan {scan.info.key})",
            grid.reshape(shape.rows, shape.columns),
            (xvals, yvals),
            (xlabel, ylabel, counter),
            conversions,
        )
        selection = {"x": xlabel, "y": ylabel, "z": counter}
        _finish(image, _source(spec, scan, selection, conversions), metadata)
        images.append(image)
    return images


@dataclasses.dataclass(frozen=True)
class ScanGroup:
    """Signals and images read from one scan, imported in groups of their own."""

    title: str
    signals: tuple[SignalObj, ...]
    images: tuple[ImageObj, ...] = ()


@dataclasses.dataclass(frozen=True)
class SkippedScan:
    """Scan left out of an import, with the reason."""

    key: str
    reason: str


@dataclasses.dataclass(frozen=True)
class ScanImport:
    """Objects to import, one group per scan, and the scans that were skipped."""

    groups: tuple[ScanGroup, ...]
    skipped: tuple[SkippedScan, ...]

    @property
    def object_count(self) -> int:
        """Return the number of signals and images to import."""
        return sum(len(group.signals) + len(group.images) for group in self.groups)


def _scan_list(keys: Sequence[str], max_keys: int) -> str:
    """Return a short list of scan keys: first ones, then the last one."""
    if len(keys) == 1:
        return f"scan {keys[0]}"
    if len(keys) <= max_keys:
        return f"{len(keys)} scans: {', '.join(keys)}"
    shown = ", ".join(keys[: max_keys - 1])
    return f"{len(keys)} scans: {shown}, ..., {keys[-1]}"


def summarize_skipped(
    skipped: Sequence[SkippedScan], max_reasons: int = 5, max_keys: int = 6
) -> list[str]:
    """Return one line per reason why scans were skipped, with a short list of them.

    Args:
        skipped: skipped scans
        max_reasons: number of reasons shown, the others being counted together
        max_keys: number of scan keys shown per reason
    """
    by_reason: dict[str, list[str]] = {}
    for item in skipped:
        by_reason.setdefault(item.reason, []).append(item.key)
    reasons = sorted(by_reason.items(), key=lambda item: -len(item[1]))
    lines = [
        f"{reason[:1].upper()}{reason[1:]} ({_scan_list(keys, max_keys)})"
        for reason, keys in reasons[:max_reasons]
    ]
    others = reasons[max_reasons:]
    if others:
        count = sum(len(keys) for _reason, keys in others)
        lines.append(f"Other reasons ({count} scans)")
    return lines


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


def check_scan_selection(
    x: str, counters: Sequence[str], mca_devices: Sequence[str] = ()
) -> None:
    """Raise if neither a counter other than X nor an MCA device is selected."""
    if not [counter for counter in counters if counter != x] and not mca_devices:
        raise ValueError("Select at least one counter or MCA device")


def _scan_objects(
    spec: SpecFile,
    scan: SpecScan,
    x: str,
    counters: Sequence[str],
    mca_devices: Sequence[str],
    mesh_as_images: bool,
) -> tuple[list[SignalObj], list[ImageObj], SkippedScan | None]:
    """Return the signals and images of a scan, and why its columns were left out,
    if so.

    Counters of a mesh scan whose points cannot be placed (see
    :func:`mesh_point_indices`) are imported as signals versus X, the reason
    being reported as for columns left out."""
    key = scan.info.key
    signals: list[SignalObj] = []
    images: list[ImageObj] = []
    skipped = None
    shape = mesh_shape(scan.info) if mesh_as_images else None
    unsure = bool(
        shape is not None
        and counters
        and scan.data.shape[0] > 0
        and mesh_point_indices(scan, shape) is None
    )
    mesh = shape is not None and not unsure
    needed = counters if mesh else (x, *counters)
    missing = [name for name in needed if name not in scan.info.labels]
    if counters and missing:
        skipped = SkippedScan(key, f"no column {', '.join(missing)}")
    elif counters and scan.data.shape[0] == 0:
        skipped = SkippedScan(key, "no data")
    elif counters and mesh:
        images.extend(mesh_images(spec, scan, counters))
    elif counters and unsure:
        reason = f"mesh imported as signals: {_MESH_UNSURE}"
        signals.extend(scan_signals(spec, scan, x, counters, [reason]))
        skipped = SkippedScan(key, reason)
    elif counters:
        signals.extend(scan_signals(spec, scan, x, counters))
    devices = [device for device in mca_devices if device in scan.mca]
    if devices:
        images.extend(mca_images(spec, scan, x, devices))
    return signals, images, skipped


def import_scan(
    spec: SpecFile,
    key: str,
    x: str,
    counters: Sequence[str],
    mca_devices: Sequence[str] = (),
    mesh_as_images: bool = True,
) -> tuple[ScanGroup | None, SkippedScan | None]:
    """Return the signals and images of one scan, and why its columns were left
    out, if so.

    Counters are imported as signals versus X, or as images for mesh scans if
    ``mesh_as_images`` is True (as signals, with the reason, if the points of
    the mesh cannot be placed, see :func:`mesh_point_indices`). MCA spectra of
    the selected devices are imported as images, even if columns are missing. A
    scan that cannot be read is skipped, with the error.
    """
    counters = [counter for counter in counters if counter != x]
    try:
        scan = spec.read_scan(key)
        signals, images, skipped = _scan_objects(
            spec, scan, x, counters, mca_devices, mesh_as_images
        )
    except Exception as exc:  # pylint: disable=broad-except
        # Data of third-party files: report the scan and read the other ones
        return None, SkippedScan(key, f"unreadable: {exc}")
    if not signals and not images:
        return None, skipped
    title = f"Scan {key} - {scan.info.command}".strip(" -")
    return ScanGroup(title, tuple(signals), tuple(images)), skipped


def plan_scan_import(
    spec: SpecFile,
    keys: Sequence[str],
    x: str,
    counters: Sequence[str],
    mca_devices: Sequence[str] = (),
    mesh_as_images: bool = True,
) -> ScanImport:
    """Return the objects to import from scans, one group per scan.

    Scans of the same structure are never merged: each scan is its own group.
    Scans lacking a selected column, or that cannot be read, are skipped, with
    the reason.

    Raises:
        ValueError: if nothing is selected for import
    """
    check_scan_selection(x, counters, mca_devices)
    groups: list[ScanGroup] = []
    skipped: list[SkippedScan] = []
    for key in keys:
        group, reason = import_scan(spec, key, x, counters, mca_devices, mesh_as_images)
        if group is not None:
            groups.append(group)
        if reason is not None:
            skipped.append(reason)
    if not groups:
        raise ValueError("Nothing to import:\n" + "\n".join(summarize_skipped(skipped)))
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

#: Units of monochromator angles, with their conversion to radians
_ANGLE_UNITS = {
    "": np.deg2rad,
    "deg": np.deg2rad,
    "degree": np.deg2rad,
    "degrees": np.deg2rad,
    "rad": np.asarray,
    "radian": np.asarray,
    "radians": np.asarray,
}


def xdi_energy(xdi: XdiFile) -> tuple[np.ndarray, XdiColumn, list[str]]:
    """Return the abscissa of an XDI file, its column, and the conversions applied.

    Monochromator angles (``angle`` column, in degrees unless given in radians)
    are converted to energies in eV with the Bragg law, ``E = hc / (2 d sin)``,
    if the file gives the ``Mono.d_spacing`` lattice spacing in Å. Other
    abscissas are returned as written.
    """
    column = xdi.columns[0]
    values = xdi.data[:, 0].copy()
    to_radians = _ANGLE_UNITS.get(column.units.lower())
    if column.name.lower() != "angle" or to_radians is None:
        return values, column, []
    try:
        spacing = float(xdi.field("Mono.d_spacing").split()[0])
    except (IndexError, ValueError):
        return values, column, []
    sines = np.sin(to_radians(values))
    if spacing <= 0 or not np.all(sines > 0):
        return values, column, []
    energies = HC_EV_ANGSTROM / (2 * spacing * sines)
    conversion = (
        f"angle -> energy: E = hc / (2 d sin(angle)), "
        f"d = {spacing} Å, hc = {HC_EV_ANGSTROM} eV.Å"
    )
    return energies, XdiColumn("energy", "eV"), [conversion]


def xdi_metadata(xdi: XdiFile) -> dict[str, str]:
    """Return the header of an XDI file kept as object metadata.

    Keys: every header field (``Namespace.tag``, as written), ``XDI version``
    (with the application versions), ``XDI comments`` (one comment per line) and
    ``XDI problems`` (ignored header lines, one per line), if any.
    """
    metadata = dict(xdi.fields)
    metadata["XDI version"] = f"XDI/{xdi.version} {xdi.applications}".strip()
    if xdi.comments:
        metadata["XDI comments"] = "\n".join(xdi.comments)
    if xdi.problems:
        metadata["XDI problems"] = "\n".join(xdi.problems)
    return metadata


def _outer_blocks(xdi: XdiFile) -> list[tuple[float | None, slice]]:
    """Return the outer value and rows of each block of an XDI file (one block
    without outer value for one-dimensional data)."""
    if not xdi.outer:
        return [(None, slice(None))]
    stops = [first for _value, first in xdi.outer[1:]] + [xdi.data.shape[0]]
    return [
        (value, slice(first, stop))
        for (value, first), stop in zip(xdi.outer, stops)
        if stop > first
    ]


def xdi_signals(xdi: XdiFile, columns: Sequence[str] | None = None) -> list[SignalObj]:
    """Return one signal per column of an XDI file, versus the first column.

    Monochromator angles are converted to energies (see :func:`xdi_energy`). For
    two-dimensional data, each column gives one signal per block of the outer
    scan, its outer value being recorded in the title, the metadata (``XDI outer
    value``) and the origin.

    Args:
        xdi: XDI file
        columns: column names (default: all columns but the first one)

    Raises:
        KeyError: if a column does not exist
    """
    xvalues, xcol, conversions = xdi_energy(xdi)
    if columns is None:
        columns = [column.name for column in xdi.columns[1:]]
    details = {key: xdi.field(name) for key, name in _XDI_DETAILS.items()}
    details["element"], details["edge"] = xdi.element, xdi.edge
    details = {key: value for key, value in details.items() if value}
    metadata = xdi_metadata(xdi)
    outer_name = xdi.field("Outer.name") or "outer"
    filename = PurePath(xdi.path).name
    signals = []
    for name in columns:
        column = xdi.columns[xdi.column_index(name)]
        for outer, rows in _outer_blocks(xdi):
            title = f"{column.name} ({filename})"
            selection = {"x": xdi.columns[0].name, "y": column.name}
            block_metadata = dict(metadata)
            if outer is not None:
                title = f"{column.name} ({filename}, {outer_name} = {outer:g})"
                if not np.isnan(outer):
                    selection["outer"] = outer
                    block_metadata["XDI outer value"] = outer
            signal = create_signal(
                title,
                xvalues[rows].copy(),
                xdi.column(name)[rows].copy(),
                units=(xcol.units, column.units),
                labels=(xcol.name, column.name),
            )
            source = make_experimental_source(
                "xdi",
                xdi.path,
                selection=selection,
                conversions=conversions or None,
                details=details or None,
            )
            _finish(signal, source, block_metadata)
            signals.append(signal)
    return signals
