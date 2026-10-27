"""SPEC data files: index of scans, and reading of their columns and MCA spectra.

A SPEC file is a text file holding scans: a ``#S <number> <command>`` line,
header lines (``#D`` date, ``#P`` motor positions, ``#N`` column count, ``#L``
column labels, ``#@CALIB`` MCA calibration...), then one data line per point
and, for MCA scans, ``@A`` spectrum lines (continued with ``\\``). File header
lines (``#F``, ``#E``, ``#O`` motor names...) apply to the scans that follow.

Several MCA devices may write spectra at each point: their lines start with
``@A1``, ``@A2``..., and their ``#@CALIB``/``#@CHANN`` lines may end with the
device name (``mca1``...). Spectra are grouped by device, named ``mca`` for
``@A`` lines and ``mca<n>`` for ``@A<n>`` lines.

The same scan number may appear several times in a file: scans are identified
by ``"<number>.<occurrence>"`` (e.g. ``"12.1"``, ``"12.2"``). Opening a file
only indexes its scans; the data of a scan is read when the scan is read.
"""

from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path

import numpy as np

__all__ = ["SpecFile", "SpecScan", "SpecScanInfo", "is_spec_file", "mca_device"]

#: Number of bytes inspected to recognize a SPEC file
SNIFF_SIZE = 65536

_SPLIT_LABELS = re.compile(r"\s{2,}")
_MCA_LINE = re.compile(r"@A(\d*)(?=\s|\\|$)")
_POSITIONS = re.compile(r"#P\d+(?:\s+(.*))?$")
_MOTORS = re.compile(r"#O\d+(?:\s+(.*))?$")
#: Values written for missing data by some acquisition programs (e.g. Bluesky)
_MISSING_VALUES = ("none", "null")


def is_spec_file(path: str | Path) -> bool:
    """Return True if a file looks like a SPEC file, whatever its extension.

    The file must start with a ``#`` header line and contain a ``#S`` scan line
    in its first bytes.
    """
    try:
        with open(path, "rb") as file:
            head = file.read(SNIFF_SIZE)
    except OSError:
        return False
    text = head.decode("latin-1")
    stripped = text.lstrip()
    return stripped.startswith("#") and re.search(r"^#S \d+", text, re.M) is not None


def mca_device(suffix: str) -> str:
    """Return the name of the MCA device of ``@A<suffix>`` lines.

    Args:
        suffix: digits following ``@A`` (empty for ``@A`` lines)
    """
    return f"mca{suffix}"


@dataclasses.dataclass(frozen=True)
class SpecScanInfo:
    """Scan of a SPEC file, as indexed when the file is opened.

    Args:
        number: scan number
        occurrence: occurrence of the scan number in the file (from 1)
        command: scan command (e.g. ``ascan th 0 1 10 0.1``)
        date: ``#D`` date of the scan
        labels: column labels, one per column (``column<n>`` if not given,
         ``<label>_<n>`` for the n-th repetition of a label)
        point_count: number of data lines
        mca_count: number of MCA spectra, all devices together
        mca_devices: MCA devices, in order of appearance
    """

    number: int
    occurrence: int
    command: str
    date: str
    labels: tuple[str, ...]
    point_count: int
    mca_count: int
    mca_devices: tuple[str, ...] = ()

    @property
    def key(self) -> str:
        """Scan identifier: ``"<number>.<occurrence>"``."""
        return f"{self.number}.{self.occurrence}"


@dataclasses.dataclass(frozen=True)
class SpecScan:
    """Scan read from a SPEC file.

    Args:
        info: scan index entry
        data: data points, one column per label (incomplete lines are dropped,
         missing values are NaN)
        motors: motor positions at the start of the scan (``#O``/``#P``)
        header: scan header lines
        mca: MCA spectra of each device, in acquisition order
        mca_calibration: ``#@CALIB`` coefficients ``(a, b, c)`` by device, the
         empty name standing for the calibration of all devices
        mca_channels: ``#@CHANN`` values ``(count, first, last, reduction)`` by
         device, the empty name standing for all devices
        problems: lines that could not be read as data, with their reason
        ignored: number of ignored ``@`` lines that are not MCA spectra, by prefix
    """

    info: SpecScanInfo
    data: np.ndarray
    motors: dict[str, float]
    header: tuple[str, ...]
    mca: dict[str, tuple[np.ndarray, ...]]
    mca_calibration: dict[str, tuple[float, float, float]]
    mca_channels: dict[str, tuple[int, int, int, int]]
    problems: tuple[str, ...]
    ignored: dict[str, int] = dataclasses.field(default_factory=dict)

    def column(self, label: str) -> np.ndarray:
        """Return the values of a column.

        Raises:
            ValueError: if the scan has no column with this label
        """
        try:
            return self.data[:, self.info.labels.index(label)]
        except ValueError as exc:
            raise ValueError(
                f"Scan {self.info.key} has no column '{label}' "
                f"(available: {', '.join(self.info.labels)})"
            ) from exc

    def calibration(self, device: str) -> tuple[float, float, float] | None:
        """Return the ``#@CALIB`` coefficients ``(a, b, c)`` of an MCA device."""
        return self.mca_calibration.get(device, self.mca_calibration.get(""))

    def channel_numbers(self, device: str) -> np.ndarray:
        """Return the channel numbers of the spectra of an MCA device.

        Raises:
            ValueError: if the device has no spectrum, or spectra of several sizes
        """
        sizes = {spectrum.size for spectrum in self.mca.get(device, ())}
        if len(sizes) != 1:
            raise ValueError(
                f"Scan {self.info.key}: MCA device '{device}' has "
                + ("no spectrum" if not sizes else "spectra of several sizes")
            )
        size = sizes.pop()
        channels = self.mca_channels.get(device, self.mca_channels.get(""))
        if channels is None:
            return np.arange(size, dtype=float)
        _count, first, _last, reduction = channels
        return first + reduction * np.arange(size, dtype=float)


