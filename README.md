# Synchrotron Beamline Data

A [DataLab](https://datalab-platform.com/) plugin to read beamline data and analyze it in DataLab.

> **Status: Alpha.** The SPEC reader is validated against silx on synthetic files, and the X-ray absorption analysis against Larch on measured spectra. Beamline profiles will follow.

## What it does

- **SPEC files:** **Plugins > Synchrotron Beamline Data > Import SPEC scans...** reads any SPEC file, whatever its extension: choose the scans (`all`, or e.g. `1, 3.2, 10-12`), the X column, the counters and the MCA spectra, and each scan is imported in its own group. Scans lacking a selected column are skipped and listed. **File > Open** in the signal panel also reads a `.spec` file, as one signal per scan: the last column (usually the detector counts) versus the first one (usually the scanned motor). Repeated scan numbers are told apart by their occurrence (`12.1`, `12.2`), the acquisition order of the points is kept, incomplete data lines of interrupted scans are skipped and counted, and MCA spectra are read with their channel range and calibration.
- Each signal records its origin in its `experimental_source` metadata: file, scan, columns, command, date and motor positions. A saved workspace reopens without the SPEC file or the plugin.
- **XDI files** (XAS Data Interchange, as written by Larch, Athena and many beamlines): **File > Open** reads every column versus the energy, with units; the origin records the element, edge, facility, beamline, monochromator, sample and start time.
- **X-ray absorption (XANES/EXAFS):** **Absorption from counters...** computes `mu(E)` from the selected monitor (I0, recognized by its name) and detector counts, in transmission (`ln(I0/It)`) or fluorescence (`If/I0`); points without valid counts are left out and listed. **Edge normalization...** finds the edge energy E0 of each selected spectrum and normalizes it to a unit edge step, with a pre-edge line and a post-edge polynomial (automatic or given ranges), giving the normalized and flattened spectra and a table of E0, edge step and ranges. The results are those of [Larch](https://xraypy.github.io/xraylarch/) on 10 measured spectra (transmission and fluorescence, several beamlines).
- **Example:** **Open copper foil example** opens the monitor and transmitted counts of a copper foil (Larch examples, MIT license) to try both recipes: E0 is 8980.5 eV, 1.5 eV above the tabulated Cu K edge, and the edge step is 2.73.
- NeXus files are read by DataLab itself (HDF5 browser), which shows `NXdata` groups as signals or images with their axes. While the plugin is loaded, the HDF5 browser also shows every counter `data_1`, `data_2`... of scan data groups as a signal versus the time stamps `time_1` of the points, with its label and units: such groups designate only their first counter, without axis.

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
