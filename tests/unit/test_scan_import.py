"""Scan selection and import plans: one group per scan, explicit skips."""

from __future__ import annotations

from pathlib import Path

import pytest
from support.spec_files import write_spec

from datalab_synchrotron.core import (
    SkippedScan,
    SpecFile,
    plan_scan_import,
    select_scans,
    summarize_skipped,
)


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
    assert plan.skipped == tuple(
        SkippedScan(key, "no column Theta, Monitor, Detector counts")
        for key in ("2.1", "3.1", "4.1")
    )
    assert plan.signal_count == 4


def test_mca_only(spec: SpecFile) -> None:
    """MCA spectra are imported without columns, from the scans that have some."""
    plan = plan_scan_import(spec, ["3.1", "4.1"], "Energy", [], include_mca=True)
    assert [len(group.signals) for group in plan.groups] == [1, 3]
    with pytest.raises(ValueError, match="Select at least one counter"):
        plan_scan_import(spec, ["3.1"], "Energy", ["Energy"])
    message = "No signal to import:\nNo column Energy, I0 \\(scan 1.1\\)"
    with pytest.raises(ValueError, match=message):
        plan_scan_import(spec, ["1.1"], "Energy", ["I0"])


def test_summarize_skipped() -> None:
    """Skipped scans are reported in one line per reason, most frequent first,
    with a short list of scans: the report stays short for large files."""
    skipped = [SkippedScan(f"{number}.1", "no column eta") for number in range(2, 90)]
    skipped += [SkippedScan("90.1", "no data")]
    skipped += [SkippedScan(f"{n}.1", f"no column c{n}") for n in range(91, 99)]
    lines = summarize_skipped(skipped, max_reasons=3, max_keys=4)
    assert lines == [
        "No column eta (88 scans: 2.1, 3.1, 4.1, ..., 89.1)",
        "No data (scan 90.1)",
        "No column c91 (scan 91.1)",
        "Other reasons (7 scans)",
    ]
    assert summarize_skipped([]) == []
