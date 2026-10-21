# Synchrotron Beamline Data

A [DataLab](https://datalab-platform.com/) plugin to read beamline data and analyze it in DataLab.

> **Status: Alpha.** The SPEC reader is validated against silx on synthetic files. Beamline analyses and profiles will follow.

## What it does

- **SPEC files:** **Plugins > Synchrotron Beamline Data > Import SPEC scans...** reads any SPEC file, whatever its extension: choose the scans (`all`, or e.g. `1, 3.2, 10-12`), the X column, the counters and the MCA spectra, and each scan is imported in its own group. Scans lacking a selected column are skipped and listed. **File > Open** in the signal panel also reads a `.spec` file, as one signal per scan: the last column (usually the detector counts) versus the first one (usually the scanned motor). Repeated scan numbers are told apart by their occurrence (`12.1`, `12.2`), the acquisition order of the points is kept, incomplete data lines of interrupted scans are skipped and counted, and MCA spectra are read with their channel range and calibration.
- Each signal records its origin in its `experimental_source` metadata: file, scan, columns, command, date and motor positions. A saved workspace reopens without the SPEC file or the plugin.
- NeXus files are read by DataLab itself (HDF5 browser), which shows `NXdata` groups as signals or images with their axes.

The readers are written in pure Python: the plugin installs from DataLab's plugin catalog, including with the standalone version of DataLab, and its core can run in DataLab-Web. silx is used only by the tests, as a reference reader.

## Installation

The plugin needs DataLab 1.4 or later (not released yet). Download the wheel (`.whl`) attached to the latest release and install it with **Plugins > Configure plugins... > Install plugins**, or install it with pip in the Python environment of DataLab:

```bash
pip install git+https://github.com/DataLab-Platform/datalab-synchrotron.git
```

## Documentation

- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

BSD 3-Clause, see [LICENSE](LICENSE).
