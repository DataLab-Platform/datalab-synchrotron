"""Scan selection and import plans: one group per scan, explicit skips."""

from __future__ import annotations

from pathlib import Path

import pytest
from support.spec_files import write_spec

from datalab_synchrotron.core import SpecFile, plan_scan_import, select_scans


@pytest.fixture(name="spec")
def fixture_spec(tmp_path: Path) -> SpecFile:
    """Synthetic SPEC file."""
    return SpecFile(write_spec(tmp_path / "scans.spec"))


@pytest.mark.parametrize(
    "text, keys",
    [
        ("all", ["1.1", "1.2", "2.1", "3.1", "4.1"]),
        ("", ["1.1", "1.2", "2.1", "3.1", "4.1"]),
        ("1", ["1.1", "1.2"]),
        ("1.2", ["1.2"]),
        ("4, 2-3", ["2.1", "3.1", "4.1"]),
    ],
)
def test_select_scans(spec: SpecFile, text: str, keys: list[str]) -> None:
    """Scans are selected by number, key or range, in file order."""
    assert select_scans(spec, text) == keys


@pytest.mark.parametrize(
    "text, message",
    [("1;2", "Invalid scan selection '1;2'"), ("7", "No scan matches '7'")],
)
def test_invalid_selection(spec: SpecFile, text: str, message: str) -> None:
    """Invalid selections are refused with an example of valid ones."""
    with pytest.raises(ValueError, match=message):
        select_scans(spec, text)


def test_one_group_per_scan(spec: SpecFile) -> None:
    """Scans of the same structure are not merged; others are skipped explicitly."""
    plan = plan_scan_import(
        spec, select_scans(spec, "all"), "Theta", ["Monitor", "Detector counts"]
    )
    assert [group.title for group in plan.groups] == [
        "Scan 1.1 - ascan  th 1 0.6 4 0.1",
        "Scan 1.2 - ascan  th 0 1 2 0.1",
    ]
    assert [len(group.signals) for group in plan.groups] == [2, 2]
    assert plan.skipped == (
        "scan 2.1: no column Theta, Monitor, Detector counts",
        "scan 3.1: no column Theta, Monitor, Detector counts",
        "scan 4.1: no column Theta, Monitor, Detector counts",
    )


def test_mca_only(spec: SpecFile) -> None:
    """MCA spectra are imported without columns, from the scans that have some."""
    plan = plan_scan_import(spec, ["3.1", "4.1"], "Energy", [], include_mca=True)
    assert [len(group.signals) for group in plan.groups] == [1, 3]
    with pytest.raises(ValueError, match="Select at least one counter"):
        plan_scan_import(spec, ["3.1"], "Energy", ["Energy"])
    with pytest.raises(ValueError, match="No signal to import: scan 1.1"):
        plan_scan_import(spec, ["1.1"], "Energy", ["I0"])
