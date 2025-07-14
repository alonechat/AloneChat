"""
Plugin system module for AloneChat application.
Provides base plugin interface and plugin management functionality.
"""

from abc import ABC, abstractmethod

import AloneChat.plugins as _plugins


class Plugin(ABC):
    """
    Abstract base class for AloneChat plugins.
    All plugins must inherit from this class and implement its methods.
    """

    @abstractmethod
    def initialize(self, context):
        """
        Initialize the plugin with given context.

        Args:
            context: Plugin initialization context
        """
        pass

    @abstractmethod
    def execute(self, *args, **kwargs):
        """
        Execute the plugin's main functionality.

        Args:
            *args: Variable positional arguments
            **kwargs: Variable keyword arguments
        """
        pass


class PluginManager:
    """
    Plugin manager responsible for loading and managing plugins.
    """

    def __init__(self, path):
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
        _plugins.load_plugins(path=self.__path)
        self.plugins = _plugins.PLUGIN_MODULES
