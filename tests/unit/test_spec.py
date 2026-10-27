"""SPEC files: index, data, MCA spectra and conversion to signals and images."""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest
from sigima.objects import get_experimental_source
from support.spec_files import MORE_TEXT, write_spec

from datalab_synchrotron.core import (
    SpecFile,
    is_spec_file,
    mca_images,
    mesh_images,
    mesh_shape,
    scan_metadata,
    scan_signals,
)


@pytest.fixture(name="spec")
def fixture_spec(tmp_path: Path) -> SpecFile:
    """Synthetic SPEC file."""
    return SpecFile(write_spec(tmp_path / "scans.dat"))


@pytest.fixture(name="more")
def fixture_more(tmp_path: Path) -> SpecFile:
    """Synthetic SPEC file with the conventions of other acquisition programs."""
    return SpecFile(write_spec(tmp_path / "more.spec", text=MORE_TEXT))


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
    assert spec.get_info("4.1").mca_devices == ("mca",)
    assert spec.get_info("1.1").mca_devices == ()
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
    """MCA lines are joined across continuations, with channel range and
    calibration."""
    scan = spec.read_scan("3.1")
    (spectrum,) = scan.mca["mca"]
    assert np.array_equal(spectrum, np.arange(8))
    assert scan.mca_channels == {"": (8, 2, 9, 1)}
    assert scan.calibration("mca") == (0.5, 0.25, 0.0)
    assert np.array_equal(scan.channel_numbers("mca"), np.arange(2, 10))
    with pytest.raises(ValueError, match="'mca9' has no spectrum"):
        scan.channel_numbers("mca9")


def test_mca_images(spec: SpecFile) -> None:
    """The spectra of a device are an image: one spectrum per row, calibrated
    channels along X, the X column of the scan along Y if it is monotonic."""
    scan = spec.read_scan("4.1")
    (image,) = mca_images(spec, scan, "Energy")
    assert image.title == "mca (scan 4.1)"
    np.testing.assert_array_equal(
        image.data, [[1, 2, 3, 4], [2, 3, 4, 5], [3, 4, 5, 6]]
    )
    np.testing.assert_array_equal(image.ycoords, [7.1, 7.2, 7.4])
    np.testing.assert_array_equal(image.xcoords, [0, 1, 2, 3])
    assert (image.xlabel, image.ylabel, image.zlabel) == ("Channel", "Energy", "Counts")
    assert get_experimental_source(image)["selection"] == {"mca": "mca", "y": "Energy"}
    (by_point,) = mca_images(spec, scan)
    assert by_point.ylabel == "Point"
    assert (by_point.x0, by_point.dx, by_point.y0, by_point.dy) == (0, 1, 0, 1)
    assert get_experimental_source(by_point)["selection"]["y"] == "point"
    (decreasing,) = mca_images(spec, scan, "It")
    np.testing.assert_array_equal(decreasing.ycoords, [47, 49, 50])
    np.testing.assert_array_equal(decreasing.data[0], [3, 4, 5, 6])
    (calibrated,) = mca_images(spec, spec.read_scan("3.1"))
    assert calibrated.xlabel == "Calibrated channel"
    assert (calibrated.x0, calibrated.dx) == (1.0, 0.25)
    conversions = get_experimental_source(calibrated)["conversions"]
    assert conversions[1].startswith("channels -> a + b*ch + c*ch^2")


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
    assert signal.metadata["SPEC comments"].endswith("Scan aborted after 2 points.")


def test_other_conventions(more: SpecFile) -> None:
    """Labels separated by single spaces are split according to the column count,
    missing values are NaN, and empty motor lines are accepted."""
    info = more.get_info("1.1")
    assert info.labels == ("Epoch", "seconds", "I0", "diode")
    scan = more.read_scan("1.1")
    assert math.isnan(scan.column("diode")[0])
    assert scan.column("diode")[1] == 12
    assert not scan.problems and scan.motors == {}


def test_scan_header_metadata(more: SpecFile) -> None:
    """Count time, monitor, hkl, geometry, comments and Bluesky metadata are kept."""
    metadata = scan_metadata(more.read_scan("1.1"))
    hkl, geometry = metadata.pop("SPEC hkl"), metadata.pop("SPEC geometry G0")
    np.testing.assert_array_equal(hkl, [1, 0, 0.5])
    np.testing.assert_array_equal(geometry, [0, 0, 1, 2])
    assert metadata == {
        "SPEC count time": 0.5,
        "SPEC count time unit": "seconds",
        "SPEC monitor count": 1000.0,
        "SPEC monitor counter": "I0",
        "SPEC MD uid": "1234-abcd",
        "SPEC comments": "Scan ended normally.",
    }
    (signal,) = scan_signals(more, more.read_scan("1.1"), "Epoch", ["I0"])
    assert signal.metadata["SPEC MD uid"] == "1234-abcd"


def test_mca_devices(more: SpecFile) -> None:
    """Spectra of several devices are told apart, with their own calibration and
    channels; other '@' lines are ignored and counted."""
    info = more.get_info("2.1")
    assert (info.point_count, info.mca_count) == (3, 6)
    assert info.mca_devices == ("mca1", "mca2")
    scan = more.read_scan("2.1")
    assert [spectrum.tolist() for spectrum in scan.mca["mca1"]] == [
        [1, 2, 3, 4],
        [2, 3, 4, 5],
        [3, 4, 5, 6],
    ]
    assert scan.ignored == {"@0": 1}
    assert not scan.problems
    mca1, mca2 = mca_images(more, scan, "Energy")
    assert (mca1.x0, mca1.dx) == (0, 1)
    assert (mca2.x0, mca2.dx) == (1, 2)
    assert (mca2.y0, mca2.dy) == (690, 1)
    np.testing.assert_array_equal(mca2.data[2], [7, 8, 9, 10])
    assert get_experimental_source(mca1)["details"]["ignored_lines"] == {"@0": 1}
    (only,) = mca_images(more, scan, "Energy", ["mca2"])
    assert only.title == "mca2 (scan 2.1)"


def test_mesh_images(more: SpecFile) -> None:
    """Counters of a mesh scan are images of the two motors; missing points of an
    interrupted mesh are NaN, and decreasing motors are reversed."""
    info = more.get_info("3.1")
    shape = mesh_shape(info)
    assert (shape.columns, shape.rows, shape.steps) == (3, 2, (1.0, -1.0))
    assert mesh_shape(more.get_info("2.1")) is None
    (image,) = mesh_images(more, more.read_scan("3.1"), ["counts"])
    assert (image.xlabel, image.ylabel, image.zlabel) == (
        "Sample X",
        "Sample Y",
        "counts",
    )
    assert (image.x0, image.dx, image.y0, image.dy) == (0, 1, 10, 1)
    np.testing.assert_array_equal(image.data, [[4, 5, np.nan], [1, 2, 3]])
    source = get_experimental_source(image)
    assert source["selection"] == {"x": "Sample X", "y": "Sample Y", "z": "counts"}
    assert "incomplete mesh: 1 points set to NaN" in source["conversions"]
    assert "axis 'Sample Y': reversed to increasing order" in source["conversions"]
    with pytest.raises(ValueError, match="not a mesh scan"):
        mesh_images(more, more.read_scan("2.1"), ["TEY"])


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
