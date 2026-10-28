# <img src="src/datalab_synchrotron/icons/synchrotron.svg" alt="" width="48" align="absmiddle"> Synchrotron Beamline Data

A [DataLab](https://datalab-platform.com/) plugin to read beamline data and analyze it in DataLab.

> **Example plugin.** This plugin shows how DataLab can read beamline data and run a beamline analysis. It is a demonstration, not a finished or supported feature: its scope is limited to what is described below, its results are validated only by the tests described in [CONTRIBUTING](CONTRIBUTING.md) (SPEC reader compared with spec2nexus on extracts of real files, XDI reader on the test files of the XDI library, X-ray absorption analysis compared with Larch on measured spectra), and its interface may change without notice.

## What it does

- **SPEC files:** **Plugins > Synchrotron Beamline Data > Import SPEC scans...** reads any SPEC file, whatever its extension: choose the scans (`all`, or e.g. `1, 3.2, 10-12`), the X column, the counters and the MCA devices, and each scan is imported in its own group. Counters are signals versus the X column; counters of mesh scans (`mesh`, `dmesh`) are images of the two motors (optional), with NaN for the points missing in an interrupted scan; after data lines that cannot be read, the points that follow are placed from the motor positions (the lost points are NaN), or, if the positions do not tell how many points were lost, the counters are imported as signals and the reason is reported; the spectra of each MCA device are an image, one spectrum per row, versus the calibrated channels and the X column (or the point number), in the image panel. Scans lacking a selected column, or that cannot be read, are skipped and reported in one line per reason, and a progress dialog lets you cancel a long import. **File > Open** in the signal panel also reads a `.spec` file, as one signal per scan: the last column (usually the detector counts) versus the first one (usually the scanned motor). Repeated scan numbers are told apart by their occurrence (`12.1`, `12.2`), the acquisition order of the points is kept, incomplete data lines of interrupted scans are skipped and counted, missing values (`None`, `nan`) are NaN, labels separated by single spaces are split according to the column count, and MCA spectra of several devices (`@A1`, `@A2`...) are read with their own channel range and calibration.
- Each object records its origin in its `experimental_source` metadata: file, scan, columns, command, date and motor positions; the scan header (count time, monitor, hkl, geometry, comments, Bluesky metadata) is kept as `SPEC ...` metadata. A saved workspace reopens without the SPEC file or the plugin.
- **XDI files** (XAS Data Interchange, as written by Larch, Athena and many beamlines): **File > Open** reads every column versus the energy, with units, as the XDI library does: data tables with invalid values are refused with the line number, invalid header lines are recorded (`XDI problems` metadata), free text may be UTF-8, monochromator angles are converted to energies with the lattice spacing (`Mono.d_spacing`), and two-dimensional data (`Outer.value` blocks) gives one signal per block. Every header field and the comments are kept as metadata; the origin records the element, edge, facility, beamline, monochromator, sample and start time.
- **X-ray absorption (XANES/EXAFS):** **Absorption from counters...** computes `mu(E)` from the selected monitor (I0, recognized by its name) and detector counts, in transmission (`ln(I0/It)`) or fluorescence (`If/I0`); points without valid counts are left out and listed. **Edge normalization...** finds the edge energy E0 of each selected spectrum and normalizes it to a unit edge step, with a pre-edge line and a post-edge polynomial (automatic or given ranges), giving the normalized and flattened spectra and a table of E0, edge step and ranges. The results are those of [Larch](https://xraypy.github.io/xraylarch/) on 10 measured spectra (transmission and fluorescence, several beamlines). Energies in keV are converted to eV, and results are given in eV. Spectra are refused, with a message telling which X unit to set, if their energies are in another unit (e.g. monochromator angles in degrees), labelled keV with values in eV, or without unit and below 150 (most likely keV, as often in SPEC files); energies without unit from 150 up are taken as eV.
- **Example:** **Open copper foil example** opens the monitor and transmitted counts of a copper foil (Larch examples, MIT license) to try both recipes: E0 is 8980.5 eV, 1.5 eV above the tabulated Cu K edge, and the edge step is 2.73.
- NeXus files are read by DataLab itself (HDF5 browser), which shows `NXdata` groups as signals or images with their axes, and stacks of images or spectra as frames, including the legacy conventions of recent SOLEIL scans: counters are signals versus the scanned motor, and detectors images or stacks with the motor first. While the plugin is loaded, the HDF5 browser also shows every counter and detector `data_1`, `data_2`... of scan data groups versus the time stamps `time_1` of the points, with its label and units: such groups (time scans of SOLEIL) designate only their first counter, without axis.

The readers are written in pure Python: the plugin installs from DataLab's plugin catalog, including with the standalone version of DataLab, and its core can run in DataLab-Web. silx and spec2nexus are used only by the tests, as reference readers.

## Installation

Python 3.10 or later is required in a Python environment; the standalone DataLab application supplies its own interpreter.

The plugin needs DataLab 1.4 or later (not released yet). Download the wheel (`.whl`) attached to the latest release and install it with **Plugins > Configure plugins... > Install plugins**, or install it with pip in the Python environment of DataLab:

```bash
pip install git+https://github.com/DataLab-Platform/datalab-synchrotron.git
```

## Documentation

- [Contributing](CONTRIBUTING.md)
- [Changelog](CHANGELOG.md)

## License

BSD 3-Clause, see [LICENSE](LICENSE).
