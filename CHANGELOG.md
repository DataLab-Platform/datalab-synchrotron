# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

First version of the Synchrotron Beamline Data plugin.

- SPEC reader in pure Python: index of scans with repeated numbers told apart by occurrence, columns in acquisition order, motor positions from the file headers, interrupted scans, MCA spectra with continuation lines, channel range and calibration; SPEC files recognized by their content, whatever their extension.
- **File > Open** of `.spec` files in the signal panel: one signal per scan, last column versus the first one.
- **Plugins > Synchrotron Beamline Data > Import SPEC scans...**: selection of scans (`all`, numbers, `<number>.<occurrence>` keys, ranges), X column, counters and MCA spectra, imported in one group per scan; scans lacking a selected column are skipped and reported in one line per reason. Scans are read and added one at a time, in batches, with a progress dialog that cancels the import (the 5414 signals of a scan with 4 MCA spectra per point are added in about 6 s).
- Origin of each signal in its `experimental_source` metadata (file, scan, columns, command, date, motor positions).
- HDF5 data mapping "Scan counters", applied by DataLab's HDF5 browser while the plugin is loaded: each counter `data_<n>` of an `NXdata` group with `time_1` time stamps is imported versus time.
- X-ray absorption analysis core (`core.xas`): absorption from monitor and detector counts in transmission or fluorescence, with invalid points reported; edge energy E0; pre-edge and post-edge normalization and flattening. Results are identical to Larch's on 10 measured spectra (reference foils and samples, transmission and fluorescence, several beamlines), and E0 of reference foils is within 2 eV of tabulated edge energies.
- **Plugins > Synchrotron Beamline Data > Absorption from counters...** and **Edge normalization...** recipes: `mu(E)` from the selected monitor and detector counts (monitor recognized by its name, counters of different scans refused, invalid points listed); normalized and flattened spectra with a results table (E0, edge step, fit ranges and degree), automatic or given E0 and ranges.
- XDI reader (XAS Data Interchange 1.x) in pure Python, and **File > Open** of `.xdi` files in the signal panel: one signal per column versus the energy, with units and origin (element, edge, beamline, sample...).
- **Open copper foil example**: measured counts of a copper foil (Larch examples) to try the absorption and normalization recipes.
