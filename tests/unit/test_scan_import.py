"""Scan selection and import plans: one group per scan, explicit skips."""

from __future__ import annotations

from pathlib import Path

import pytest
from sigima.objects import get_experimental_source
from support.spec_files import MESH_TEXT, MORE_TEXT, write_spec

from datalab_synchrotron.core import (
    SkippedScan,
    SpecFile,
    import_scan,
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
    assert plan.object_count == 4


def test_mca_only(spec: SpecFile) -> None:
    """MCA spectra are imported without columns, as one image per device, from the
    scans that have some."""
    plan = plan_scan_import(spec, ["3.1", "4.1"], "Energy", [], ["mca"])
    assert [len(group.images) for group in plan.groups] == [1, 1]
    assert not any(group.signals for group in plan.groups)
    assert plan.groups[1].images[0].data.shape == (3, 4)
    with pytest.raises(ValueError, match="Select at least one counter or MCA"):
        plan_scan_import(spec, ["3.1"], "Energy", ["Energy"])
    message = "Nothing to import:\nNo column Energy, I0 \\(scan 1.1\\)"
    with pytest.raises(ValueError, match=message):
        plan_scan_import(spec, ["1.1"], "Energy", ["I0"])


def test_mesh_scans(tmp_path: Path) -> None:
    """Counters of mesh scans are images, unless asked otherwise; the X column is
    then not needed."""
    more = SpecFile(write_spec(tmp_path / "more.spec", text=MORE_TEXT))
    group, skipped = import_scan(more, "3.1", "Energy", ["counts"])
    assert skipped is None and not group.signals
    assert group.images[0].data.shape == (2, 3)
    group, _skipped = import_scan(
        more, "3.1", "Sample X", ["counts"], mesh_as_images=False
    )
    assert len(group.signals) == 1 and not group.images


def test_mesh_points_that_cannot_be_placed(tmp_path: Path) -> None:
    """Counters of a mesh scan whose points cannot be placed after data lines that
    could not be read are imported as signals versus X, with the reason."""
    meshes = SpecFile(write_spec(tmp_path / "mesh.spec", text=MESH_TEXT))
    reason = (
        "mesh imported as signals: points cannot be placed after lines that "
        "could not be read"
    )
    for key in ("6.1", "7.1"):
        group, skipped = import_scan(meshes, key, "samx", ["counts"])
        assert skipped == SkippedScan(key, reason)
        assert not group.images
        (signal,) = group.signals
        assert get_experimental_source(signal)["conversions"] == [reason]
    group, skipped = import_scan(meshes, "7.1", "Energy", ["counts"])
    assert group is None and skipped == SkippedScan("7.1", "no column Energy")
    group, skipped = import_scan(meshes, "1.1", "samx", ["counts"])
    assert skipped is None and not group.signals
    assert group.images[0].data.shape == (2, 3)


def test_unreadable_scan(spec: SpecFile, monkeypatch: pytest.MonkeyPatch) -> None:
    """A scan that cannot be read is skipped with the error, the others are read."""
    read_scan = spec.read_scan

    def failing(key: str):
        if key == "1.2":
            raise IndexError("list index out of range")
        return read_scan(key)

    monkeypatch.setattr(spec, "read_scan", failing)
    plan = plan_scan_import(spec, ["1.1", "1.2"], "Theta", ["Monitor"])
    assert [group.title for group in plan.groups] == [
        "Scan 1.1 - ascan  th 1 0.6 4 0.1"
    ]
    assert plan.skipped == (SkippedScan("1.2", "unreadable: list index out of range"),)


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