@dataclasses.dataclass(frozen=True)
class _Section:
    """Lines of a scan and of the file header that applies to it."""

    start: int
    stop: int
    file_header: tuple[str, ...]


def _numbers(text: str) -> list[float]:
    """Return the numbers of a text line."""
    return [float(value) for value in text.split()]


def _values(text: str) -> list[float]:
    """Return the values of a data line, missing values being NaN.

    Raises:
        ValueError: if a word is neither a number nor a missing value
    """
    values = []
    for word in text.split():
        try:
            values.append(float(word))
        except ValueError:
            if word.lower() not in _MISSING_VALUES:
                raise
            values.append(math.nan)
    return values


def _unique(labels: list[str]) -> tuple[str, ...]:
    """Return labels with a ``_<n>`` suffix added to repeated ones, as spec2nexus
    does, so that each column has its own label."""
    result: list[str] = []
    for label in labels:
        name, index = label, 0
        while name in result:
            index += 1
            name = f"{label}_{index}"
        result.append(name)
    return tuple(result)


def _labels(text: str, count: int | None, width: int) -> tuple[str, ...]:
    """Return one label per column.

    Labels are separated by two spaces or more, or by single spaces if this gives
    the column count: the ``#N`` count, else the number of values of the first
    data line (some programs write a wrong ``#N``). Columns without label are
    named ``column<n>`` (the split giving the most labels is then used), and
    repeated labels get a ``_<n>`` suffix.

    Args:
        text: ``#L`` line content
        count: ``#N`` column count, if given
        width: number of values of the first data line (0: no data)
    """
    spaced = _SPLIT_LABELS.split(text.strip()) if text.strip() else []
    words = text.split()
    for expected in (count, width):
        if expected:
            for labels in (spaced, words):
                if len(labels) == expected:
                    return _unique(labels)
    expected = width or count or len(spaced)
    # More labels than the double-space split, without exceeding the columns
    base = words if len(spaced) < len(words) <= expected else spaced
    labels = base + [f"column{index + 1}" for index in range(len(base), expected)]
    return _unique(labels[:expected])


def _device_values(text: str) -> tuple[list[float], str]:
    """Return the numbers of an MCA header line, and its trailing device name."""
    words = text.split()
    if words and not re.fullmatch(r"[-+0-9.eE]+", words[-1]):
        return _numbers(" ".join(words[:-1])), words[-1]
    return _numbers(text), ""


