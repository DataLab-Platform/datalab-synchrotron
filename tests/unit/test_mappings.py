"""HDF5 data mappings shipped with the plugin."""

from __future__ import annotations

from datalab_synchrotron.mappings import packaged_mappings


def test_packaged_mappings_are_valid() -> None:
    """Every shipped mapping is loaded and validated, under a distinct name."""
    mappings = packaged_mappings()
    assert [mapping.name for mapping in mappings] == ["Scan counters"]
    assert len({mapping.name for mapping in mappings}) == len(mappings)
