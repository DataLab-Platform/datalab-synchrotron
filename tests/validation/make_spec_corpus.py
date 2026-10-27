"""Generate the SPEC validation corpus and its reference values.

Run from the repository root, with network access, in a Python environment where
spec2nexus (from the commit of the corpus sources) and silx are installed::

    pip install silx "spec2nexus @ git+https://github.com/prjemian/spec2nexus@7d315b23463631ae07c98a07d2abc0034e665431"
    python tests/validation/make_spec_corpus.py

Source files are downloaded at pinned commits and checked against their SHA-256
(``tests/support/spec_corpus.py``). Corpus files are written to
``tests/data/spec``: whole files unchanged, extracts made of the selected scans
preceded by the file header that applies to them, limited to their first points
if requested. Their SHA-256 are printed, to be recorded in ``spec_corpus.py``.

The values read by spec2nexus, or by silx for the files spec2nexus cannot read,
are written to ``tests/data/spec/references.json``, so that the validation tests
need neither: for each scan, in file order, the column labels and, for each
column, the number of values, of NaN values, and their sum; for each MCA device,
the number of spectra, of channels and the sum of the counts.
"""  # noqa: E501

from __future__ import annotations

import contextlib
import hashlib
import io
import json
import sys
import urllib.request
import warnings
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).parents[1]))

from support.spec_corpus import DATA_DIR, EXTRACTS, REFERENCES, Extract  # noqa: E402


def _download(item: Extract) -> bytes:
    """Return the source file, checked against its SHA-256 if recorded."""
    with urllib.request.urlopen(item.url, timeout=60) as response:  # noqa: S310
        raw = response.read()
    digest = hashlib.sha256(raw).hexdigest()
    if item.source_sha256 and digest != item.source_sha256:
        raise ValueError(f"{item.url}: SHA-256 {digest} differs from the expected one")
    print(f"{item.filename}: source SHA-256 {digest}")
    return raw


def _scan_lines(
    lines: list[str], scans: tuple[tuple[int, int], ...], max_points: int | None
) -> list[str]:
    """Return the lines of the selected scans, each preceded by the file header
    that applies to it (written once), and limited to their first points."""
    wanted = set(scans)
    out: list[str] = []
    header: list[str] = []
    header_written = False
    occurrences: dict[int, int] = {}
    selected = in_scan = stopped = continued = False
    points = 0

    def end_scan() -> None:
        if selected and out and out[-1].strip():
            out.append("\n")

    for line in lines:
        stripped = line.strip()
        if line.startswith(("#F ", "#E ")):
            end_scan()
            header, header_written = [line], False
            selected = in_scan = False
        elif line.startswith("#S "):
            end_scan()
            number = int(line.split()[1])
            occurrences[number] = occurrences.get(number, 0) + 1
            selected = (number, occurrences[number]) in wanted
            in_scan, stopped, continued, points = True, False, False, 0
            if selected:
                if not header_written:
                    out.extend(header)
                    if header and header[-1].strip():
                        out.append("\n")
                    header_written = True
                out.append(line)
        elif not in_scan:
            header.append(line)
        elif selected and not stopped:
            is_point = (
                not continued and stripped and not stripped.startswith(("#", "@"))
            )
            continued = stripped.endswith("\\")
            if is_point:
                points += 1
                if max_points is not None and points > max_points:
                    stopped = True
                    continue
            out.append(line)
    end_scan()
    return out


def _keys(numbers: list[int]) -> list[str]:
    """Return the ``<number>.<occurrence>`` keys of scans numbered in file order."""
    occurrences: dict[int, int] = {}
    keys = []
    for number in numbers:
        occurrences[number] = occurrences.get(number, 0) + 1
        keys.append(f"{number}.{occurrences[number]}")
    return keys


def _column(values) -> list[float]:
    """Return the number of values, of NaN values, and the sum of the others."""
    array = np.asarray(values, dtype=float)
    return [int(array.size), int(np.isnan(array).sum()), float(np.nansum(array))]


def _spectra(spectra) -> list[float]:
    """Return the number of spectra, of channels, and the sum of the counts."""
    array = np.asarray(spectra, dtype=float)
    return [int(array.shape[0]), int(array.shape[1]), float(array.sum())]


def _spec2nexus_scans(path: Path) -> list[dict]:
    """Return the reference values of the scans read by spec2nexus."""
    from spec2nexus import spec  # pylint: disable=import-outside-toplevel

    with contextlib.redirect_stdout(io.StringIO()), warnings.catch_warnings():
        warnings.simplefilter("ignore")
        scans = list(spec.SpecDataFile(str(path)).scans.values())
        for scan in scans:
            scan.interpret()
    keys = _keys([int(str(scan.scanNum).split(".")[0]) for scan in scans])
    results = []
    for key, scan in zip(keys, scans):
        data = scan.data
        mca = data.get("_mca_", {})
        results.append(
            {
                "key": key,
                "labels": list(scan.L),
                "columns": [_column(data[label]) for label in scan.L],
                "mca": {device: _spectra(spectra) for device, spectra in mca.items()},
            }
        )
    return results


def _silx_scans(path: Path) -> list[dict]:
    """Return the reference values of the scans read by silx."""
    from silx.io import specfile  # pylint: disable=import-outside-toplevel

    reference = specfile.SpecFile(str(path))
    try:
        return [
            {
                "key": key,
                "labels": list(reference[key].labels),
                "columns": [_column(values) for values in reference[key].data],
                "mca": (
                    {"mca": _spectra(list(reference[key].mca))}
                    if len(reference[key].mca)
                    else {}
                ),
            }
            for key in reference.keys()
        ]
    finally:
        reference.close()


def _references(path: Path) -> dict:
    """Return the reference values of a corpus file, and the reader used."""
    try:
        return {"reader": "spec2nexus", "scans": _spec2nexus_scans(path)}
    except Exception:  # pylint: disable=broad-except
        return {"reader": "silx", "scans": _silx_scans(path)}


def main() -> None:
    """Write the corpus files and their reference values."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    references = {}
    for item in EXTRACTS:
        raw = _download(item)
        if item.scans is None:
            item.path.write_bytes(raw)
        else:
            lines = raw.decode("latin-1").splitlines(keepends=True)
            text = "".join(_scan_lines(lines, item.scans, item.max_points))
            item.path.write_bytes(text.encode("latin-1"))
        digest = hashlib.sha256(item.path.read_bytes()).hexdigest()
        print(f"{item.filename}: SHA-256 {digest}")
        references[item.filename] = _references(item.path)
    import silx  # pylint: disable=import-outside-toplevel
    from spec2nexus import __version__  # pylint: disable=import-outside-toplevel

    document = {
        "spec2nexus_version": __version__,
        "silx_version": silx.version,
        "files": references,
    }
    REFERENCES.write_text(json.dumps(document, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote {REFERENCES}")


if __name__ == "__main__":
    main()
