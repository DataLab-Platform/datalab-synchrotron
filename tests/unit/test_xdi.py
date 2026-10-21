"""XDI reader, on measured files of several beamlines and on synthetic files."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from support.xas_corpus import DATA_DIR, read_columns, spectrum

from datalab_synchrotron.core import is_xdi_file, read_xdi

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
    assert not xdi.skipped_lines


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
    """Without Column fields, labels come from the last header line; malformed
    data lines are skipped and recorded."""
    path = tmp_path / "minimal.xdi"
    path.write_text(
        "# XDI/1.0\n# Element.symbol: Fe\n#----\n# energy mu\n"
        "7100 0.1\n7101 bad\n7102\n7103 0.4\n",
        encoding="utf-8",
    )
    xdi = read_xdi(path)
    assert [column.name for column in xdi.columns] == ["energy", "mu"]
    assert xdi.skipped_lines == (6, 7)
    np.testing.assert_array_equal(xdi.column("mu"), [0.1, 0.4])
    assert xdi.element == "Fe" and xdi.edge == ""
