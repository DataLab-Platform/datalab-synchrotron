# Contributing

## Setup and Checks

Install the project in editable mode, in a Python environment where DataLab 1.4 or later is available, then run the checks before submitting a change:

```bash
python -m pip install -e ".[test]"
python -m ruff check .
python -m ruff format --check .
python -m pytest
```

## Continuous Integration

GitHub Actions (`.github/workflows/ci.yml`) runs the same checks on Linux and Windows for each push to `develop` or `main` and each pull request, including the validation tests against silx and the frozen Larch results (Larch itself is not needed). DataLab 1.4 is not released yet: the workflow installs DataLab, Sigima and SigimaX from the `develop` branch of their repositories, or from another branch when run manually (**Run workflow**, `stack-ref` input).

## Trying the Plugin in DataLab

With DataLab 1.4 or later, add this project folder in **Plugins > Configure plugins... > Plugin settings**, then reload the plugins: DataLab loads the plugin from `src/datalab_synchrotron/adapters/desktop.py`, without installing the project (see [DataLab-Platform/DataLab#412](https://github.com/DataLab-Platform/DataLab/pull/412)).

## Architecture

Dependencies point inward:

```text
adapters -> workflow, formats, mappings -> core
```

- `core` holds the readers (`spec`, `xdi`), their conversion to Sigima signals with their `experimental_source`, the import plans of scans (`convert`), and the X-ray absorption analysis (`xas`). It imports neither DataLab, Qt, nor compiled reader libraries such as silx or FabIO, so that it also runs in DataLab-Web and installs from DataLab's plugin catalog.
- `workflow` holds the recipes run by DataLab (`xas`) and the examples (`examples`, data in `data/examples` with its source and license): headless, they use DataLab's recipe and example contracts and the core only.
- `formats.py` registers the Sigima file formats used by **File > Open**, removes them when the plugin is unloaded and registers them again when it is loaded again (Sigima's `register_format` and `unregister_format`).
- `mappings.py` registers the HDF5 data mappings of `data/mappings` (JSON, see `sigimax.h5.mapping`) when the plugin is loaded, and removes them when it is unloaded. A new mapping is a new JSON file there. Files following the NeXus conventions, legacy ones included (`axis` and `primary` attributes, as recent SOLEIL scans), need no mapping: DataLab's HDF5 browser imports them; mappings describe what NeXus does not, such as the time stamps of SOLEIL scans (`axis` 0).
- `adapters/desktop.py` declares the plugin and its **Import SPEC scans...** action.

`tests/unit/test_architecture.py` checks the layer boundaries.

## Tests

- `tests/unit`: readers, conversion, formats and shipped mappings, on synthetic files (`tests/support`).
- `tests/integration`: imports and recipes in DataLab. DataLab's plugin discovery is disabled there: DataLab would otherwise load this plugin, whether installed or found on the Python path, reload the modules patched by the tests and unregister its formats when closing.
- `tests/validation`: the readers and the XAS analysis on real files, compared with independent readers and analysis software:
  - SPEC reader on extracts of real files (`tests/data/spec`: several MCA devices, mesh scans, labels separated by single spaces, Bluesky and Sardana files, interrupted scans, repeated scan numbers), from spec2nexus (CC BY 4.0) and PyMca (MIT), compared with the values read by spec2nexus, or by silx for the files spec2nexus cannot read. The extracts and these values are frozen in `tests/data/spec` (sources at pinned commits and SHA-256 in `tests/support/spec_corpus.py`); regenerate them with `python tests/validation/make_spec_corpus.py` in an environment where spec2nexus, from the same commit as the sources, and silx are installed (see the script). The SPEC reader is also compared with silx's reader on synthetic files (skipped if silx is not installed).
  - XDI reader on the test files of the XDI library (`tests/data/xdi`, public domain), checked against the behaviour of the library described in `BadFiles.txt`.
  - XAS analysis on measured spectra (`tests/data/xas`, from Larch's examples, MIT license) compared with Larch's results and with tabulated edge energies. Larch's results are frozen in `tests/data/xas/larch_references.json`; regenerate them with `python tests/validation/make_larch_references.py` in an environment where Larch is installed (`pip install xraylarch`).

Test data stays in this repository: these formats are read by the plugin, not by Sigima. Each data folder holds a `SOURCES.txt` file giving the origin, commit, license and changes of its files; files without a license allowing redistribution are not added.

## Branches

Day-to-day work lands on `develop`, the default branch: open pull requests against it. `main` is the release branch, created at the first release; after that, `develop` is merged into `main` only to cut a release.
