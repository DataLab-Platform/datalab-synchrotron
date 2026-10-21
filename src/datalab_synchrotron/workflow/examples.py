"""Examples opened from the plugin menu, with the recipes they were designed for."""

from __future__ import annotations

import dataclasses
from importlib import resources

from datalab.plugins.examples import PluginExample, PluginExampleData

from ..core import AbsorptionMode, read_xdi, xdi_signals
from .xas import ABSORPTION_RECIPE, NORMALIZATION_RECIPE

_CU_FOIL_FILE = "cu_metal_rt.xdi"

CU_FOIL_EXAMPLE = PluginExample(
    id="cu-foil-xas",
    title="Copper foil, K edge",
    description=(
        "Monitor (i0) and transmitted (itrans) counts of a copper foil measured in "
        "transmission at APS 13-ID (Larch examples, MIT license). Compute mu(E), "
        "then normalize it."
    ),
    recipe_ids=(ABSORPTION_RECIPE.recipe_id, NORMALIZATION_RECIPE.recipe_id),
    expected_checks=(
        "E0 = 8980.5 eV, 1.5 eV above the tabulated Cu K edge (8979 eV)",
        "Edge step: 2.73",
    ),
)

EXAMPLES = (CU_FOIL_EXAMPLE,)


def materialize_example(example_id: str) -> PluginExampleData:
    """Return the objects of an example, read from the plugin's data files."""
    if example_id != CU_FOIL_EXAMPLE.id:
        raise KeyError(f"Unknown example {example_id!r}")
    package = __package__.rsplit(".", 1)[0]
    item = resources.files(package).joinpath("data").joinpath("examples")
    with resources.as_file(item.joinpath(_CU_FOIL_FILE)) as path:
        xdi = read_xdi(path)
    xdi = dataclasses.replace(xdi, path=f"{package}/data/examples/{_CU_FOIL_FILE}")
    return PluginExampleData(
        objects=xdi_signals(xdi, ["i0", "itrans"]),
        parameter_values={
            ABSORPTION_RECIPE.recipe_id: {"mode": AbsorptionMode.TRANSMISSION.value}
        },
    )


__all__ = ["CU_FOIL_EXAMPLE", "EXAMPLES", "materialize_example"]
