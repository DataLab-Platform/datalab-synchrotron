"""X-ray absorption recipes on measured spectra, headless and in DataLab."""

from __future__ import annotations

import json

import numpy as np
import pytest
from datalab.env import execenv
from datalab.gui.plugins.recipe_runner import RecipeRunner
from datalab.plugins.recipes import (
    RecipeDiagnosticLevel,
    RecipeExecutionContext,
    RecipeValidationError,
)
from datalab.tests import datalab_test_app_context
from sigima.objects import (
    SignalObj,
    create_signal,
    make_experimental_source,
    set_experimental_source,
)
from support.xas_corpus import REFERENCES, spectrum

from datalab_synchrotron.adapters.desktop import SynchrotronPlugin
from datalab_synchrotron.workflow import (
    ABSORPTION_RECIPE,
    CU_FOIL_EXAMPLE,
    NORMALIZATION_RECIPE,
    AbsorptionParameters,
    EdgeNormalizationParameters,
)

LARCH = json.loads(REFERENCES.read_text(encoding="utf-8"))["spectra"]


def _counter(name: str, energy: np.ndarray, counts: np.ndarray) -> SignalObj:
    """Return a counter signal as imported from a scan."""
    signal = create_signal(f"{name} (scan 1.1)", energy, counts, labels=("E", name))
    source = make_experimental_source(
        "spec", "scan.dat", entry="1.1", selection={"x": "E", "y": name}
    )
    set_experimental_source(signal, source)
    return signal


def _esrf_counters() -> tuple[SignalObj, SignalObj, np.ndarray]:
    """Return monitor and transmission counters of the ESRF scan, and its mu."""
    columns = spectrum("esrf_sample").columns()
    energy = columns["ebraggenergy"]
    monitor = _counter("I0_EH1", energy, columns["i0_eh1"])
    detector = _counter("I1_EH1", energy, columns["i1_eh1"])
    return monitor, detector, columns["mu"]


def _spectrum(name: str) -> SignalObj:
    """Return a corpus spectrum as a signal in eV."""
    energy, mu = spectrum(name).energy_and_mu()
    return create_signal(name, energy, mu, units=("eV", ""), labels=("Energy", "mu"))


def test_absorption_from_counters() -> None:
    """The monitor is recognized by its name and mu is the beamline's."""
    monitor, detector, expected = _esrf_counters()
    bindings = ABSORPTION_RECIPE.suggest_bindings((detector, monitor))
    assert bindings == {"monitor": (monitor,), "detector": (detector,)}
    outcome = ABSORPTION_RECIPE.run(
        bindings, AbsorptionParameters(), RecipeExecutionContext()
    )
    (output,) = outcome.objects
    np.testing.assert_allclose(output.value.y, expected, rtol=1e-13, atol=1e-15)
    np.testing.assert_array_equal(output.value.x, monitor.x)
    assert not outcome.diagnostics


def test_absorption_reports_invalid_counts() -> None:
    """Points without counts are left out of mu and listed."""
    monitor, detector, expected = _esrf_counters()
    monitor.y[[3, 50]] = 0.0
    outcome = ABSORPTION_RECIPE.run(
        {"monitor": (monitor,), "detector": (detector,)},
        AbsorptionParameters(),
        RecipeExecutionContext(),
    )
    (output,) = outcome.objects
    assert output.value.y.size == expected.size - 2
    (diagnostic,) = outcome.diagnostics
    assert diagnostic.level is RecipeDiagnosticLevel.WARNING
    assert diagnostic.details["energies"] == [monitor.x[3], monitor.x[50]]


def test_absorption_needs_same_scan() -> None:
    """Counters of different scans are refused before running."""
    monitor, detector, _expected = _esrf_counters()
    detector.x = detector.x + 1.0
    inputs = {"monitor": (monitor,), "detector": (detector,)}
    (diagnostic,) = ABSORPTION_RECIPE.check_inputs(inputs, None)
    assert diagnostic.level is RecipeDiagnosticLevel.ERROR
    with pytest.raises(RecipeValidationError, match="same energies"):
        ABSORPTION_RECIPE.run(inputs, AbsorptionParameters(), RecipeExecutionContext())


