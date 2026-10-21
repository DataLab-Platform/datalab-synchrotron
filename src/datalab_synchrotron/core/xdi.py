"""Reader of XDI files (XAS Data Interchange format, versions 1.x).

An XDI file holds one X-ray absorption scan as text: ``#``-prefixed header fields
``Namespace.tag: value`` (columns, element and edge, beamline, sample...), user
comments after ``# ///``, a ``#----`` line, then whitespace-separated data
columns. Field names are case-insensitive. Values often carry an EPICS process
variable after ``||``, which is kept apart.
"""

from __future__ import annotations

import dataclasses
import re
from pathlib import Path

import numpy as np

__all__ = ["XdiColumn", "XdiFile", "is_xdi_file", "read_xdi"]

_VERSION = re.compile(r"^#\s*XDI/(\d+\.\d+)", re.IGNORECASE)
_FIELD = re.compile(r"^#\s*([A-Za-z][\w-]*)\.([\w-]+)\s*:\s?(.*)$")


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
        skipped_lines: numbers of the data lines without a value per column
    """

    path: str
    version: str
    fields: dict[str, str]
    comments: tuple[str, ...]
    columns: tuple[XdiColumn, ...]
    data: np.ndarray
    skipped_lines: tuple[int, ...] = ()

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


def is_xdi_file(path: str | Path) -> bool:
    """Return True if the file starts with an XDI version line."""
    try:
        with open(path, encoding="latin-1") as fdesc:
            return bool(_VERSION.match(fdesc.readline()))
    except (OSError, UnicodeDecodeError):
        return False


def _column(value: str) -> XdiColumn:
    """Return a column from its ``Column.N`` field value."""
    words = re.split(r"\s*(?:\|\||#)", value, maxsplit=1)[0].split()
    if not words:
        raise ValueError("Empty column name")
    return XdiColumn(words[0], words[1] if len(words) > 1 else "")


def read_xdi(path: str | Path) -> XdiFile:
    """Read an XDI file.

    Args:
        path: file path

    Returns:
        File content; data lines without a value per column are skipped and
        their numbers recorded

    Raises:
        ValueError: if the file is not an XDI file or has no data
    """
    lines = Path(path).read_text(encoding="latin-1").splitlines()
    match = _VERSION.match(lines[0]) if lines else None
    if match is None:
        raise ValueError(f"'{path}' is not an XDI file (no XDI version line)")
    fields: dict[str, str] = {}
    comments: list[str] = []
    numbered: dict[int, XdiColumn] = {}
    in_comments, last_header = False, ""
    rows: list[list[float]] = []
    skipped: list[int] = []
    for number, line in enumerate(lines[1:], start=2):
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("#"):
            text = stripped[1:].strip()
            if text.startswith("///"):
                in_comments = True
            elif text.startswith("---"):
                in_comments = False
            elif in_comments:
                comments.append(text)
            else:
                field = _FIELD.match(stripped)
                if field is not None:
                    name = f"{field.group(1)}.{field.group(2)}"
                    fields[name] = field.group(3).strip()
                    if field.group(1).lower() == "column" and field.group(2).isdigit():
                        numbered[int(field.group(2))] = _column(field.group(3))
            last_header = text
            continue
        try:
            values = [float(word) for word in stripped.split()]
        except ValueError:
            skipped.append(number)
            continue
        if rows and len(values) != len(rows[0]):
            skipped.append(number)
            continue
        rows.append(values)
    if not rows:
        raise ValueError(f"'{path}' has no data")
    count = len(rows[0])
    if numbered:
        columns = [
            numbered.get(index, XdiColumn(f"column{index}"))
            for index in range(1, count + 1)
        ]
    else:
        names = last_header.split()
        names += [f"column{index + 1}" for index in range(len(names), count)]
        columns = [XdiColumn(names[index]) for index in range(count)]
    return XdiFile(
        path=str(path),
        version=match.group(1),
        fields=fields,
        comments=tuple(comments),
        columns=tuple(columns),
        data=np.array(rows, dtype=float),
        skipped_lines=tuple(skipped),
    )
