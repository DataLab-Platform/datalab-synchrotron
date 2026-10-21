"""Headless recipes and examples run by DataLab on the user's signals."""

from .examples import CU_FOIL_EXAMPLE, EXAMPLES, materialize_example
from .xas import (
    ABSORPTION_RECIPE,
    NORMALIZATION_RECIPE,
    RECIPES,
    AbsorptionParameters,
    EdgeNormalizationParameters,
)

__all__ = [
    "ABSORPTION_RECIPE",
    "CU_FOIL_EXAMPLE",
    "EXAMPLES",
    "NORMALIZATION_RECIPE",
    "RECIPES",
    "AbsorptionParameters",
    "EdgeNormalizationParameters",
    "materialize_example",
]
