"""Reader of XDI files (XAS Data Interchange format, versions 1.x).

An XDI file holds one X-ray absorption scan as text: a version line
(``# XDI/1.0``, possibly followed by application versions), ``#``-prefixed
header fields ``Namespace.tag: value`` (columns, element and edge, beamline,
sample...), user comments after a ``# ///`` line, a ``#----`` header-end line,
an optional column label line, then whitespace-separated data columns. Field
names are case-insensitive, the last occurrence of a field being used. Values
often carry an EPICS process variable after ``||``, which is kept apart from
column names. Free text may be UTF-8; files that are not are read as Latin-1.

Files are read as the reference XDI library does: data lines that are not
numbers, hold NaN or infinite values, or whose value count differs from the
first data line are refused, with their line number. Header lines that are not
valid fields (no value, no ``:``, name not of the ``Namespace.tag`` form) and
header lines starting with another character than ``#`` are recorded as
problems and otherwise ignored. ``#`` lines of the data section are ignored,
except ``# Outer.value: <value>`` lines, which start a block of points measured
at another value of an outer scan (two-dimensional data, ``Outer.name`` naming
the outer scan).
"""

from __future__ import annotations

import dataclasses
import math
import re
from pathlib import Path

import numpy as np

__all__ = ["XdiColumn", "XdiFile", "is_xdi_file", "read_xdi"]

_VERSION = re.compile(r"^#\s*XDI/(\d+\.\d+)(.*)$", re.IGNORECASE)
_FIELD = re.compile(r"^([A-Za-z][\w-]*)\.([\w-]+)\s*:\s?(.*)$")


@dataclasses.dataclass(frozen=True)
class XdiColumn:
    """Data column of an XDI file.

    Args:
        name: column name, e.g. ``energy`` or ``i0``
        units: column units, if given
    """

    name: str
    units: str = ""


@dataclasses.dataclass(frozen=True)
class XdiFile:
    """Content of an XDI file.

    Args:
        path: file path
        version: XDI version, e.g. ``"1.0"``
        fields: header fields, by ``Namespace.tag`` name as written
        comments: user comment lines
        columns: data columns
        data: data values, one row per point
        applications: versions of the applications that wrote the file, as
         written after the XDI version (e.g. ``"GSE/1.0"``)
        problems: header lines that were ignored, with their line number and
         reason
        outer: blocks of an outer scan, as ``(outer value, first row)``, in row
         order (empty for one-dimensional data); the value is NaN if not given
    """

    path: str
    version: str
    fields: dict[str, str]
    comments: tuple[str, ...]
    columns: tuple[XdiColumn, ...]
    data: np.ndarray
    applications: str = ""
    problems: tuple[str, ...] = ()
    outer: tuple[tuple[float, int], ...] = ()

    def field(self, name: str, default: str = "") -> str:
        """Return a header field value, by case-insensitive ``Namespace.tag`` name."""
        lowered = name.lower()
        for key, value in self.fields.items():
            if key.lower() == lowered:
                return value
        return default

    def column_index(self, name: str) -> int:
        """Return the index of a column, by case-insensitive name.

        Raises:
            KeyError: if there is no such column
        """
        lowered = name.lower()
        for index, column in enumerate(self.columns):
            if column.name.lower() == lowered:
                return index
        raise KeyError(f"No column '{name}' in {Path(self.path).name}")

    def column(self, name: str) -> np.ndarray:
        """Return the values of a column, by case-insensitive name."""
        return self.data[:, self.column_index(name)]

    @property
    def element(self) -> str:
        """Return the absorbing element (``Element.symbol``), if given."""
        return self.field("Element.symbol") or self.field("Scan.element")

    @property
    def edge(self) -> str:
        """Return the absorption edge (``Element.edge``), if given."""
        return self.field("Element.edge") or self.field("Scan.edge")


def _decode(raw: bytes) -> str:
    """Return the text of a file: UTF-8, or Latin-1 for older files."""
    try:
        return raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        return raw.decode("latin-1")


def is_xdi_file(path: str | Path) -> bool:
    """Return True if the file starts with an XDI version line."""
    try:
        with open(path, "rb") as fdesc:
            first = _decode(fdesc.readline()).strip()
    except OSError:
        return False
    return bool(_VERSION.match(first))


def _column(value: str) -> XdiColumn:
    """Return a column from its ``Column.N`` field value."""
    words = re.split(r"\s*(?:\|\||#)", value, maxsplit=1)[0].split()
    if not words:
        raise ValueError("Empty column name")
    return XdiColumn(words[0], words[1] if len(words) > 1 else "")


def _is_number(word: str) -> bool:
    """Return True if a word is a number."""
    try:
        float(word)
    except ValueError:
        return False
    return True


