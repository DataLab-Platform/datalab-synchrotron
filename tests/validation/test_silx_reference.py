"""SPEC reader compared with silx, the reference reader of the community."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pytest
from support.spec_files import write_spec

from datalab_synchrotron.core import SpecFile

specfile = pytest.importorskip("silx.io.specfile")


def test_same_values_as_silx(tmp_path: Path) -> None:
    """Scans, labels, columns and MCA spectra match silx's reader."""
    fname = write_spec(tmp_path / "scans.spec")
    ours = SpecFile(fname)
    reference = specfile.SpecFile(fname)
    try:
        assert [info.key for info in ours.scans] == reference.keys()
        for info in ours.scans:
            scan, expected = ours.read_scan(info.key), reference[info.key]
            assert list(info.labels) == expected.labels
            assert info.command == expected.scan_header_dict["S"].split(maxsplit=1)[1]
            if expected.data.size:
                assert np.array_equal(scan.data, expected.data.T)
            assert len(scan.mca) == len(expected.mca)
            for index, spectrum in enumerate(scan.mca):
                assert np.array_equal(spectrum, expected.mca[index])
            if scan.motors:
                # silx drops the spaces inside motor names ("sample z")
                names = [name.replace(" ", "") for name in scan.motors]
                assert names == expected.motor_names
                assert list(scan.motors.values()) == expected.motor_positions
    finally:
        reference.close()
