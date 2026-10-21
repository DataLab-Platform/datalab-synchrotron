"""XAS analysis on measured spectra, compared with Larch and tabulated edges.

The corpus (``tests/data/xas``) gathers reference foils and samples measured in
transmission and fluorescence on several beamlines. Larch's results are frozen in
``larch_references.json`` (see ``make_larch_references.py``).
"""

from __future__ import annotations

import json

import numpy as np
import pytest
from support.xas_corpus import REFERENCES, SPECTRA, TABULATED_EDGES, Spectrum, sha256

from datalab_synchrotron.core.xas import absorption, edge_energy, normalize_edge

LARCH = json.loads(REFERENCES.read_text(encoding="utf-8"))["spectra"]
FOILS = [item for item in SPECTRA if item.foil is not None]
FROM_COUNTS = [item for item in SPECTRA if item.mode and item.mu]


def _ids(spectra: list[Spectrum]) -> list[str]:
    """Return test ids of spectra."""
    return [item.name for item in spectra]


@pytest.mark.parametrize("item", SPECTRA, ids=_ids(SPECTRA))
def test_corpus_is_unchanged(item: Spectrum) -> None:
    """Corpus files are the published ones (no line ending conversion)."""
    assert sha256(item.path) == item.sha256


@pytest.mark.parametrize("item", FROM_COUNTS, ids=_ids(FROM_COUNTS))
def test_absorption_matches_file(item: Spectrum) -> None:
    """Absorption from counts matches the column written by the beamline or Larch,
    to the precision of the written values."""
    columns = item.columns()
    result = absorption(columns[item.monitor], columns[item.detector], item.mode)
    assert result.invalid_count == 0
    np.testing.assert_allclose(result.mu, columns[item.mu], rtol=2e-5, atol=1e-7)


@pytest.mark.parametrize("item", SPECTRA, ids=_ids(SPECTRA))
def test_edge_energy_matches_larch(item: Spectrum) -> None:
    """E0 is Larch's, including on a dilute sample with a 7e-4 edge step."""
    energy, mu = item.energy_and_mu()
    assert edge_energy(energy, mu) == pytest.approx(LARCH[item.name]["find_e0"])


@pytest.mark.parametrize("item", SPECTRA, ids=_ids(SPECTRA))
def test_normalization_matches_larch(item: Spectrum) -> None:
    """Default ranges, edge step, normalized and flattened spectra are Larch's."""
    reference = LARCH[item.name]
    energy, mu = item.energy_and_mu()
    result = normalize_edge(energy, mu)
    assert result.e0 == pytest.approx(reference["e0"])
    assert result.pre_range == pytest.approx(reference["pre_range"])
    assert result.post_range == pytest.approx(reference["post_range"])
    assert result.post_degree == reference["post_degree"]
    assert result.edge_step == pytest.approx(reference["edge_step"], rel=1e-7)
    np.testing.assert_allclose(result.energy, reference["energy"], atol=1e-4)
    np.testing.assert_allclose(result.norm, reference["norm"], atol=1e-6)
    np.testing.assert_allclose(result.flat, reference["flat"], atol=1e-6)


@pytest.mark.parametrize("item", FOILS, ids=_ids(FOILS))
def test_foil_edge_energy_is_tabulated(item: Spectrum) -> None:
    """E0 of reference foils is within the monochromator calibration (3 eV) of the
    tabulated edge energy."""
    energy, mu = item.energy_and_mu()
    assert abs(edge_energy(energy, mu) - TABULATED_EDGES[item.foil]) <= 3.0
