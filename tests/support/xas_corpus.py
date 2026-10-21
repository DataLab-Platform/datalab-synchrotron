"""Measured XAS spectra of the validation corpus (``tests/data/xas``).

This module depends on NumPy only, so that the reference generator can run in an
environment with Larch and without DataLab.
"""

from __future__ import annotations

import dataclasses
import hashlib
import re
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parents[1] / "data" / "xas"
REFERENCES = DATA_DIR / "larch_references.json"

#: Edge energies (eV) of the reference foils: Elam, Ravel and Sieber tables,
#: Radiat. Phys. Chem. 63 (2002) 121, as distributed with xraydb
TABULATED_EDGES = {
    ("Cu", "K"): 8979.0,
    ("Ge", "K"): 11103.0,
    ("Ni", "K"): 8333.0,
    ("Pt", "L3"): 11564.0,
    ("V", "K"): 5465.0,
}


@dataclasses.dataclass(frozen=True)
class Spectrum:
    """One absorption spectrum of a corpus file.

    Args:
        name: spectrum identifier
        filename: file name in the data folder
        sha256: SHA-256 of the file
        mode: ``"transmission"``, ``"fluorescence"``, or None if ``mu`` is a column
        monitor: incident intensity column
        detector: transmitted or fluorescence intensity column
        mu: absorption column (computed by the beamline or by Larch)
        foil: element and edge of a reference foil (None: sample)
    """

    name: str
    filename: str
    sha256: str
    mode: str | None = None
    monitor: str | None = None
    detector: str | None = None
    mu: str | None = None
    foil: tuple[str, str] | None = None

    @property
    def path(self) -> Path:
        """Return the file path."""
        return DATA_DIR / self.filename

    def columns(self) -> dict[str, np.ndarray]:
        """Return the columns of the file, by lower-case label."""
        return read_columns(self.path)

    def energy_and_mu(self) -> tuple[np.ndarray, np.ndarray]:
        """Return energy and absorption, computed from counts when available."""
        columns = self.columns()
        energy = next(iter(columns.values()))
        if self.mode is None:
            return energy, columns[self.mu]
        monitor, detector = columns[self.monitor], columns[self.detector]
        if self.mode == "transmission":
            return energy, np.log(monitor / detector)
        return energy, detector / monitor


_CU = "bc9cc1fc81de2534330a7884669b0955c92f5ddb4f8219f5491b0a565cf0d220"
_CU_GLASS = "8cc7586fa4b635764a4678c37161f869c80e153544aecbd392622d673198a274"
_ESRF = "af4061530ebc8a3a0bdce8da355aba5346d9ad7dba4a903e2d4941b9e1c50a2d"

SPECTRA = (
    Spectrum("cu_foil", "cu_metal_rt.xdi", _CU, "transmission", "i0", "itrans",
             "mutrans", ("Cu", "K")),
    Spectrum("ni_foil", "ni_metal_rt.xdi",
             "676a29f67b0b65d9c8a81d1ae20c44d19537cba0a44a4a53028f2d56c96243e7",
             mu="mutrans", foil=("Ni", "K")),
    Spectrum("pt_foil", "pt_metal_rt.xdi",
             "594b67f748ccb5f68e44e737a6e4ab6157a9c83d4a0a434bf79338a2ae24e068",
             "transmission", "i0", "itrans", foil=("Pt", "L3")),
    Spectrum("v_foil", "v_foil.xdi",
             "177cce932b14d6b444035c42d32ebda84b78fc4c20a680da2d2d034921a66829",
             "transmission", "i0", "i1", foil=("V", "K")),
    Spectrum("cu_glass_fluorescence", "cu_romanglass.xdi", _CU_GLASS,
             "fluorescence", "i0", "ifluor", "mufluor"),
    Spectrum("cu_glass_transmission", "cu_romanglass.xdi", _CU_GLASS,
             "transmission", "i0", "itrans", "mutrans"),
    Spectrum("fe3c", "fe3c_rt.xdi",
             "e650d741de2199a1b8568c51a5bc238255d5933f0b3900016ed56c36b85ea584",
             mu="mutrans"),
    Spectrum("fe2o3", "fe2o3_rt1.xmu",
             "85e497dd98761e014ddcb31f736d38ec0700c11a9c2c51cd8950b73dc273c5ed",
             mu="mu"),
    Spectrum("esrf_sample", "ESRF_BM08_LISA_2021.dat", _ESRF, "transmission",
             "i0_eh1", "i1_eh1", "mu"),
    Spectrum("esrf_ge_foil", "ESRF_BM08_LISA_2021.dat", _ESRF, "transmission",
             "i1_eh2", "ir_eh2", "mu_ref", ("Ge", "K")),
)  # fmt: skip


def spectrum(name: str) -> Spectrum:
    """Return a spectrum of the corpus by name."""
    return next(item for item in SPECTRA if item.name == name)


def sha256(path: Path) -> str:
    """Return the SHA-256 of a file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_columns(path: Path) -> dict[str, np.ndarray]:
    """Read a column file: XDI ``Column.N`` labels, or the last header line."""
    header = [
        line[1:].strip()
        for line in path.read_text(encoding="latin-1").splitlines()
        if line.startswith("#")
    ]
    xdi = {}
    for line in header:
        match = re.match(r"Column\.(\d+):\s*(\S+)", line)
        if match:
            xdi[int(match.group(1))] = match.group(2)
    data = np.loadtxt(path, comments="#", ndmin=2)
    if len(xdi) == data.shape[1]:
        labels = [xdi[index] for index in sorted(xdi)]
    else:
        labels = header[-1].split()
    if len(labels) != data.shape[1]:
        raise ValueError(f"{path.name}: {len(labels)} labels, {data.shape[1]} columns")
    return {label.lower(): data[:, index] for index, label in enumerate(labels)}
