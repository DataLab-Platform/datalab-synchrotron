"""SPEC files of the validation corpus (``tests/data/spec``).

The corpus holds extracts of real files: scans chosen for the conventions they
cover, written with the file header that applies to them, sometimes limited to
their first points. They are generated from sources at pinned commits by
``tests/validation/make_spec_corpus.py``, which also writes the reference values
read by spec2nexus (or by silx, for files spec2nexus cannot read).

This module depends on the standard library only, so that the generator can run
in an environment without DataLab.
"""

from __future__ import annotations

import dataclasses
import hashlib
from pathlib import Path

DATA_DIR = Path(__file__).parents[1] / "data" / "spec"
REFERENCES = DATA_DIR / "references.json"

SPEC2NEXUS_COMMIT = "7d315b23463631ae07c98a07d2abc0034e665431"
PYMCA_COMMIT = "4fbf74ac4edc032b54d9ab05f4ddb75ca19a1aa8"
_SPEC2NEXUS = (
    f"https://raw.githubusercontent.com/prjemian/spec2nexus/{SPEC2NEXUS_COMMIT}/"
    "spec2nexus/"
)
_PYMCA = f"https://raw.githubusercontent.com/vasole/pymca/{PYMCA_COMMIT}/src/"


@dataclasses.dataclass(frozen=True)
class Extract:
    """File of the corpus, extracted from a source file.

    Args:
        filename: corpus file name
        url: source file, at a pinned commit
        source_sha256: SHA-256 of the source file
        sha256: SHA-256 of the corpus file
        covers: conventions covered by the file
        scans: scans extracted, as ``(number, occurrence)`` (None: whole file)
        max_points: number of points kept per scan (None: all points)
    """

    filename: str
    url: str
    source_sha256: str
    sha256: str
    covers: str
    scans: tuple[tuple[int, int], ...] | None = None
    max_points: int | None = None

    @property
    def path(self) -> Path:
        """Return the corpus file path."""
        return DATA_DIR / self.filename


EXTRACTS = (
    Extract(
        "mca_spectra_example_scan1.spec",
        _SPEC2NEXUS + "data/mca_spectra_example.dat",
        "63b9f3eac4db8b9378f0d1ffe6573a11390100f1be07232650f41bf462c31655",
        "2f78a026eb4610d7d62666199c5d22fe0261e8ee796b0854ecbe8cde8fee4973",
        "4 MCA devices (@A1 to @A4), 256 channels, spectra after their point",
        ((1, 1),),
        3,
    ),
    Extract(
        "33id_spec_mesh_escan.spec",
        _SPEC2NEXUS + "data/33id_spec.dat",
        "fe960985d13d8416f7f83bbd9f29f144ae098ee71392ffea3ba94d7e01036c41",
        "8382eda7251322a60b4aeb9f065c7006d26b09b75fd8cffaa93846a969f6c07e",
        "mesh scan with an MCA spectrum before each point, #@CHANN, duplicate "
        "labels; Escan in keV",
        ((22, 1), (105, 1)),
    ),
    Extract(
        "issue216_scan1.spec",
        _SPEC2NEXUS + "tests/data/issue216_scan1.spec",
        "59a464e2540b653a7213a67d306c880b55458f0dd04166e6297630ac5b3a42e3",
        "59a464e2540b653a7213a67d306c880b55458f0dd04166e6297630ac5b3a42e3",
        "labels separated by single spaces",
    ),
    Extract(
        "user6idd.dat",
        _SPEC2NEXUS + "data/user6idd.dat",
        "fe5e152fab93ad9f25e1b519b3e3bb79c0d54e924b8150d65bc140e7873919b2",
        "fe5e152fab93ad9f25e1b519b3e3bb79c0d54e924b8150d65bc140e7873919b2",
        "labels separated by single spaces, matching #N",
    ),
    Extract(
        "20220311-161530_scan2.spec",
        _SPEC2NEXUS + "data/20220311-161530.dat",
        "9f135a9949750957c8cc0808f4f83eafb2babd9c7154e23bbc8df86d5623252f",
        "705d3b568f84e6990cc9d8e214b3ded6220a7777b0c21c6e1495c0a6b897b475",
        "Bluesky file header with empty motor lines (#O0, #o0)",
        ((2, 1),),
    ),
    Extract(
        "05_02_test_none.spec",
        _SPEC2NEXUS + "data/05_02_test.dat",
        "cfbd0d445df803961a0125f169414f667b240e4bc46a281206dd31448fe56242",
        "0382b639e8c194973b8d5f9be439dd96c749b83e9a903b67230d7c9d42c1c318",
        "Bluesky scans with a wrong #N column count, and None values",
        ((1, 1), (1, 6)),
    ),
    Extract(
        "spec_from_spock_scan1.spec",
        _SPEC2NEXUS + "data/spec_from_spock.spc",
        "5ae789e62a54fa6408c5bbd66efa9281a1e903971980c714a12473ec1f395615",
        "8d732c180fd90e8239e6cf227af639e1a74ab8ba65b1bafe187ea37860502ff6",
        "Sardana (spock) file with nan values",
        ((1, 1),),
    ),
    Extract(
        "startup_1_scan16.spec",
        _SPEC2NEXUS + "data/startup_1.spec",
        "8e948d1eebd0acc6813618af81188a076e1246736b813c211dc9ec54e70e6ea2",
        "dc5a21de6abf49b59529aa58b3bdfd5b2bbeb1c6d641ea2f61a1ecad1611baee",
        "@0 lines with continuations, which are not MCA spectra",
        ((16, 1),),
        3,
    ),
    Extract(
        "CdSe_scan92.spec",
        _SPEC2NEXUS + "data/CdSe",
        "67e4b7b8518722d8e9438e7010736164ab5240efbfca520a9457dd87af411a02",
        "a2ec02b696f819c4f2dcd9576182b426d8f35f6c3fb024d65daef6ec1c1638a5",
        "interrupted scan ending with an incomplete data line",
        ((92, 1),),
    ),
    Extract(
        "twoc.dat",
        _SPEC2NEXUS + "data/twoc.dat",
        "6d6bf0fb2202e2410d6831d4fe280488569010b300aba421cf81b06e696feedf",
        "6d6bf0fb2202e2410d6831d4fe280488569010b300aba421cf81b06e696feedf",
        "repeated scan numbers",
    ),
    Extract(
        "EXAFS_Cu.dat",
        _PYMCA + "PyMca5/PyMcaData/EXAFS_Cu.dat",
        "7c220b65258c13cf521c72f4ef6614f32fc9611f00e793afc4b8620f30847253",
        "7c220b65258c13cf521c72f4ef6614f32fc9611f00e793afc4b8620f30847253",
        "EXAFS spectrum of a copper foil (PyMca)",
    ),
)


def extract(name: str) -> Extract:
    """Return a corpus file by name."""
    return next(item for item in EXTRACTS if item.filename == name)


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()
