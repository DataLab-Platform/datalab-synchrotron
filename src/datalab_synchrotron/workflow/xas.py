"""X-ray absorption recipes: absorption from counters, edge normalization."""

from __future__ import annotations

import re

import guidata.dataset as gds
import numpy as np
from datalab.plugins.recipes import (
    RecipeCardinality,
    RecipeDescriptor,
    RecipeDiagnostic,
    RecipeDiagnosticLevel,
    RecipeExecutionContext,
    RecipeInputs,
    RecipeInputSlot,
    RecipeObjectOutput,
    RecipeObjectType,
    RecipeOutcome,
    RecipeResultOutput,
    RecipeValidationError,
)
from sigima.objects import NO_ROI, SignalObj, TableResult, create_signal

from .. import PLUGIN_ID, __version__
from ..core import AbsorptionMode, absorption, normalize_edge

#: Number of invalid point energies listed in diagnostics
MAX_LISTED_POINTS = 20

_MONITOR_NAME = re.compile(r"^(i0|io|mon(itor)?)(?![a-z])", re.IGNORECASE)


class AbsorptionParameters(gds.DataSet):
    """Absorption from counters"""

    mode = gds.ChoiceItem(
        "Measurement",
        [
            (AbsorptionMode.TRANSMISSION.value, "Transmission: ln(I0 / It)"),
            (AbsorptionMode.FLUORESCENCE.value, "Fluorescence: If / I0"),
        ],
        default=AbsorptionMode.TRANSMISSION.value,
    )


class EdgeNormalizationParameters(gds.DataSet):
    """Edge normalization"""

    _auto_e0 = gds.GetAttrProp("automatic_e0")
    _auto_ranges = gds.GetAttrProp("automatic_ranges")

    _e0 = gds.BeginGroup("Edge energy")
    automatic_e0 = gds.BoolItem(
        "Steepest point of the spectrum", default=True
    ).set_prop("display", store=_auto_e0)
    e0 = gds.FloatItem("E0", default=0.0, unit="eV").set_prop(
        "display", active=gds.NotProp(_auto_e0)
    )
    _e0e = gds.EndGroup("Edge energy")
    _ranges = gds.BeginGroup("Fit ranges, relative to E0")
    automatic_ranges = gds.BoolItem("Automatic ranges", default=True).set_prop(
        "display", store=_auto_ranges
    )
    pre1 = gds.FloatItem("Pre-edge from", default=-150.0, unit="eV").set_prop(
        "display", active=gds.NotProp(_auto_ranges)
    )
    pre2 = gds.FloatItem("Pre-edge to", default=-30.0, unit="eV").set_prop(
        "display", active=gds.NotProp(_auto_ranges)
    )
    post1 = gds.FloatItem("Post-edge from", default=50.0, unit="eV").set_prop(
        "display", active=gds.NotProp(_auto_ranges)
    )
    post2 = gds.FloatItem("Post-edge to", default=600.0, unit="eV").set_prop(
        "display", active=gds.NotProp(_auto_ranges)
    )
    post_degree = gds.ChoiceItem(
        "Post-edge polynomial degree",
        [(-1, "Automatic"), (0, "0"), (1, "1"), (2, "2"), (3, "3")],
        default=-1,
    )
    _rangese = gds.EndGroup("Fit ranges, relative to E0")


def _column_name(signal: SignalObj) -> str:
    """Return the counter name of a signal: source column, label or title."""
    source = signal.metadata.get("experimental_source") or {}
    selection = source.get("selection") or {}
    for key in ("y", "signal", "column"):
        value = selection.get(key)
        if isinstance(value, str) and value:
            return value.rsplit("/", 1)[-1]
    return signal.ylabel or signal.title or ""


def suggest_absorption_bindings(
    candidates: tuple[SignalObj, ...],
) -> dict[str, tuple[SignalObj, ...]]:
    """Propose the monitor among two signals, from its name (I0, monitor...)."""
    if len(candidates) != 2:
        return {}
    monitors = [obj for obj in candidates if _MONITOR_NAME.match(_column_name(obj))]
    if len(monitors) != 1:
        return {}
    (monitor,) = monitors
    detector = next(obj for obj in candidates if obj is not monitor)
    return {"monitor": (monitor,), "detector": (detector,)}


