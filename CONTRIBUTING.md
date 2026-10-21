# Contributing

## Setup and Checks

Install the project in editable mode, in a Python environment where DataLab 1.4 or later is available, then run the checks before submitting a change:

```bash
python -m pip install -e ".[test]"
python -m ruff check .
python -m pytest
```

## Architecture

Dependencies point inward:

```text
adapters -> formats -> core
```

- `core` holds the readers (`spec`) and their conversion to Sigima signals with their `experimental_source` (`convert`). It imports neither DataLab, Qt, nor compiled reader libraries such as silx or FabIO, so that it also runs in DataLab-Web and installs from DataLab's plugin catalog.
- `formats.py` registers the Sigima file formats used by **File > Open**, and removes them when the plugin is unloaded.
- `adapters/desktop.py` declares the plugin.

`tests/unit/test_architecture.py` checks the layer boundaries.

## Tests

- `tests/unit`: readers, conversion and formats, on synthetic files (`tests/support`).
- `tests/validation`: the SPEC reader compared with silx's reader (skipped if silx is not installed).

## Branches

Day-to-day work lands on `develop`, the default branch: open pull requests against it. `main` is the release branch, created at the first release; after that, `develop` is merged into `main` only to cut a release.
