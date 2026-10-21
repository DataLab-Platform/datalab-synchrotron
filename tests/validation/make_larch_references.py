"""Generate the Larch reference results of the XAS validation corpus.

Run in a Python environment where Larch (``pip install xraylarch``) is installed,
from the repository root::

    python tests/validation/make_larch_references.py

The results are written to ``tests/data/xas/larch_references.json``, so that the
validation tests do not need Larch.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import larch
import numpy as np
from larch import Group
from larch.xafs import find_e0, pre_edge

sys.path.insert(0, str(Path(__file__).parents[1]))

from support.xas_corpus import REFERENCES, SPECTRA  # noqa: E402


def _array(values: np.ndarray) -> list[float]:
    """Return array values as a JSON list with 9 significant digits."""
    return [float(f"{value:.9g}") for value in np.asarray(values, dtype=float)]


def main() -> None:
    """Write Larch's edge energy and normalization of every corpus spectrum."""
    results = {}
    for spectrum in SPECTRA:
        energy, mu = spectrum.energy_and_mu()
        group = Group(energy=energy, mu=mu)
        pre_edge(group)
        details = group.pre_edge_details
        results[spectrum.name] = {
            "find_e0": float(find_e0(energy, mu)),
            "e0": float(group.e0),
            "edge_step": float(group.edge_step),
            "pre_range": [float(details.pre1), float(details.pre2)],
            "post_range": [float(details.norm1), float(details.norm2)],
            "post_degree": int(details.nnorm),
            "energy": _array(group.energy),
            "norm": _array(group.norm),
            "flat": _array(group.flat),
        }
    document = {"larch_version": larch.__version__, "spectra": results}
    text = json.dumps(document, separators=(",", ":"))
    REFERENCES.write_text(text + "\n", encoding="utf-8")
    print(f"Wrote {REFERENCES}")


if __name__ == "__main__":
    main()