def check_absorption_inputs(
    inputs: RecipeInputs, _parameters: gds.DataSet | None
) -> list[RecipeDiagnostic]:
    """Monitor and detector counts must be recorded at the same energies."""
    (monitor,), (detector,) = inputs["monitor"], inputs["detector"]
    if monitor.x.size != detector.x.size or not np.allclose(
        monitor.x, detector.x, rtol=1e-9, atol=0.0, equal_nan=True
    ):
        return [
            RecipeDiagnostic(
                RecipeDiagnosticLevel.ERROR,
                "energies-differ",
                "Monitor and detector counts must be recorded at the same energies "
                "(same scan)",
            )
        ]
    return []


def _listed(energies: np.ndarray) -> str:
    """Return a short list of energies."""
    text = ", ".join(f"{value:g}" for value in energies[:MAX_LISTED_POINTS])
    return text + (", ..." if energies.size > MAX_LISTED_POINTS else "")


def run_absorption(
    inputs: RecipeInputs,
    parameters: gds.DataSet | None,
    context: RecipeExecutionContext,
) -> RecipeOutcome:
    """Compute the absorption from monitor and detector counts."""
    if not isinstance(parameters, AbsorptionParameters):
        raise RecipeValidationError("Absorption requires AbsorptionParameters")
    for diagnostic in check_absorption_inputs(inputs, parameters):
        raise RecipeValidationError(diagnostic.message)
    context.raise_if_cancelled()
    (monitor,), (detector,) = inputs["monitor"], inputs["detector"]
    mode = AbsorptionMode(parameters.mode)
    result = absorption(monitor.y, detector.y, mode)
    valid = ~result.invalid
    if np.count_nonzero(valid) < 2:
        raise RecipeValidationError("Less than 2 points have valid counts")
    formula = "ln(I0/It)" if mode is AbsorptionMode.TRANSMISSION else "If/I0"
    output = create_signal(
        f"mu = {formula} ({detector.title})",
        monitor.x[valid],
        result.mu[valid],
        units=(monitor.xunit or "", ""),
        labels=(monitor.xlabel or "Energy", "mu"),
    )
    diagnostics = []
    if result.invalid_count:
        energies = monitor.x[result.invalid]
        diagnostics.append(
            RecipeDiagnostic(
                RecipeDiagnosticLevel.WARNING,
                "invalid-counts",
                f"{result.invalid_count} points without valid counts were left "
                f"out: {_listed(energies)}",
                {"energies": [float(value) for value in energies]},
            )
        )
    return RecipeOutcome(
        objects=(RecipeObjectOutput("mu", output),), diagnostics=diagnostics
    )


def check_normalization_inputs(
    inputs: RecipeInputs, _parameters: gds.DataSet | None
) -> list[RecipeDiagnostic]:
    """Energies are expected in eV."""
    units = {signal.xunit for signal in inputs["spectra"] if signal.xunit}
    other = sorted(unit for unit in units if unit != "eV")
    if not other:
        return []
    return [
        RecipeDiagnostic(
            RecipeDiagnosticLevel.WARNING,
            "energy-unit",
            f"Energies are read in eV, but some spectra are in {', '.join(other)}: "
            "default ranges assume eV",
        )
    ]


def _table(signal: SignalObj, result) -> TableResult:
    """Return the normalization results of one spectrum."""
    rows = [
        ["E0", result.e0, "eV"],
        ["Edge step", result.edge_step, ""],
        ["Pre-edge range start", result.pre_range[0], "eV"],
        ["Pre-edge range end", result.pre_range[1], "eV"],
        ["Post-edge range start", result.post_range[0], "eV"],
        ["Post-edge range end", result.post_range[1], "eV"],
        ["Post-edge polynomial degree", result.post_degree, ""],
    ]
    return TableResult(
        title=f"Edge normalization ({signal.title})",
        kind="xas_edge_normalization",
        headers=["Quantity", "Value", "Unit"],
        data=rows,
        roi_indices=[NO_ROI] * len(rows),
    )