class SpecFile:
    """SPEC file, indexed when opened.

    Args:
        path: file path

    Raises:
        ValueError: if the file cannot be read or holds no scan
    """

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        try:
            self._lines = Path(path).read_text(encoding="latin-1").splitlines()
        except OSError as exc:
            raise ValueError(f"Cannot read '{path}': {exc.strerror}") from exc
        self._sections: dict[str, _Section] = {}
        self.scans: tuple[SpecScanInfo, ...] = self._index()
        if not self.scans:
            raise ValueError(f"'{path}' holds no SPEC scan")

    def _index(self) -> tuple[SpecScanInfo, ...]:
        """Index the scans of the file."""
        occurrences: dict[int, int] = {}
        infos: list[SpecScanInfo] = []
        file_header: list[str] = []
        scan: dict | None = None

        def close(stop: int) -> None:
            if scan is None:
                return
            number = scan["number"]
            occurrences[number] = occurrences.get(number, 0) + 1
            info = SpecScanInfo(
                number=number,
                occurrence=occurrences[number],
                command=scan["command"],
                date=scan["date"],
                labels=_labels(scan["labels"], scan["count"], scan["width"]),
                point_count=scan["points"],
                mca_count=sum(scan["mca"].values()),
                mca_devices=tuple(scan["mca"]),
            )
            self._sections[info.key] = _Section(scan["start"], stop, scan["header"])
            infos.append(info)

        continued = False
        for index, line in enumerate(self._lines):
            stripped = line.strip()
            if continued:
                continued = stripped.endswith("\\")
                continue
            if line.startswith("#S "):
                close(index)
                fields = line[3:].strip().split(maxsplit=1)
                try:
                    number = int(fields[0])
                except (IndexError, ValueError):
                    scan = None
                    continue
                scan = {
                    "number": number,
                    "command": fields[1] if len(fields) > 1 else "",
                    "date": "",
                    "labels": "",
                    "count": None,
                    "width": 0,
                    "points": 0,
                    "mca": {},
                    "start": index,
                    "header": tuple(file_header),
                }
            elif line.startswith(("#F ", "#E ")):
                close(index)
                scan = None
                file_header = [line]
            elif scan is None:
                if line.startswith("#"):
                    file_header.append(line)
            elif line.startswith("#L "):
                scan["labels"] = line[3:]
            elif line.startswith("#N "):
                try:
                    scan["count"] = int(line[3:].split()[0])
                except (IndexError, ValueError):
                    pass
            elif line.startswith("#D "):
                scan["date"] = line[3:].strip()
            elif stripped.startswith("@"):
                match = _MCA_LINE.match(stripped)
                if match is not None:
                    device = mca_device(match.group(1))
                    scan["mca"][device] = scan["mca"].get(device, 0) + 1
                continued = stripped.endswith("\\")
            elif stripped and not stripped.startswith("#"):
                if not scan["points"]:
                    scan["width"] = len(stripped.split())
                scan["points"] += 1
        close(len(self._lines))
        return tuple(infos)

    def get_info(self, key: str) -> SpecScanInfo:
        """Return the index entry of a scan.

        Raises:
            ValueError: if the file has no such scan
        """
        for info in self.scans:
            if info.key == key:
                return info
        raise ValueError(f"'{self.path}' has no scan {key}")

    def read_scan(self, key: str) -> SpecScan:
        """Read the data of a scan.

        Args:
            key: scan identifier, ``"<number>.<occurrence>"``

        Raises:
            ValueError: if the file has no such scan
        """
        info = self.get_info(key)
        section = self._sections[key]
        lines = self._lines[section.start + 1 : section.stop]
        header: list[str] = [self._lines[section.start]]
        rows: list[list[float]] = []
        problems: list[str] = []
        mca: dict[str, list[np.ndarray]] = {}
        calibration: dict[str, tuple[float, float, float]] = {}
        channels: dict[str, tuple[int, int, int, int]] = {}
        ignored: dict[str, int] = {}
        positions: list[float] = []
        index = 0
        ncols = len(info.labels)
        while index < len(lines):
            line = lines[index]
            stripped = line.strip()
            index += 1
            if not stripped:
                continue
            if stripped.startswith("#"):
                header.append(line)
                lowered = stripped.lower()
                if lowered.startswith("#@calib"):
                    values, device = _device_values(stripped[7:])
                    calibration[device] = tuple((values + [0.0, 0.0, 0.0])[:3])
                elif lowered.startswith("#@chann"):
                    values, device = _device_values(stripped[7:])
                    if len(values) == 4:
                        channels[device] = tuple(int(value) for value in values)
                else:
                    match = _POSITIONS.match(stripped)
                    if match is not None and match.group(1):
                        positions.extend(_numbers(match.group(1)))
                continue
            if stripped.startswith("@"):
                text = stripped
                while text.endswith("\\") and index < len(lines):
                    text = text[:-1] + " " + lines[index].strip()
                    index += 1
                text = text.rstrip("\\")
                match = _MCA_LINE.match(text)
                if match is None:
                    prefix = text.split(maxsplit=1)[0]
                    ignored[prefix] = ignored.get(prefix, 0) + 1
                    continue
                device = mca_device(match.group(1))
                mca.setdefault(device, []).append(
                    np.array(_numbers(text[match.end() :]))
                )
                continue
            try:
                values = _values(stripped)
            except ValueError:
                problems.append(f"line '{stripped[:40]}': not numeric")
                continue
            if ncols and len(values) != ncols:
                problems.append(
                    f"line '{stripped[:40]}': {len(values)} values for {ncols} columns"
                )
                continue
            rows.append(values)
        data = np.array(rows, dtype=float).reshape(len(rows), ncols)
        motor_names = []
        for line in section.file_header:
            match = _MOTORS.match(line.rstrip())
            if match is not None and match.group(1):
                motor_names.extend(_SPLIT_LABELS.split(match.group(1).strip()))
        motors = dict(zip(motor_names, positions))
        return SpecScan(
            info=info,
            data=data,
            motors=motors,
            header=tuple(header),
            mca={device: tuple(spectra) for device, spectra in mca.items()},
            mca_calibration=calibration,
            mca_channels=channels,
            problems=tuple(problems),
            ignored=ignored,
        )
