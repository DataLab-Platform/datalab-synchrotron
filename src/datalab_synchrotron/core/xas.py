"""X-ray absorption spectroscopy: absorption, edge energy and edge normalization.

The definitions are the usual XAFS ones, as implemented by Larch, so that results
compare with the reference analysis software of the field:

- absorption in transmission ``mu = ln(I0 / It)``, in fluorescence ``mu = If / I0``
- edge energy ``E0``: point of maximum derivative of ``mu(E)``, refined on the
  derivative smoothed over about one energy step, ignoring isolated glitches
- normalization: a line fitted below the edge (pre-edge) and a polynomial fitted
  above it (post-edge) are extrapolated to ``E0``; their difference is the edge
  step, and ``norm = (mu - pre_edge) / edge_step``. ``flat`` also removes the
  curvature of the post-edge polynomial above ``E0``.

Energies are in eV: :func:`energy_unit` tells how to convert energies given in
another unit, or refuses them.
"""

from __future__ import annotations

import dataclasses
import enum

import numpy as np

__all__ = [
    "MAX_EDGE_KEV",
    "Absorption",
    "AbsorptionMode",
    "EdgeNormalization",
    "EnergyUnit",
    "absorption",
    "edge_energy",
    "energy_unit",
    "normalize_edge",
]

#: Upper bound of X-ray absorption edge energies in keV (uranium K edge: 115.6 keV).
#: Energies of a spectrum in keV are below it; in eV, they are above it, except for
#: soft X-ray edges below 150 eV.
MAX_EDGE_KEV = 150.0

#: Factors converting the supported energy units to eV, by lowercase unit name
_ENERGY_FACTORS = {"ev": 1.0, "kev": 1000.0}


@dataclasses.dataclass(frozen=True)
class EnergyUnit:
    """Conversion of the energies of a spectrum to eV.

    Args:
        factor: factor converting the energies to eV
        note: remark for the user (assumed unit, conversion), if any
        doubtful: True if the note asks the user to check the unit
    """

    factor: float
    note: str = ""
    doubtful: bool = False


def energy_unit(unit: str | None, energy: np.ndarray) -> EnergyUnit:
    """Return how to convert energies to eV, from their unit and their values.

    Energies in eV or keV are accepted (unit name in any case). Without a unit,
    energies are taken as eV if they reach :data:`MAX_EDGE_KEV`, and refused
    otherwise: they are most likely in keV. Energies in keV beyond
    :data:`MAX_EDGE_KEV` are refused: they are most likely in eV.

    Args:
        unit: unit of the energies (empty or None if unknown)
        energy: energies

    Returns:
        Conversion of the energies to eV

    Raises:
        ValueError: with a user-facing message if the energies cannot be converted
    """
    name = (unit or "").strip()
    values = np.asarray(energy, dtype=float)
    values = values[np.isfinite(values)]
    if values.size == 0:
        raise ValueError("No finite energy")
    low, high = float(values.min()), float(values.max())
    if not name:
        if high < MAX_EDGE_KEV:
            raise ValueError(
                f"Energies have no unit, and values up to {high:g} look like keV: "
                "set the X unit to eV or keV"
            )
        return EnergyUnit(1.0, "Energies have no unit: they are taken as eV")
    factor = _ENERGY_FACTORS.get(name.lower())
    if factor is None:
        raise ValueError(
            f"Energies in '{name}' cannot be used: the X unit must be eV or keV"
        )
    if factor != 1.0:
        if low > MAX_EDGE_KEV:
            raise ValueError(
                f"Energies from {low:g} {name} are beyond X-ray absorption edges: "
                "they are most likely in eV, set the X unit to eV"
            )
        return EnergyUnit(factor, f"Energies converted from {name} to eV")
    if high < MAX_EDGE_KEV:
        return EnergyUnit(
            1.0,
            f"Energies up to {high:g} eV are unusually low: check that the X unit "
            "is not keV",
            doubtful=True,
        )
    return EnergyUnit(1.0)


class AbsorptionMode(enum.Enum):
    """Measurement geometry of an absorption spectrum."""

    TRANSMISSION = "transmission"
    FLUORESCENCE = "fluorescence"


@dataclasses.dataclass(frozen=True)
class Absorption:
    """Absorption computed from detector counts.

    Args:
        mu: absorption, NaN at invalid points
        invalid: True where a count is not finite, or not positive where the
         definition requires it
    """

    mu: np.ndarray
    invalid: np.ndarray

    @property
    def invalid_count(self) -> int:
        """Return the number of invalid points."""
        return int(np.count_nonzero(self.invalid))