def _data_values(text: str, where: str) -> list[float]:
    """Return the values of a data line.

    Raises:
        ValueError: if a value is not a finite number
    """
    values = []
    for word in text.split():
        try:
            value = float(word)
        except ValueError as exc:
            raise ValueError(f"{where}: '{word}' is not a number") from exc
        if not math.isfinite(value):
            raise ValueError(f"{where}: '{word}' is not a finite number")
        values.append(value)
    return values


def _outer_value(text: str, where: str) -> float:
    """Return the value of an ``Outer.value`` field.

    Raises:
        ValueError: if the value is not a number
    """
    try:
        return float(text.split()[0])
    except (IndexError, ValueError) as exc:
        raise ValueError(f"{where}: outer value '{text}' is not a number") from exc


class _Fields:
    """Header fields, case-insensitive, the last occurrence of a field winning."""

    def __init__(self) -> None:
        self.values: dict[str, str] = {}

    def set(self, name: str, value: str) -> None:
        """Set a field, replacing an earlier occurrence written in another case."""
        for key in [key for key in self.values if key.lower() == name.lower()]:
            del self.values[key]
        self.values[name] = value

    def get(self, name: str) -> str:
        """Return a field value by case-insensitive name (empty if not given)."""
        return next(
            (value for key, value in self.values.items() if key.lower() == name),
            "",
        )


def read_xdi(path: str | Path) -> XdiFile:
    """Read an XDI file.

    Args:
        path: file path

    Returns:
        File content

    Raises:
        ValueError: if the file is not an XDI file, has no data, or has an invalid
         data line
    """
    name = Path(path).name
    lines = _decode(Path(path).read_bytes()).splitlines()
    match = _VERSION.match(lines[0].strip()) if lines else None
    if match is None:
        raise ValueError(f"'{path}' is not an XDI file (no XDI version line)")
    fields = _Fields()
    comments: list[str] = []
    numbered: dict[int, XdiColumn] = {}
    problems: list[str] = []
    # Header sections, in file order, before the data section
    section, label_line = "fields", ""
    rows: list[list[float]] = []
    outer: list[tuple[float, int]] = []
    for number, line in enumerate(lines[1:], start=2):
        stripped = line.strip()
        if not stripped:
            continue
        if section == "data" and stripped.startswith("#"):
            field = _FIELD.match(stripped[1:].strip())
            if field is not None and (
                f"{field.group(1)}.{field.group(2)}".lower() == "outer.value"
            ):
                where = f"'{name}', line {number}"
                outer.append((_outer_value(field.group(3), where), len(rows)))
            continue
        if section != "data" and stripped.startswith("#"):
            body = line.lstrip()[1:].rstrip()
            text = body.strip()
            if section == "fields" and text.startswith("///"):
                section = "comments"
            elif text.startswith("---"):
                section = "labels"
            elif section == "comments":
                comments.append(body[1:] if body.startswith(" ") else body)
            elif section == "labels":
                label_line = text
            elif text:
                field = _FIELD.match(text)
                if field is None:
                    problems.append(
                        f"line {number}: not a 'Namespace.tag: value' field"
                    )
                elif not field.group(3).strip():
                    problems.append(f"line {number}: field without value")
                else:
                    namespace, tag = field.group(1), field.group(2)
                    fields.set(f"{namespace}.{tag}", field.group(3).strip())
                    if namespace.lower() == "column" and tag.isdigit():
                        numbered[int(tag)] = _column(field.group(3))
            continue
        if section != "data":
            if not _is_number(stripped.split()[0]):
                problems.append(
                    f"line {number}: unsupported comment character '{stripped[0]}'"
                )
                continue
            if section != "labels":
                problems.append(f"line {number}: data without header-end line")
            section = "data"
        values = _data_values(stripped, f"'{name}', line {number}")
        if rows and len(values) != len(rows[0]):
            raise ValueError(
                f"'{name}', line {number}: {len(values)} values "
                f"for {len(rows[0])} columns"
            )
        rows.append(values)
    if not rows:
        raise ValueError(f"'{path}' has no data")
    if outer and outer[0][1] > 0:
        # Points before the first outer value of the data section: header value
        first = fields.get("outer.value")
        initial = _outer_value(first, f"'{name}'") if first else math.nan
        outer.insert(0, (initial, 0))
    count = len(rows[0])
    if numbered:
        columns = [
            numbered.get(index, XdiColumn(f"column{index}"))
            for index in range(1, count + 1)
        ]
    else:
        names = label_line.split()
        names += [f"column{index + 1}" for index in range(len(names), count)]
        columns = [XdiColumn(names[index]) for index in range(count)]
    return XdiFile(
        path=str(path),
        version=match.group(1),
        fields=fields.values,
        comments=tuple(comments),
        columns=tuple(columns),
        data=np.array(rows, dtype=float),
        applications=match.group(2).strip(),
        problems=tuple(problems),
        outer=tuple(outer),
    )
