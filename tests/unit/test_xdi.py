"""XDI reader, on measured files of several beamlines and on synthetic files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sigima.objects import get_experimental_source
from support.xas_corpus import DATA_DIR, read_columns, spectrum

from datalab_synchrotron.core import (
    HC_EV_ANGSTROM,
    is_xdi_file,
    read_xdi,
    xdi_energy,
    xdi_signals,
)

XDI_FILES = sorted(path.name for path in DATA_DIR.glob("*.xdi"))


@pytest.mark.parametrize("name", XDI_FILES)
def test_read_measured_files(name: str) -> None:
    """Columns and values of measured files are read as written."""
    path = DATA_DIR / name
    assert is_xdi_file(path)
    xdi = read_xdi(path)
    assert xdi.version in ("1.0", "1.1")
    expected = read_columns(path)
    assert [column.name.lower() for column in xdi.columns] == list(expected)
    np.testing.assert_array_equal(xdi.data, np.column_stack(list(expected.values())))
    assert xdi.columns[0].units == "eV"
    assert not xdi.problems


def test_fields_and_comments() -> None:
    """Fields are found whatever their case; comments and PVs are kept apart."""
    nickel = read_xdi(DATA_DIR / "ni_metal_rt.xdi")
    assert (nickel.element, nickel.edge) == ("Ni", "K")
    assert nickel.field("sample.NAME") == "Ni metal foil"
    assert nickel.comments[0] == "room temperature"
    copper = read_xdi(spectrum("cu_foil").path)
    assert (copper.element, copper.edge) == ("Cu", "K")
    vanadium = read_xdi(DATA_DIR / "v_foil.xdi")
    assert [(column.name, column.units) for column in vanadium.columns] == [
        ("energy", "eV"),
        ("scaler_count_time", "counts"),
        ("i0", "counts"),
        ("i1", "counts"),
    ]
    glass = read_xdi(DATA_DIR / "cu_romanglass.xdi")
    assert glass.columns[3].name == "ifluor"
    np.testing.assert_array_equal(glass.column("I0"), glass.data[:, 5])
    with pytest.raises(KeyError, match="No column"):
        glass.column("i2")


def test_other_files_are_not_xdi(tmp_path: Path) -> None:
    """Column files without XDI version line are refused."""
    other = DATA_DIR / "fe2o3_rt1.xmu"
    assert not is_xdi_file(other)
    with pytest.raises(ValueError, match="not an XDI file"):
        read_xdi(other)
    assert not is_xdi_file(tmp_path / "missing.xdi")


def test_labels_without_column_fields(tmp_path: Path) -> None:
    """Without Column fields, labels come from the line following the header end."""
    path = tmp_path / "minimal.xdi"
    path.write_text(
        "# XDI/1.0\n# Element.symbol: Fe\n#----\n# energy mu\n7100 0.1\n7103 0.4\n",
        encoding="utf-8",
    )
    xdi = read_xdi(path)
    assert [column.name for column in xdi.columns] == ["energy", "mu"]
    np.testing.assert_array_equal(xdi.column("mu"), [0.1, 0.4])
    assert xdi.element == "Fe" and xdi.edge == ""


_HEADER = "# XDI/1.0 GSE/1.0\n# Column.1: energy eV\n# Column.2: mu\n"


@pytest.mark.parametrize(
    "line, message",
    [
        ("7102 0.2 0.3", "line 6: 3 values for 2 columns"),
        ("7102", "line 6: 1 values for 2 columns"),
        ("7102 nan", "line 6: 'nan' is not a finite number"),
        ("7102 bad", "line 6: 'bad' is not a number"),
        ("7102 1.2.3", "line 6: '1.2.3' is not a number"),
    ],
)
def test_invalid_data_lines(tmp_path: Path, line: str, message: str) -> None:
    """Invalid data lines are refused with their line number, as the reference
    XDI library does, instead of being left out silently."""
    path = tmp_path / "invalid.xdi"
    path.write_text(f"{_HEADER}#----\n7100 0.1\n{line}\n", encoding="utf-8")
    with pytest.raises(ValueError, match=f"'invalid.xdi', {message}"):
        read_xdi(path)


def test_header_problems(tmp_path: Path) -> None:
    """Invalid header lines are recorded and ignored; the last occurrence of a
    field wins, whatever its case."""
    path = tmp_path / "header.xdi"
    path.write_text(
        _HEADER
        + "# Sample.name: first\n# Family.key:\n# Family.key  Value\n"
        + "# 2000Family.key: Value\n# Family.00key: Value\n# sample.NAME: last\n"
        + "! Beamline.name: 13ID\n#----\n7100 0.1\n",
        encoding="utf-8",
    )
    xdi = read_xdi(path)
    assert xdi.problems == (
        "line 5: field without value",
        "line 6: not a 'Namespace.tag: value' field",
        "line 7: not a 'Namespace.tag: value' field",
        "line 10: unsupported comment character '!'",
    )
    assert xdi.field("Sample.name") == "last"
    assert "Sample.name" not in xdi.fields
    assert xdi.field("Family.00key") == "Value"
    assert xdi.applications == "GSE/1.0"


def test_utf8_text_and_comments(tmp_path: Path) -> None:
    """Free text is read as UTF-8; comments keep their inner spaces."""
    path = tmp_path / "utf8.xdi"
    path.write_text(
        _HEADER
        + "# Sample.name: Échantillon µ-Cu, 25 °C\n# ///\n#  two  spaces kept\n#\n"
        + "#----\n# energy mu\n7100 0.1\n",
        encoding="utf-8",
    )
    xdi = read_xdi(path)
    assert xdi.field("Sample.name") == "Échantillon µ-Cu, 25 °C"
    assert xdi.comments == (" two  spaces kept", "")
    latin1 = tmp_path / "latin1.xdi"
    latin1.write_bytes(path.read_bytes().decode("utf-8").encode("latin-1"))
    assert read_xdi(latin1).field("Sample.name") == "Échantillon µ-Cu, 25 °C"


def test_header_without_end_line(tmp_path: Path) -> None:
    """Data without header-end line is read, and the problem is recorded."""
    path = tmp_path / "noend.xdi"
    path.write_text(_HEADER + "# ///\n# comment\n7100 0.1\n", encoding="utf-8")
    xdi = read_xdi(path)
    assert xdi.data.shape == (1, 2)
    assert xdi.problems == ("line 6: data without header-end line",)


def test_angle_to_energy(tmp_path: Path) -> None:
    """Monochromator angles are converted to energies with the Bragg law when the
    lattice spacing is given, and kept otherwise."""
    path = tmp_path / "angle.xdi"
    header = "# XDI/1.0\n# Column.1: angle degrees\n# Column.2: mu\n"
    path.write_text(
        header + "# Mono.d_spacing: 3.13553\n#----\n14.6 0.1\n14.4 0.2\n",
        encoding="utf-8",
    )
    xdi = read_xdi(path)
    energy, column, conversions = xdi_energy(xdi)
    expected = HC_EV_ANGSTROM / (2 * 3.13553 * np.sin(np.deg2rad([14.6, 14.4])))
    np.testing.assert_allclose(energy, expected)
    assert (column.name, column.units) == ("energy", "eV")
    assert conversions[0].startswith("angle -> energy: E = hc / (2 d sin(angle))")
    (signal,) = xdi_signals(xdi)
    assert (signal.xlabel, signal.xunit) == ("energy", "eV")
    source = get_experimental_source(signal)
    assert source["selection"] == {"x": "angle", "y": "mu"}
    assert source["conversions"] == conversions
    path.write_text(header + "#----\n14.6 0.1\n", encoding="utf-8")
    energy, column, conversions = xdi_energy(read_xdi(path))
    assert column.name == "angle" and not conversions


def test_metadata() -> None:
    """Every header field and the comments are kept as object metadata."""
    (signal, *_others) = xdi_signals(read_xdi(DATA_DIR / "ni_metal_rt.xdi"))
    assert signal.metadata["Sample.name"] == "Ni metal foil"
    assert signal.metadata["Element.symbol"] == "Ni"
    assert signal.metadata["XDI version"].startswith("XDI/1.0")
    assert signal.metadata["XDI comments"].startswith("room temperature")
    assert "XDI problems" not in signal.metadata