def test_fluorescence_absorption() -> None:
    """Fluorescence mu is If / I0, as written in the file."""
    columns = spectrum("cu_glass_fluorescence").columns()
    energy = columns["energy"]
    outcome = ABSORPTION_RECIPE.run(
        {
            "monitor": (_counter("i0", energy, columns["i0"]),),
            "detector": (_counter("ifluor", energy, columns["ifluor"]),),
        },
        AbsorptionParameters.create(mode="fluorescence"),
        RecipeExecutionContext(),
    )
    np.testing.assert_allclose(
        outcome.objects[0].value.y, columns["mufluor"], rtol=2e-5
    )


def test_edge_normalization_matches_larch() -> None:
    """Each spectrum is normalized as by Larch, with its results table."""
    names = ("cu_foil", "esrf_sample")
    outcome = NORMALIZATION_RECIPE.run(
        {"spectra": tuple(_spectrum(name) for name in names)},
        EdgeNormalizationParameters(),
        RecipeExecutionContext(),
    )
    assert [output.id for output in outcome.objects] == [
        "norm-1",
        "flat-1",
        "norm-2",
        "flat-2",
    ]
    for index, name in enumerate(names, start=1):
        objects = {output.id: output.value for output in outcome.objects}
        np.testing.assert_allclose(
            objects[f"norm-{index}"].y, LARCH[name]["norm"], atol=1e-6
        )
        np.testing.assert_allclose(
            objects[f"flat-{index}"].y, LARCH[name]["flat"], atol=1e-6
        )
        table = outcome.results[index - 1]
        assert table.anchor_id == f"norm-{index}"
        values = {row[0]: row[1] for row in table.value.data}
        assert values["E0"] == pytest.approx(LARCH[name]["e0"])
        assert values["Edge step"] == pytest.approx(LARCH[name]["edge_step"])


def test_edge_normalization_parameters() -> None:
    """Given E0, ranges and degree are used instead of the automatic ones."""
    parameters = EdgeNormalizationParameters.create(
        automatic_e0=False,
        e0=8979.0,
        automatic_ranges=False,
        pre1=-150.0,
        pre2=-30.0,
        post1=50.0,
        post2=600.0,
        post_degree=1,
    )
    outcome = NORMALIZATION_RECIPE.run(
        {"spectra": (_spectrum("cu_foil"),)}, parameters, RecipeExecutionContext()
    )
    values = {row[0]: row[1] for row in outcome.results[0].value.data}
    assert values["E0"] == 8979.0
    assert (values["Pre-edge range start"], values["Post-edge range end"]) == (
        -150.0,
        600.0,
    )
    assert values["Post-edge polynomial degree"] == 1


def _normalize(*spectra: SignalObj):
    """Return the outcome of the edge normalization of spectra, with defaults."""
    return NORMALIZATION_RECIPE.run(
        {"spectra": spectra}, EdgeNormalizationParameters(), RecipeExecutionContext()
    )


def _table_values(outcome, index: int = 0) -> dict[str, float]:
    """Return the results table of a normalization outcome as a dictionary."""
    return {row[0]: row[1] for row in outcome.results[index].value.data}


def test_edge_normalization_converts_kev() -> None:
    """A spectrum in keV gives the results of the same spectrum in eV, in eV."""
    reference = _normalize(_spectrum("cu_foil"))
    signal = _spectrum("cu_foil")
    signal.x = signal.x / 1000.0
    signal.xunit = "keV"
    (diagnostic,) = NORMALIZATION_RECIPE.check_inputs({"spectra": (signal,)}, None)
    assert diagnostic.level is RecipeDiagnosticLevel.INFO
    outcome = _normalize(signal)
    expected, values = _table_values(reference), _table_values(outcome)
    assert values.keys() == expected.keys()
    for name, value in expected.items():
        assert values[name] == pytest.approx(value, rel=1e-9, abs=1e-6), name
    for output, expected_output in zip(outcome.objects, reference.objects):
        assert output.value.xunit == "eV"
        np.testing.assert_allclose(output.value.x, expected_output.value.x, rtol=1e-12)
        np.testing.assert_allclose(output.value.y, expected_output.value.y, atol=1e-9)
    assert "energy-unit-1" in {d.code for d in outcome.diagnostics}


