"""DataLab plugin package."""

PLUGIN_DESCRIPTION = (
    "Read beamline data (SPEC scans, MCA spectra, XDI files) and analyze X-ray "
    "absorption spectra in DataLab"
)
PLUGIN_ID = "org.datalab.synchrotron"
PLUGIN_NAME = "Synchrotron Beamline Data"
__version__ = "0.1.0"

__all__ = [
    "PLUGIN_DESCRIPTION",
    "PLUGIN_ID",
    "PLUGIN_NAME",
    "__version__",
]