def absorption(
    i0: np.ndarray, detector: np.ndarray, mode: AbsorptionMode | str
) -> Absorption:
    """Return the absorption computed from incident and detector counts.

    Args:
        i0: incident intensity (monitor) counts
        detector: transmitted intensity (transmission) or fluorescence counts
        mode: measurement geometry

    Returns:
        Absorption, with the invalid points reported instead of being dropped
    """
    mode = AbsorptionMode(mode)
    i0 = np.asarray(i0, dtype=float)
    detector = np.asarray(detector, dtype=float)
    if i0.shape != detector.shape:
        raise ValueError("Monitor and detector counts must have the same length")
    invalid = ~np.isfinite(i0) | ~np.isfinite(detector) | (i0 <= 0.0)
    if mode is AbsorptionMode.TRANSMISSION:
        invalid |= detector <= 0.0
    mu = np.full(i0.shape, np.nan)
    valid = ~invalid
    if mode is AbsorptionMode.TRANSMISSION:
        mu[valid] = np.log(i0[valid] / detector[valid])
    else:
        mu[valid] = detector[valid] / i0[valid]
    return Absorption(mu, invalid)


def _clean(energy: np.ndarray, mu: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Return finite points in increasing energy order, without repeated energies."""
    energy = np.asarray(energy, dtype=float)
    mu = np.asarray(mu, dtype=float)
    if energy.shape != mu.shape or energy.ndim != 1:
        raise ValueError("Energy and absorption must be 1D arrays of the same length")
    keep = np.isfinite(energy) & np.isfinite(mu)
    energy, mu = energy[keep], mu[keep]
    order = np.argsort(energy, kind="stable")
    energy, mu = energy[order], mu[order]
    distinct = np.concatenate(([True], np.diff(energy) > 0.0))
    energy, mu = energy[distinct], mu[distinct]
    if energy.size < 10:
        raise ValueError("An absorption spectrum needs at least 10 distinct energies")
    return energy, mu


def _energy_step(energy: np.ndarray) -> float:
    """Return the typical smallest energy step, ignoring the smallest 1%."""
    steps = np.sort(np.diff(energy))
    skip = int(0.01 * energy.size)
    return float(steps[skip : skip + 10].mean())


def _smooth(energy: np.ndarray, values: np.ndarray, step: float) -> np.ndarray:
    """Return values convolved with a Lorentzian of half-width ``step``.

    The values are resampled on a grid of the given step, aligned on its multiples
    and extended by 5 steps, as by Larch's ``smooth`` (on noisy data, E0 depends
    on these details).
    """
    start = step * int((energy[0] - 5 * step) / step)
    stop = step * int((energy[-1] + 5 * step) / step)
    count = min(1 + int(abs(stop - start + 0.1 * step) / step), 50 * energy.size)
    grid = np.linspace(start, stop, count)
    gridded = np.interp(grid, energy, values)
    kernel = 1.0 / (1.0 + (np.arange(2 * count) - count) ** 2.0)
    padded = np.concatenate((gridded[count:0:-1], gridded, gridded[::-1]))
    smoothed = np.convolve(kernel / kernel.sum(), padded, mode="valid")
    return np.interp(energy, grid, smoothed[:count])


def _steepest_index(energy: np.ndarray, mu: np.ndarray, step: float | None) -> int:
    """Return the index of the steepest rise, ignoring isolated glitches."""
    size = energy.size
    margin = max(3, int(0.02 * size))
    slope = np.gradient(mu) / np.gradient(energy)
    if step is not None:
        slope = _smooth(energy, slope, step)
    slope[~np.isfinite(slope)] = -1.0
    inner = slope[margin:-margin]
    if inner.size == 0:
        return 0
    slope = (slope - inner.min()) / max(1e-10, float(np.ptp(inner)))
    threshold = 0.6 if size > 20 else 0.3
    high = slope > threshold
    for _attempt in range(2):
        if np.count_nonzero(high) > 3:
            break
        threshold *= 0.5
        high = slope > threshold
    if np.count_nonzero(high) < 3:
        high = np.isfinite(slope)
    best, best_slope = 0, 0.0
    for index in np.flatnonzero(high):
        if index < margin or index > size - margin or index + 1 >= size:
            continue
        if slope[index] > best_slope and high[index - 1] and high[index + 1]:
            best, best_slope = int(index), float(slope[index])
    return best


def edge_energy(energy: np.ndarray, mu: np.ndarray) -> float:
    """Return the edge energy E0 of an absorption spectrum.

    Args:
        energy: energies (eV), in any order
        mu: absorption

    Returns:
        Energy of the steepest rise of the absorption, one of the given energies
    """
    energy, mu = _clean(energy, mu)
    size = energy.size
    first = _steepest_index(energy, mu, None)
    estimate = float(energy[first])
    start, stop = max(3, first - 75), min(first + 75, size - 3)
    if first < 0.05 * size:
        # Steepest point at the start of the scan: most likely a glitch
        estimate = float(energy.mean())
        start, stop = max(3, first - 20), size - 3
    step = 0.5 * (
        float(np.clip(_energy_step(energy), 0.01, 1.0))
        + float(np.clip(estimate / 25000.0, 0.01, 1.0))
    )
    refined = _steepest_index(energy[start:stop], mu[start:stop], step)
    if refined < 1:
        return float(energy[start + 2])
    return float(energy[start + refined])


@dataclasses.dataclass(frozen=True)
class EdgeNormalization:
    """Normalization of an absorption spectrum.

    Args:
        energy: energies of the valid points, in increasing order
        mu: absorption at these energies
        e0: edge energy
        edge_step: edge step, difference of post-edge and pre-edge curves at E0
        pre_range: energy range of the pre-edge line fit, relative to E0
        post_range: energy range of the post-edge polynomial fit, relative to E0
        post_degree: degree of the post-edge polynomial
        pre_edge: pre-edge line
        post_edge: post-edge curve (pre-edge line plus polynomial)
        norm: normalized absorption
        flat: normalized absorption, without the post-edge curvature above E0
    """

    energy: np.ndarray
    mu: np.ndarray
    e0: float
    edge_step: float
    pre_range: tuple[float, float]
    post_range: tuple[float, float]
    post_degree: int
    pre_edge: np.ndarray
    post_edge: np.ndarray
    norm: np.ndarray
    flat: np.ndarray


def _index_below(values: np.ndarray, value: float) -> int:
    """Return the index of the last value not above ``value`` (0 if none)."""
    below = np.flatnonzero(values <= value)
    return int(below[-1]) if below.size else 0


def _index_nearest(values: np.ndarray, value: float) -> int:
    """Return the index of the value nearest to ``value``."""
    return int(np.argmin(np.abs(values - value)))


def _polynomial(energy: np.ndarray, values: np.ndarray, degree: int):
    """Return the least-squares polynomial of values versus energy."""
    return np.polynomial.Polynomial.fit(energy, values, degree)


def normalize_edge(
    energy: np.ndarray,
    mu: np.ndarray,
    e0: float | None = None,
    pre_range: tuple[float, float] | None = None,
    post_range: tuple[float, float] | None = None,
    post_degree: int | None = None,
) -> EdgeNormalization:
    """Normalize an absorption spectrum to a unit edge step.

    Ranges are relative to E0. Default ranges and degree:

    - pre-edge: from the second energy of the scan (rounded to 5 eV) to half that
    - post-edge: from 1/15 of the range above E0 (at most 25 eV, rounded to 5 eV)
      to the end of the scan (rounded to 5 eV, without going beyond it)
    - post-edge degree: 2 for a fitted range of 300 eV or more, 1 for 30 eV or
      more, 0 below

    Args:
        energy: energies (eV), in any order
        mu: absorption
        e0: edge energy (default: :func:`edge_energy`)
        pre_range: pre-edge fit range, relative to E0
        post_range: post-edge fit range, relative to E0
        post_degree: degree of the post-edge polynomial, from 0 to 5

    Returns:
        Normalization of the finite points of the spectrum
    """
    energy, mu = _clean(energy, mu)
    if e0 is None or not energy[1] <= e0 <= energy[-2]:
        e0 = edge_energy(energy, mu)
    size = energy.size
    ie0 = _index_nearest(energy, e0)
    relative = energy - e0

    if pre_range is None:
        unit = 5.0 if ie0 > 20 else 2.0
        pre1 = max(unit * round((energy[1] - e0) / unit), energy[0] - e0)
        pre_range = (pre1, 0.5 * pre1)
    pre1, pre2 = sorted(float(value) for value in pre_range)
    constant = _index_below(relative, pre2) - _index_below(relative, pre1) < 3
    first, last = _index_below(relative, pre1), _index_nearest(relative, pre2)
    if constant:
        last = last + 1 if last == first else last
        pre_edge = np.full(size, mu[first:last].mean())
    else:
        last = max(last, min(size, first + 2))
        pre_edge = _polynomial(energy[first:last], mu[first:last], 1)(energy)

    if post_range is None:
        norm2 = min(5.0 * round((energy[-1] - e0) / 5.0), energy[-1] - e0)
        norm1 = min(25.0, 5.0 * round(norm2 / 15.0))
        post_range = (min(norm1, norm2 - 2.0), norm2)
    norm1, norm2 = sorted(float(value) for value in post_range)
    if post_degree is None:
        span = norm2 - norm1
        post_degree = 2 if span >= 300 else 1 if span >= 30 else 0
    post_degree = int(np.clip(post_degree, 0, 5))
    first = min(_index_below(relative, norm1), size - 3)
    last = _index_nearest(relative, norm2)
    if last - first < 2:
        first, post_degree = first - 2, 0
    elif last - first < 5:
        post_degree = min(1, post_degree)
    residue = (mu - pre_edge)[first:last]
    post_edge = pre_edge + _polynomial(energy[first:last], residue, post_degree)(energy)

    edge_step = max(1e-12, abs(float(post_edge[ie0] - pre_edge[ie0])))
    norm = (mu - pre_edge) / edge_step
    curvature = (post_edge - pre_edge) / edge_step
    flat = norm - curvature + curvature[ie0]
    flat[:ie0] = norm[:ie0]
    return EdgeNormalization(
        energy=energy,
        mu=mu,
        e0=float(e0),
        edge_step=edge_step,
        pre_range=(pre1, pre2),
        post_range=(norm1, norm2),
        post_degree=post_degree,
        pre_edge=pre_edge,
        post_edge=post_edge,
        norm=norm,
        flat=flat,
    )