def run_normalization(
    inputs: RecipeInputs,
    parameters: gds.DataSet | None,
    context: RecipeExecutionContext,
) -> RecipeOutcome:
    """Normalize each absorption spectrum to a unit edge step."""
    if not isinstance(parameters, EdgeNormalizationParameters):
        raise RecipeValidationError(
            "Edge normalization requires EdgeNormalizationParameters"
        )
    automatic = bool(parameters.automatic_ranges)
    degree = int(parameters.post_degree)
    spectra = inputs["spectra"]
    objects, results, diagnostics = [], [], []
    for index, signal in enumerate(spectra, start=1):
        context.raise_if_cancelled()
        context.report_progress((index - 1) / len(spectra), signal.title)
        try:
            result = normalize_edge(
                signal.x,
                signal.y,
                e0=None if parameters.automatic_e0 else float(parameters.e0),
                pre_range=None if automatic else (parameters.pre1, parameters.pre2),
                post_range=None if automatic else (parameters.post1, parameters.post2),
                post_degree=None if degree < 0 else degree,
            )
        except ValueError as error:
            raise RecipeValidationError(f"{signal.title}: {error}") from error
        dropped = signal.x.size - result.energy.size
        if dropped:
            diagnostics.append(
                RecipeDiagnostic(
                    RecipeDiagnosticLevel.INFO,
                    f"dropped-points-{index}",
                    f"{signal.title}: {dropped} points with a non-finite or "
                    "repeated energy, or a non-finite value, were left out",
                )
            )
        labels = (signal.xlabel or "Energy", "Normalized mu")
        units = (signal.xunit or "eV", "")
        for name, values in (("norm", result.norm), ("flat", result.flat)):
            output = create_signal(
                f"{name}({signal.title})",
                result.energy,
                values,
                units=units,
                labels=labels,
            )
            objects.append(RecipeObjectOutput(f"{name}-{index}", output))
        results.append(
            RecipeResultOutput(f"edge-{index}", _table(signal, result), f"norm-{index}")
        )
    context.report_progress(1.0, "Edge normalization complete")
    return RecipeOutcome(objects=objects, results=results, diagnostics=diagnostics)


ABSORPTION_RECIPE = RecipeDescriptor(
    recipe_id=f"{PLUGIN_ID}:xas-absorption",
    plugin_version=__version__,
    title="Absorption from counters",
    version="1.0.0",
    description=(
        "Compute the X-ray absorption mu(E) of a scan from its monitor and detector "
        "counts, in transmission or fluorescence. Points without valid counts are "
        "left out and listed."
    ),
    inputs=(
        RecipeInputSlot(
            "monitor",
            RecipeObjectType.SIGNAL,
            RecipeCardinality.ONE,
            title="Monitor (I0)",
            description="Incident intensity counts versus energy.",
        ),
        RecipeInputSlot(
            "detector",
            RecipeObjectType.SIGNAL,
            RecipeCardinality.ONE,
            title="Detector (It or If)",
            description="Transmitted or fluorescence counts, from the same scan.",
        ),
    ),
    parameter_class=AbsorptionParameters,
    run=run_absorption,
    suggest_bindings=suggest_absorption_bindings,
    check_inputs=check_absorption_inputs,
)

NORMALIZATION_RECIPE = RecipeDescriptor(
    recipe_id=f"{PLUGIN_ID}:xas-normalization",
    plugin_version=__version__,
    title="Edge normalization",
    version="1.0.0",
    description=(
        "Find the edge energy E0 of absorption spectra and normalize them to a unit "
        "edge step, with a pre-edge line and a post-edge polynomial, as Larch and "
        "Athena do. The flattened spectrum also removes the post-edge curvature."
    ),
    inputs=(
        RecipeInputSlot(
            "spectra",
            RecipeObjectType.SIGNAL,
            RecipeCardinality.MANY,
            title="Absorption spectra",
            description="mu(E) versus energy in eV, each normalized separately.",
        ),
    ),
    parameter_class=EdgeNormalizationParameters,
    run=run_normalization,
    check_inputs=check_normalization_inputs,
)

RECIPES = (ABSORPTION_RECIPE, NORMALIZATION_RECIPE)

__all__ = [
    "ABSORPTION_RECIPE",
    "NORMALIZATION_RECIPE",
    "RECIPES",
    "AbsorptionParameters",
    "EdgeNormalizationParameters",
]
