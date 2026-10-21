"""SPEC data files: index of scans, and reading of their columns and MCA spectra.

A SPEC file is a text file holding scans: a ``#S <number> <command>`` line,
header lines (``#D`` date, ``#P`` motor positions, ``#N`` column count, ``#L``
column labels, ``#@CALIB`` MCA calibration...), then one data line per point
and, for MCA scans, ``@A`` spectrum lines (continued with ``\\``). File header
lines (``#F``, ``#E``, ``#O`` motor names...) apply to the scans that follow.

The same scan number may appear several times in a file: scans are identified
by ``"<number>.<occurrence>"`` (e.g. ``"12.1"``, ``"12.2"``). Opening a file
only indexes its scans; the data of a scan is read when the scan is read.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import numpy as np

__all__ = ["SpecFile", "SpecScan", "SpecScanInfo", "is_spec_file"]

#: Number of bytes inspected to recognize a SPEC file
SNIFF_SIZE = 65536

_SPLIT_LABELS = re.compile(r"\s{2,}")


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


@dataclasses.dataclass(frozen=True)
class SpecScanInfo:
    """Scan of a SPEC file, as indexed when the file is opened.

    Args:
        number: scan number
        occurrence: occurrence of the scan number in the file (from 1)
        command: scan command (e.g. ``ascan th 0 1 10 0.1``)
        date: ``#D`` date of the scan
        labels: column labels
        point_count: number of data lines
        mca_count: number of MCA spectra
    """

    number: int
    occurrence: int
    command: str
    date: str
    labels: tuple[str, ...]
    point_count: int
    mca_count: int

    @property
    def key(self) -> str:
        """Scan identifier: ``"<number>.<occurrence>"``."""
        return f"{self.number}.{self.occurrence}"


@dataclasses.dataclass(frozen=True)
class SpecScan:
    """Scan read from a SPEC file.

    Args:
        info: scan index entry
        data: data points, one column per label (incomplete lines are dropped)
        motors: motor positions at the start of the scan (``#O``/``#P``)
        header: scan header lines
        mca: MCA spectra, in acquisition order
        mca_calibration: ``#@CALIB`` coefficients ``(a, b, c)``, if any
        mca_channels: ``#@CHANN`` values ``(count, first, last, reduction)``, if any
        problems: lines that could not be read as data, with their reason
    """

    info: SpecScanInfo
    data: np.ndarray
    motors: dict[str, float]
    header: tuple[str, ...]
    mca: tuple[np.ndarray, ...]
    mca_calibration: tuple[float, float, float] | None
    mca_channels: tuple[int, int, int, int] | None
    problems: tuple[str, ...]

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

    def mca_channels_axis(self, index: int) -> np.ndarray:
        """Return the channel numbers of an MCA spectrum."""
        size = self.mca[index].size
        if self.mca_channels is None:
            return np.arange(size, dtype=float)
        _count, first, _last, reduction = self.mca_channels
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
                labels=scan["labels"],
                point_count=scan["points"],
                mca_count=scan["mca"],
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
                    "labels": (),
                    "points": 0,
                    "mca": 0,
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
                scan["labels"] = tuple(_SPLIT_LABELS.split(line[3:].strip()))
            elif line.startswith("#D "):
                scan["date"] = line[3:].strip()
            elif stripped.startswith("@A"):
                scan["mca"] += 1
                continued = stripped.endswith("\\")
            elif stripped and not stripped.startswith(("#", "@")):
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
        mca: list[np.ndarray] = []
        calibration = channels = None
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
                if stripped.startswith("#@CALIB"):
                    values = _numbers(stripped[7:])
                    calibration = tuple((values + [0.0, 0.0, 0.0])[:3])
                elif stripped.startswith("#@CHANN"):
                    values = _numbers(stripped[7:])
                    if len(values) == 4:
                        channels = tuple(int(value) for value in values)
                elif re.match(r"#P\d+ ", stripped):
                    positions.extend(_numbers(stripped.split(maxsplit=1)[1]))
                continue
            if stripped.startswith("@A"):
                text = stripped[2:]
                while text.endswith("\\") and index < len(lines):
                    text = text[:-1] + " " + lines[index].strip()
                    index += 1
                mca.append(np.array(_numbers(text.rstrip("\\"))))
                continue
            try:
                values = _numbers(stripped)
            except ValueError:
                problems.append(f"line '{stripped[:40]}': not numeric")
                continue
            if ncols and len(values) != ncols:
                problems.append(
                    f"line '{stripped[:40]}': {len(values)} values for {ncols} columns"
                )
                continue
            rows.append(values)
        data = np.array(rows, dtype=float).reshape(len(rows), ncols or 0)
        motor_names = [
            name
            for line in section.file_header
            if re.match(r"#O\d+ ", line)
            for name in _SPLIT_LABELS.split(line.split(maxsplit=1)[1].strip())
        ]
        motors = dict(zip(motor_names, positions))
        return SpecScan(
            info=info,
            data=data,
            motors=motors,
            header=tuple(header),
            mca=tuple(mca),
            mca_calibration=calibration,
            mca_channels=channels,
            problems=tuple(problems),
        )
