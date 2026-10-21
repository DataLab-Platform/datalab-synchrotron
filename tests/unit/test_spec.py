"""SPEC files: index, data, MCA spectra and conversion to signals."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from sigima.objects import get_experimental_source
from support.spec_files import write_spec

from datalab_synchrotron.core import SpecFile, is_spec_file, mca_signals, scan_signals


@pytest.fixture(name="spec")
def fixture_spec(tmp_path: Path) -> SpecFile:
    """Synthetic SPEC file."""
    return SpecFile(write_spec(tmp_path / "scans.dat"))


def test_index(spec: SpecFile) -> None:
    """Repeated scan numbers are told apart by their occurrence."""
    keys = [info.key for info in spec.scans]
    assert keys == ["1.1", "1.2", "2.1", "3.1", "4.1"]
    first, second = spec.scans[:2]
    assert first.command == "ascan  th 1 0.6 4 0.1"
    assert first.labels == ("Theta", "Monitor", "Detector counts")
    assert (first.point_count, second.point_count) == (5, 3)
    assert spec.get_info("3.1").mca_count == 1
    assert spec.get_info("4.1").mca_count == 3
    with pytest.raises(ValueError, match="has no scan 9.1"):
        spec.read_scan("9.1")


def test_scan_data_keeps_acquisition_order(spec: SpecFile) -> None:
    """Columns are read as written, even with a decreasing scanned motor."""
    scan = spec.read_scan("1.1")
    assert np.array_equal(scan.column("Theta"), [1.0, 0.9, 0.8, 0.7, 0.6])
    assert np.array_equal(scan.column("Detector counts"), [10, 25, 60, 24, 11])
    assert scan.motors == {"th": 1.0, "tth": 2.5, "sample z": -0.25}
    assert np.array_equal(spec.read_scan("1.2").column("Monitor"), [500, 501, 502])
    with pytest.raises(ValueError, match="no column 'I0'"):
        scan.column("I0")


def test_interrupted_scan(spec: SpecFile) -> None:
    """An incomplete data line is skipped and reported."""
    scan = spec.read_scan("2.1")
    assert scan.data.shape == (2, 3)
    assert scan.problems == ("line '2 1': 2 values for 3 columns",)
    assert any("Scan aborted" in line for line in scan.header)


def test_file_headers_apply_to_following_scans(spec: SpecFile) -> None:
    """Motor names come from the file header preceding each scan."""
    assert spec.read_scan("4.1").motors == {"energy": 7.1, "gap": 12.5}


def test_mca_spectra(spec: SpecFile) -> None:
    """MCA lines are joined across continuations and calibrated if declared."""
    scan = spec.read_scan("3.1")
    (spectrum,) = scan.mca
    assert np.array_equal(spectrum, np.arange(8))
    assert scan.mca_channels == (8, 2, 9, 1)
    assert scan.mca_calibration == (0.5, 0.25, 0.0)
    (signal,) = mca_signals(spec, scan)
    assert np.allclose(signal.x, 0.5 + 0.25 * np.arange(2, 10))
    source = get_experimental_source(signal)
    assert source["selection"] == {"mca": 0}
    assert source["conversions"][0].startswith("channels -> a + b*ch + c*ch^2")
    raw = mca_signals(spec, spec.read_scan("4.1"), [2])
    assert np.array_equal(raw[0].x, [0.0, 1.0, 2.0, 3.0])
    assert np.array_equal(raw[0].y, [3.0, 4.0, 5.0, 6.0])


def test_scan_signals_record_their_origin(spec: SpecFile) -> None:
    """Signals keep the scan, columns, command, date and motor positions."""
    scan = spec.read_scan("2.1")
    (signal,) = scan_signals(spec, scan, "Time", ["It"])
    assert signal.title == "It (scan 2.1)"
    assert (signal.xlabel, signal.ylabel) == ("Time", "It")
    assert np.array_equal(signal.y, [5.0, 6.0])
    assert get_experimental_source(signal) == {
        "version": 1,
        "kind": "spec",
        "location": spec.path,
        "entry": "2.1",
        "selection": {"x": "Time", "y": "It"},
        "details": {
            "command": "timescan 0.5",
            "date": "Tue Oct 20 10:10:00 2026",
            "skipped_lines": 1,
        },
    }


def test_is_spec_file(tmp_path: Path) -> None:
    """SPEC files are recognized by their content, not their extension."""
    assert is_spec_file(write_spec(tmp_path / "run.dat"))
    windows = SpecFile(write_spec(tmp_path / "crlf.spec", newline="\r\n"))
    assert [info.key for info in windows.scans] == ["1.1", "1.2", "2.1", "3.1", "4.1"]
    csv = tmp_path / "table.dat"
    csv.write_text("x,y\n1,2\n", encoding="utf-8")
    assert not is_spec_file(csv)
    assert not is_spec_file(tmp_path / "missing.dat")
    empty = tmp_path / "empty.spec"
    empty.write_text("#F empty\n", encoding="utf-8")
    with pytest.raises(ValueError, match="holds no SPEC scan"):
        SpecFile(empty)
