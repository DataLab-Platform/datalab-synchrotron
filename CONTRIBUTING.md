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
adapters -> workflow, formats, mappings -> core
```

- `core` holds the readers (`spec`), their conversion to Sigima signals with their `experimental_source`, the import plans of scans (`convert`), and the X-ray absorption analysis (`xas`). It imports neither DataLab, Qt, nor compiled reader libraries such as silx or FabIO, so that it also runs in DataLab-Web and installs from DataLab's plugin catalog.
- `workflow` holds the recipes run by DataLab (`xas`): headless, they use DataLab's recipe contracts (`datalab.plugins.recipes`) and the core only.
- `formats.py` registers the Sigima file formats used by **File > Open**, and removes them when the plugin is unloaded.
- `mappings.py` registers the HDF5 data mappings of `data/mappings` (JSON, see `sigimax.h5.mapping`) when the plugin is loaded, and removes them when it is unloaded. A new mapping is a new JSON file there.
- `adapters/desktop.py` declares the plugin and its **Import SPEC scans...** action.

`tests/unit/test_architecture.py` checks the layer boundaries.

## Tests

- `tests/unit`: readers, conversion, formats and shipped mappings, on synthetic files (`tests/support`).
- `tests/integration`: imports and recipes in DataLab. DataLab's discovery of installed plugins is disabled there, so that an editable install does not reload the modules patched by the tests.
- `tests/validation`: the SPEC reader compared with silx's reader (skipped if silx is not installed), and the XAS analysis on measured spectra (`tests/data/xas`, from Larch's examples, MIT license) compared with Larch's results and with tabulated edge energies. Larch's results are frozen in `tests/data/xas/larch_references.json`; regenerate them with `python tests/validation/make_larch_references.py` in an environment where Larch is installed (`pip install xraylarch`).

## Branches

Day-to-day work lands on `develop`, the default branch: open pull requests against it. `main` is the release branch, created at the first release; after that, `develop` is merged into `main` only to cut a release.
