# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

Python 3.10 or later is required.

First version of the Synchrotron Beamline Data example plugin: a demonstration of DataLab with beamline data, not a finished or supported feature.

- SPEC reader in pure Python: index of scans with repeated numbers told apart by occurrence, columns in acquisition order, motor positions from the file headers, interrupted scans, MCA spectra of one or several devices (`@A`, `@A1`, `@A2`...) with continuation lines and the channel range and calibration of each device; labels separated by single spaces split according to the column count, repeated labels with a suffix (`I0_1`), missing values (`None`, `nan`) read as NaN, empty motor lines (Bluesky) and other `@` lines accepted; SPEC files recognized by their content, whatever their extension.
- **File > Open** of `.spec` files in the signal panel: one signal per scan, last column versus the first one; scans that cannot be read are left out.
- **Plugins > Synchrotron Beamline Data > Import SPEC scans...**: selection of scans (`all`, numbers, `<number>.<occurrence>` keys, ranges), X column, counters and MCA devices, imported in one group per scan: counters as signals, or as images of the two motors for mesh scans (optional, NaN for the missing points of interrupted scans), and the spectra of each MCA device as an image, one spectrum per row, in the image panel. Scans lacking a selected column, or that cannot be read, are skipped and reported in one line per reason. Scans are read and added one at a time, in batches, with a progress dialog that cancels the import.
- Origin of each object in its `experimental_source` metadata (file, scan, columns, command, date, motor positions), and scan header as metadata (count time, monitor, hkl, geometry, comments, Bluesky metadata).
- HDF5 data mapping "Scan counters", applied by DataLab's HDF5 browser while the plugin is loaded: each counter or detector `data_<n>` of an `NXdata` group with `time_1` time stamps is imported versus time (first dimension).
- X-ray absorption analysis core (`core.xas`): absorption from monitor and detector counts in transmission or fluorescence, with invalid points reported; edge energy E0; pre-edge and post-edge normalization and flattening. Results are identical to Larch's on 10 measured spectra (reference foils and samples, transmission and fluorescence, several beamlines), and E0 of reference foils is within 2 eV of tabulated edge energies.
- **Plugins > Synchrotron Beamline Data > Absorption from counters...** and **Edge normalization...** recipes: `mu(E)` from the selected monitor and detector counts (monitor recognized by its name, counters of different scans refused, invalid points listed); normalized and flattened spectra with a results table (E0, edge step, fit ranges and degree), automatic or given E0 and ranges.
- Edge normalization of spectra in keV: energies converted to eV, with the results of the same spectrum in eV, instead of fit ranges computed as if keV were eV. Energies in other units, labelled keV with values in eV, or without unit and below 150 (most likely keV) are refused before running, with the unit to set.
- XDI reader (XAS Data Interchange 1.x) in pure Python, reading files as the XDI library does (invalid data tables refused with their line, invalid header lines recorded, UTF-8 free text, two-dimensional data in blocks), and **File > Open** of `.xdi` files in the signal panel: one signal per column versus the energy (monochromator angles converted with the lattice spacing), with units, all header fields and comments as metadata, and origin (element, edge, beamline, sample...).
- **Open copper foil example**: measured counts of a copper foil (Larch examples) to try the absorption and normalization recipes.
- Application tiles on DataLab's welcome page: the plugin, **Import SPEC scans** and **Open copper foil example**, with their icons.
- Continuous integration: lint and tests on Linux and Windows, including the comparisons with silx, spec2nexus (SPEC extracts of real files), the XDI library (its test files) and Larch.
- File formats removed from Sigima when the plugin is unloaded, and registered again when it is loaded again.