def test_edge_normalization_without_unit() -> None:
    """Energies without unit are taken as eV, or refused if they look like keV."""
    signal = _spectrum("cu_foil")
    signal.xunit = ""
    (diagnostic,) = NORMALIZATION_RECIPE.check_inputs({"spectra": (signal,)}, None)
    assert diagnostic.level is RecipeDiagnosticLevel.INFO
    assert _table_values(_normalize(signal)) == _table_values(
        _normalize(_spectrum("cu_foil"))
    )
    signal.x = signal.x / 1000.0
    (diagnostic,) = NORMALIZATION_RECIPE.check_inputs({"spectra": (signal,)}, None)
    assert diagnostic.level is RecipeDiagnosticLevel.ERROR
    with pytest.raises(RecipeValidationError, match="look like keV"):
        _normalize(signal)


@pytest.mark.parametrize(
    ("unit", "match"), [("keV", "most likely in eV"), ("deg", "must be eV or keV")]
)
def test_edge_normalization_refuses_energy_unit(unit: str, match: str) -> None:
    """Energies in an unknown unit, or contradicting their unit, are refused
    before running: here, energies in eV labelled keV, or labelled in degrees."""
    signal = _spectrum("cu_foil")
    signal.xunit = unit
    other = _spectrum("esrf_sample")
    diagnostics = NORMALIZATION_RECIPE.check_inputs({"spectra": (other, signal)}, None)
    (diagnostic,) = diagnostics
    assert diagnostic.level is RecipeDiagnosticLevel.ERROR
    assert diagnostic.code == "energy-unit-2"
    assert diagnostic.message.startswith("cu_foil: ")
    with pytest.raises(RecipeValidationError, match=match):
        _normalize(other, signal)


def test_copper_foil_example() -> None:
    """The example gives the expected E0 and edge step through both recipes."""
    data = SynchrotronPlugin.materialize_example(CU_FOIL_EXAMPLE.id)
    assert [obj.title for obj in data.objects] == [
        "i0 (cu_metal_rt.xdi)",
        "itrans (cu_metal_rt.xdi)",
    ]
    bindings = ABSORPTION_RECIPE.suggest_bindings(tuple(reversed(data.objects)))
    parameters = AbsorptionParameters.create(
        **data.values_for(ABSORPTION_RECIPE.recipe_id)
    )
    absorption = ABSORPTION_RECIPE.run(bindings, parameters, RecipeExecutionContext())
    normalized = NORMALIZATION_RECIPE.run(
        {"spectra": (absorption.objects[0].value,)},
        EdgeNormalizationParameters(),
        RecipeExecutionContext(),
    )
    values = {row[0]: row[1] for row in normalized.results[0].value.data}
    assert values["E0"] == 8980.5
    assert round(values["Edge step"], 2) == 2.73
    assert values["E0"] - 8979.0 == pytest.approx(1.5)


def test_recipes_in_datalab() -> None:
    """From counters to normalized spectrum in DataLab, with results attached."""
    monitor, detector, _expected = _esrf_counters()
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        for signal in (monitor, detector):
            window.signalpanel.add_object(signal, set_current=False)
        runner = RecipeRunner(window)
        absorption = runner.run(
            ABSORPTION_RECIPE,
            {"monitor": (monitor,), "detector": (detector,)},
            AbsorptionParameters(),
        )
        mu = absorption.objects[0].value
        normalized = runner.run(
            NORMALIZATION_RECIPE, {"spectra": (mu,)}, EdgeNormalizationParameters()
        )
        titles = [obj.title for obj in window.signalpanel.objmodel.get_all_objects()]
        assert normalized.objects[0].value.title in titles
        values = {row[0]: row[1] for row in normalized.results[0].value.data}
        assert values["E0"] == pytest.approx(LARCH["esrf_sample"]["e0"])


def test_open_example_in_datalab() -> None:
    """The example opens in the signal panel."""
    with (
        execenv.context(unattended=True),
        datalab_test_app_context(console=False, exec_loop=False) as window,
    ):
        plugin = SynchrotronPlugin()
        plugin.main = window
        plugin.open_example(CU_FOIL_EXAMPLE.id)
        titles = [obj.title for obj in window.signalpanel.objmodel.get_all_objects()]
        assert titles == ["i0 (cu_metal_rt.xdi)", "itrans (cu_metal_rt.xdi)"]
