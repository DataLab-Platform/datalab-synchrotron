"""DataLab Desktop plugin adapter."""

from __future__ import annotations

from datalab.plugins import PluginBase, PluginCapability, PluginInfo

from .. import PLUGIN_DESCRIPTION, PLUGIN_ID, PLUGIN_NAME, __version__
from ..formats import unregister_formats


class SynchrotronPlugin(PluginBase):
    """Expose beamline data readers to DataLab Desktop."""

    PLUGIN_INFO = PluginInfo(
        id=PLUGIN_ID,
        name=PLUGIN_NAME,
        version=__version__,
        description=PLUGIN_DESCRIPTION,
        capabilities=(PluginCapability.IO,),
        documentation_url="https://github.com/DataLab-Platform/datalab-synchrotron",
    )

    def unregister_hooks(self) -> None:
        """Remove the file formats registered when the plugin was loaded."""
        unregister_formats()

    def create_actions(self) -> None:
        """SPEC files are opened with the signal panel's **File > Open**."""
