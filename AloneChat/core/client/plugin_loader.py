"""
Plugin system module for AloneChat application.
Provides base plugin interface and plugin management functionality.
"""

from AloneChat.plugins import LoadPluginsLocally

PLUGIN_MODULES = dict()


class PluginManager:
    """
    Plugin manager responsible for loading and managing plugins.
    """

    def __init__(self, path="../../plugins"):
        """
        Initialize plugin manager with "plugins" directory path.

        Args:
            path: Path to plugins directory
        """
        self.__path = path
        self.plugins = {}

    def load(self):
        """
        Load all plugins from the specified plugins directory.
        Plugins are registered in the PLUGIN_MODULES registry.
        """
        loader = LoadPluginsLocally()
        self.plugins = loader()
        return self.plugins
