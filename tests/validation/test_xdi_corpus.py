"""XDI reader on the test files of the XDI library.

The XDI library refuses the files whose data table is invalid, or whose header
has a line that is not a valid field; it reads the others, warning about missing
or invalid values (``tests/data/xdi/BadFiles.txt``). The reader refuses the same
data tables, but reads the files with invalid header lines, recording them as
problems: a field written by hand does not make the data unusable. It does not
check the values of the fields (element, edge, dates...).
"""

from __future__ import annotations

import hashlib
import math
from pathlib import Path

import numpy as np
import pytest
from sigima.objects import get_experimental_source

from datalab_synchrotron.core import read_xdi, xdi_signals

DATA_DIR = Path(__file__).parents[1] / "data" / "xdi"

_NOT_FIELD = "line 8: not a 'Namespace.tag: value' field"

#: Reader result for each invalid file: header problems if it is read, or the
#: error message if it is refused
INVALID_FILES = {
    "bad_00.xdi": (),
    "bad_01.xdi": "is not an XDI file",
    "bad_02.xdi": (),
    "bad_03.xdi": (),
    "bad_04.xdi": (),
    "bad_05.xdi": (),
    "bad_06.xdi": ("line 29: data without header-end line",),
    "bad_07.xdi": (),
    "bad_08.xdi": (),
    "bad_09.xdi": (),
    "bad_10.xdi": (),
    "bad_11.xdi": (
        "line 12: unsupported comment character '!'",
        "line 13: unsupported comment character '!'",
    ),
    "bad_12.xdi": (),
    "bad_13.xdi": "line 31: 3 values for 4 columns",
    "bad_14.xdi": "line 36: 6 values for 4 columns",
    "bad_15.xdi": "line 29: 'nan' is not a finite number",
    "bad_16.xdi": "line 30: 'STRING' is not a number",
    "bad_17.xdi": "line 29: '1.4.9' is not a number",
    "bad_18.xdi": ("line 8: field without value",),
    "bad_19.xdi": (_NOT_FIELD,),
    "bad_20.xdi": (_NOT_FIELD,),
    "bad_21.xdi": (_NOT_FIELD,),
    "bad_22.xdi": (_NOT_FIELD,),
    "bad_23.xdi": (),
    "bad_24.xdi": (_NOT_FIELD,),
    **{f"bad_{number}.xdi": () for number in range(25, 36)},
}


def _checksums() -> dict[str, str]:
    """Return the SHA-256 of the corpus files, by name."""
    lines = (DATA_DIR / "SHA256SUMS").read_text(encoding="utf-8").splitlines()
    return {name: digest for digest, name in (line.split() for line in lines)}


def test_corpus_files() -> None:
    """Corpus files are those of the XDI library."""
    checksums = _checksums()
    assert set(checksums) == {
        path.name for path in DATA_DIR.iterdir() if path.suffix in (".xdi", ".txt")
    } - {"SOURCES.txt"}
    for name, digest in checksums.items():
        assert hashlib.sha256((DATA_DIR / name).read_bytes()).hexdigest() == digest


@pytest.mark.parametrize("name", sorted(INVALID_FILES))
def test_invalid_files(name: str) -> None:
    """Invalid data tables are refused with their line, other files are read with
    their header problems."""
    expected = INVALID_FILES[name]
    path = DATA_DIR / name
    if isinstance(expected, str):
        with pytest.raises(ValueError, match=expected):
            read_xdi(path)
        return
    xdi = read_xdi(path)
    assert xdi.problems == expected
    assert xdi.data.shape[1] == 4
    if expected:
        assert xdi_signals(xdi)[0].metadata["XDI problems"] == "\n".join(expected)


def test_column_labels() -> None:
    """Missing column labels are named after their index."""
    names = [column.name for column in read_xdi(DATA_DIR / "bad_10.xdi").columns]
    assert names == ["energy", "i0", "itrans", "column4"]


def test_angle_without_lattice_spacing() -> None:
    """Angles are kept when the lattice spacing is not given."""
    (signal, *_others) = xdi_signals(read_xdi(DATA_DIR / "bad_12.xdi"))
    assert signal.xlabel == "angle"
    assert not get_experimental_source(signal).get("conversions")


def test_non_xafs_files() -> None:
    """Files of other measurements and XDI 1.1 files are read."""
    profile = read_xdi(DATA_DIR / "nonxafs_1d.xdi")
    assert profile.columns[0].name == "x" and profile.data.shape == (408, 4)
    negative = read_xdi(DATA_DIR / "nonxafs_negvalues.xdi")
    assert negative.version == "1.1" and (negative.data < 0).any()


def test_outer_scan() -> None:
    """Two-dimensional data gives one signal per block of the outer scan."""
    xdi = read_xdi(DATA_DIR / "nonxafs_2d.xdi")
    assert len(xdi.outer) == 41 and xdi.outer[:2] == ((1.0, 0), (1.1, 5))
    signals = xdi_signals(xdi, ["mutrans"])
    assert len(signals) == 41
    first = signals[0]
    assert first.title == "mutrans (nonxafs_2d.xdi, x2d = 1)"
    np.testing.assert_array_equal(first.x, xdi.data[:5, 0])
    assert first.metadata["XDI outer value"] == 1.0
    assert get_experimental_source(first)["selection"]["outer"] == 1.0
    assert sum(signal.x.size for signal in signals) == xdi.data.shape[0]
    assert not math.isnan(xdi.outer[-1][0])
