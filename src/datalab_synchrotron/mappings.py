"""HDF5 data mappings shipped with the plugin.

They describe the signals of beamline files that NeXus ``NXdata`` groups do not
designate completely, and are applied by DataLab's HDF5 browser while the plugin
is loaded.
"""

from __future__ import annotations

from importlib import resources

from sigimax.h5.mapping import (
    DataMapping,
    load_mapping,
    register_mapping,
    unregister_mapping,
)

__all__ = ["packaged_mappings", "register_mappings", "unregister_mappings"]


def packaged_mappings() -> list[DataMapping]:
    """Return the data mappings shipped with the plugin."""
    folder = resources.files(__package__).joinpath("data").joinpath("mappings")
    mappings = []
    for item in sorted(folder.iterdir(), key=lambda item: item.name):
        if item.name.endswith(".json"):
            with resources.as_file(item) as path:
                mappings.append(load_mapping(str(path)))
    return mappings


def register_mappings() -> None:
    """Apply the shipped data mappings to the HDF5 files opened afterwards."""
    for mapping in packaged_mappings():
        register_mapping(mapping)


def unregister_mappings() -> None:
    """Remove the shipped data mappings (when the plugin is unloaded)."""
    for mapping in packaged_mappings():
        unregister_mapping(mapping.name)
