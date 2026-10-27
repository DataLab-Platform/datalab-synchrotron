"""SPEC reader on extracts of real files, compared with spec2nexus.

The reference values are those of spec2nexus, from the commit of the corpus
sources, or of silx for the files spec2nexus cannot read (see
``tests/validation/make_spec_corpus.py``). The reader differs from them on
purpose in two cases, checked separately:

- labels separated by single spaces, kept as one label by both readers, are
  split according to the column count;
- data lines holding ``None`` (Bluesky), dropped by spec2nexus, are read with NaN
  values.
"""

from __future__ import annotations

import json
import math

import numpy as np
import pytest
from sigima.objects import get_experimental_source
from support.spec_corpus import EXTRACTS, REFERENCES, Extract, extract, sha256

from datalab_synchrotron.core import SpecFile, import_scan
from datalab_synchrotron.formats import SpecSignalFormat

REFERENCE_FILES = json.loads(REFERENCES.read_text(encoding="utf-8"))["files"]

#: Scans read with other values than the reference reader's, and why
DIFFERENT_VALUES = {
    ("05_02_test_none.spec", "1.2"): "spec2nexus drops data lines holding None",
}


def _spec(name: str) -> SpecFile:
    """Return a corpus file."""
    return SpecFile(extract(name).path)


def _expected_labels(labels: list[str], count: int) -> list[str]:
    """Return the reference labels, split if the reference reader kept labels
    separated by single spaces as one label, and completed with ``column<n>`` up
    to the number of columns."""
    if len(labels) == 1:
        labels = labels[0].split()
    return labels + [f"column{index + 1}" for index in range(len(labels), count)]


@pytest.mark.parametrize("item", EXTRACTS, ids=lambda item: item.filename)
def test_corpus_files(item: Extract) -> None:
    """Corpus files are those generated from the pinned sources."""
    assert sha256(item.path) == item.sha256


@pytest.mark.parametrize("item", EXTRACTS, ids=lambda item: item.filename)
def test_same_values_as_reference(item: Extract) -> None:
    """Scans, labels, column values and MCA spectra of each device are those read
    by the reference reader."""
    reference = REFERENCE_FILES[item.filename]
    spec = SpecFile(item.path)
    assert [info.key for info in spec.scans] == [
        scan["key"] for scan in reference["scans"]
    ]
    for expected in reference["scans"]:
        scan = spec.read_scan(expected["key"])
        columns = expected["columns"]
        assert list(scan.info.labels) == _expected_labels(
            expected["labels"], len(columns)
        )
        if (item.filename, expected["key"]) in DIFFERENT_VALUES:
            continue
        if not columns:
            assert scan.data.shape[0] == 0
            continue
        assert scan.data.shape[1] == len(columns)
        for index, (count, nans, total) in enumerate(columns):
            column = scan.data[:, index]
            assert (column.size, int(np.isnan(column).sum())) == (count, nans)
            np.testing.assert_allclose(np.nansum(column), total, rtol=1e-12)
        mca = {
            device: [len(spectra), spectra[0].size, float(np.sum(spectra))]
            for device, spectra in scan.mca.items()
        }
        assert mca == expected["mca"]


def test_mca_devices() -> None:
    """The four MCA devices of a scan are imported as four images of 256
    channels, one spectrum per point, versus the energy."""
    spec = _spec("mca_spectra_example_scan1.spec")
    info = spec.get_info("1.1")
    assert info.mca_devices == ("mca1", "mca2", "mca3", "mca4")
    devices = list(info.mca_devices)
    group, skipped = import_scan(spec, "1.1", "Energy", [], devices)
    assert skipped is None
    assert [image.title for image in group.images] == [
        f"{device} (scan 1.1)" for device in devices
    ]
    for image in group.images:
        assert image.data.shape == (3, 256)
        assert image.ylabel == "Energy"


def test_mesh_scan() -> None:
    """A mesh scan with an MCA spectrum per point gives an image per counter and
    an image of the spectra; a repeated label gets a suffix."""
    spec = _spec("33id_spec_mesh_escan.spec")
    info = spec.get_info("22.1")
    assert info.labels[-2:] == ("I0", "I0_1")
    group, skipped = import_scan(spec, "22.1", "", ["elastic"], ["mca"])
    assert skipped is None
    mesh, mca = group.images
    assert mesh.data.shape == (11, 11)
    assert (mesh.xlabel, mesh.ylabel) == ("eta", "chi")
    np.testing.assert_allclose((mesh.dx, mesh.dy), (0.01, 0.01))
    assert mca.data.shape[0] == 121
    assert spec.get_info("105.1").command.startswith("Escan")


@pytest.mark.parametrize(
    "name, key, count",
    [("issue216_scan1.spec", "1.1", 7), ("user6idd.dat", "2.1", 25)],
)
def test_single_space_labels(name: str, key: str, count: int) -> None:
    """Labels separated by single spaces are split according to the column
    count."""
    spec = _spec(name)
    scan = spec.read_scan(key)
    assert len(scan.info.labels) == count
    assert scan.data.shape[1] == count and scan.data.shape[0] > 0
    assert not scan.problems


def test_empty_motor_lines() -> None:
    """Bluesky files with empty motor lines are read, without motor positions."""
    spec = _spec("20220311-161530_scan2.spec")
    scan = spec.read_scan("2.1")
    assert scan.motors == {} and scan.data.shape[0] > 0


def test_none_values() -> None:
    """``None`` values are NaN, and the other values of their line are kept; the
    wrong ``#N`` count is ignored."""
    scan = _spec("05_02_test_none.spec").read_scan("1.2")
    assert scan.data.shape == (1, 11)
    np.testing.assert_array_equal(
        scan.data[0, :4], [3.806389331817627, 4.0, 30000000.0, 3724.0]
    )
    assert math.isnan(scan.column("scaler0")[0])


def test_nan_values() -> None:
    """``nan`` values are NaN."""
    scan = _spec("spec_from_spock_scan1.spec").read_scan("1.1")
    assert np.isnan(scan.column("lks336_outputchannela")).all()


def test_other_at_lines() -> None:
    """``@`` lines that are not MCA spectra are ignored with their continuations,
    and counted in the origin of the signals."""
    spec = _spec("startup_1_scan16.spec")
    scan = spec.read_scan("16.1")
    assert scan.ignored == {"@0": 3}
    assert not scan.problems and not scan.mca
    group, _skipped = import_scan(spec, "16.1", "TwoTheta", ["I00"])
    source = get_experimental_source(group.signals[0])
    assert source["details"]["ignored_lines"] == {"@0": 3}


def test_interrupted_scan() -> None:
    """The incomplete line of an interrupted scan, and the data line merged with a
    comment after it, are skipped and reported."""
    scan = _spec("CdSe_scan92.spec").read_scan("92.1")
    incomplete, merged = scan.problems
    assert incomplete.endswith("29 values for 55 columns")
    assert merged.endswith("not numeric")
    assert scan.data.shape == (19, 55)


def test_repeated_scan_numbers() -> None:
    """Repeated scan numbers are told apart by their occurrence."""
    assert [info.key for info in _spec("twoc.dat").scans] == ["1.1", "2.1", "2.2"]


def test_open_exafs_file() -> None:
    """File > Open reads the absorption spectrum versus the energy."""
    (signal,) = SpecSignalFormat().read(str(extract("EXAFS_Cu.dat").path))
    assert (signal.xlabel, signal.ylabel) == ("Column 1", "Column 2")
    assert signal.x.size > 100
