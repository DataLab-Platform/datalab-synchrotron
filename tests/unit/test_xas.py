"""XAS analysis on synthetic spectra with known edge energy and step."""

from __future__ import annotations

import numpy as np
import pytest

from datalab_synchrotron.core.xas import (
    MAX_EDGE_KEV,
    AbsorptionMode,
    absorption,
    edge_energy,
    energy_unit,
    normalize_edge,
)

E0, STEP = 8979.0, 2.5


def _spectrum(noise: float = 0.0) -> tuple[np.ndarray, np.ndarray]:
    """Return a K-edge-like spectrum: sloped background, arctangent edge of known
    step, slowly decreasing post-edge."""
    energy = np.concatenate(
        (
            np.arange(8779.0, 8959.0, 5.0),
            np.arange(8959.0, 9009.0, 0.5),
            np.arange(9009.0, 9600.0, 3.0),
        )
    )
    background = 0.4 - 2e-4 * (energy - E0)
    edge = STEP * (0.5 + np.arctan((energy - E0) / 0.8) / np.pi)
    decay = 1.0 - 1e-4 * np.clip(energy - E0, 0.0, None)
    mu = background + edge * decay
    if noise:
        mu = mu + np.random.default_rng(1).normal(scale=noise, size=energy.size)
    return energy, mu


def test_transmission_reports_invalid_counts() -> None:
    """Points without counts are reported and left as NaN, not dropped."""
    i0 = np.array([100.0, 0.0, 100.0, np.nan, 100.0])
    it = np.array([50.0, 50.0, -1.0, 50.0, 100.0])
    result = absorption(i0, it, "transmission")
    np.testing.assert_array_equal(result.invalid, [False, True, True, True, False])
    assert result.invalid_count == 3
    np.testing.assert_allclose(result.mu[[0, 4]], [np.log(2.0), 0.0])
    assert np.isnan(result.mu[1:4]).all()


def test_fluorescence_accepts_zero_counts() -> None:
    """Zero fluorescence counts are valid; a zero monitor is not."""
    result = absorption([10.0, 0.0, 10.0], [0.0, 3.0, 5.0], AbsorptionMode.FLUORESCENCE)
    np.testing.assert_array_equal(result.invalid, [False, True, False])
    np.testing.assert_allclose(result.mu[[0, 2]], [0.0, 0.5])


def test_absorption_rejects_mismatched_counts() -> None:
    """Monitor and detector counts must pair point by point."""
    with pytest.raises(ValueError, match="same length"):
        absorption([1.0, 2.0], [1.0], "transmission")
    with pytest.raises(ValueError):
        absorption([1.0], [1.0], "reflection")


def test_edge_energy() -> None:
    """E0 is found at the steepest point, whatever the point order and noise."""
    energy, mu = _spectrum()
    assert edge_energy(energy, mu) == pytest.approx(E0, abs=0.5)
    order = np.random.default_rng(0).permutation(energy.size)
    assert edge_energy(energy[order], mu[order]) == edge_energy(energy, mu)
    noisy_energy, noisy = _spectrum(noise=0.01)
    assert edge_energy(noisy_energy, noisy) == pytest.approx(E0, abs=1.0)


def test_edge_energy_ignores_glitch() -> None:
    """A monochromator glitch at the start of the scan is not taken for the edge."""
    energy, mu = _spectrum()
    mu[1] += 20.0
    assert edge_energy(energy, mu) == pytest.approx(E0, abs=0.5)


def test_normalize_edge() -> None:
    """The edge step is recovered; norm is 0 below the edge, 1 above it once
    flattened, and the given ranges and degree are used."""
    energy, mu = _spectrum()
    result = normalize_edge(energy, mu, e0=E0, pre_range=(-150, -30),
                            post_range=(50, 600), post_degree=1)  # fmt: skip
    assert result.edge_step == pytest.approx(STEP, rel=0.01)
    assert (result.pre_range, result.post_range) == ((-150, -30), (50, 600))
    assert result.post_degree == 1
    below = result.energy < E0 - 30
    np.testing.assert_allclose(result.norm[below], 0.0, atol=0.01)
    above = result.energy > E0 + 50
    np.testing.assert_allclose(result.flat[above], 1.0, atol=0.01)


def test_normalize_edge_defaults() -> None:
    """Default ranges cover the scan and drop non-finite points."""
    energy, mu = _spectrum()
    mu[5] = np.nan
    result = normalize_edge(energy, mu)
    assert result.energy.size == energy.size - 1
    assert result.e0 == edge_energy(energy, mu)
    # Second energy 8784 eV, rounded to 5 eV below E0; scan end at 9597 eV
    assert result.pre_range == (-195.0, -97.5)
    assert result.post_range == (25.0, 618.0)
    assert result.post_degree == 2


def test_normalize_edge_needs_points() -> None:
    """Too short spectra are refused."""
    with pytest.raises(ValueError, match="at least 10"):
        normalize_edge(np.arange(5.0), np.arange(5.0))


def test_energy_unit_converts_kev() -> None:
    """Energies in eV are used as they are, energies in keV are converted."""
    energy = _spectrum()[0]
    unit = energy_unit("eV", energy)
    assert (unit.factor, unit.note, unit.doubtful) == (1.0, "", False)
    for name in ("keV", " KEV "):
        unit = energy_unit(name, energy / 1000.0)
        assert unit.factor == 1000.0 and not unit.doubtful
        assert "converted" in unit.note


def test_energy_unit_without_unit() -> None:
    """Energies without unit are taken as eV, unless they look like keV."""
    energy = _spectrum()[0]
    unit = energy_unit("", energy)
    assert unit.factor == 1.0 and "taken as eV" in unit.note
    assert energy_unit(None, energy).factor == 1.0
    with pytest.raises(ValueError, match="look like keV"):
        energy_unit("", energy / 1000.0)


def test_energy_unit_refuses_contradictions() -> None:
    """Unknown units, and keV values beyond absorption edges, are refused."""
    energy = _spectrum()[0]
    with pytest.raises(ValueError, match="must be eV or keV"):
        energy_unit("deg", energy)
    with pytest.raises(ValueError, match="most likely in eV"):
        energy_unit("keV", energy)
    with pytest.raises(ValueError, match="No finite energy"):
        energy_unit("eV", [np.nan, np.inf])


def test_energy_unit_low_ev_is_doubtful() -> None:
    """Energies in eV below the keV range bound are kept, with a doubt raised."""
    unit = energy_unit("eV", np.linspace(50.0, MAX_EDGE_KEV - 1.0, 20))
    assert unit.factor == 1.0 and unit.doubtful and "keV" in unit.note


def test_normalize_edge_same_in_kev() -> None:
    """Energies converted from keV give the normalization of energies in eV."""
    energy, mu = _spectrum(noise=0.01)
    reference = normalize_edge(energy, mu)
    unit = energy_unit("keV", energy / 1000.0)
    result = normalize_edge(energy / 1000.0 * unit.factor, mu)
    assert result.e0 == pytest.approx(reference.e0, abs=1e-6)
    assert result.edge_step == pytest.approx(reference.edge_step, rel=1e-9)
    assert result.pre_range == pytest.approx(reference.pre_range, abs=1e-6)
    assert result.post_range == pytest.approx(reference.post_range, abs=1e-6)
    assert result.post_degree == reference.post_degree
    np.testing.assert_allclose(result.norm, reference.norm, atol=1e-9)
