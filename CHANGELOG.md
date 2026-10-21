# Changelog

All notable changes to this project will be documented in this file.

## Unreleased

First version of the Synchrotron Beamline Data plugin.

- SPEC reader in pure Python: index of scans with repeated numbers told apart by occurrence, columns in acquisition order, motor positions from the file headers, interrupted scans, MCA spectra with continuation lines, channel range and calibration; SPEC files recognized by their content, whatever their extension.
- **File > Open** of `.spec` files in the signal panel: one signal per scan, last column versus the first one.
- **Plugins > Synchrotron Beamline Data > Import SPEC scans...**: selection of scans (`all`, numbers, `<number>.<occurrence>` keys, ranges), X column, counters and MCA spectra, imported in one group per scan; scans lacking a selected column are skipped and listed.
- Origin of each signal in its `experimental_source` metadata (file, scan, columns, command, date, motor positions).
