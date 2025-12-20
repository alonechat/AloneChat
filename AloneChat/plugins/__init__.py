import os
import sys
from abc import ABC, abstractmethod

from AloneChat.core import MessageType

__all__ = [
    'Plugin', '_PluginImpl',
    'LoadPluginsLocally'
]


def load_plugins(path):
    plugins = dict()
    sys.path.append(path)
    for filename in os.listdir(path):
        if filename.endswith('.py'):
            mod = __import__(filename[:-3])
            try:
                plugins[filename[:-3]] = \
                    {"type": MessageType.COMMAND, "handler": mod.PluginImpl}
            except AttributeError:
                pass
    return plugins


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
    def execute(self, *args, **kwargs) -> str:
        """
        Execute the plugin's main functionality.

        Args:
            *args: Variable positional arguments
            **kwargs: Variable keyword arguments
        """
        pass


class _PluginImpl(ABC):
    """
    Abstract base class for AloneChat plugins **implementation**.
    All plugins must inherit from this class and implement its methods.
    """

    def __init__(self, plugin: Plugin, context):
        self.context = context
        self.plugin: Plugin = plugin
        self.plugin.initialize(context)

    @abstractmethod
    def __call__(self, *args, **kwargs) -> str:
        return self.plugin.execute(*args, **kwargs)


class LoadPluginsLocally:
    def __init__(self):
        pass

    def __call__(self):
        return load_plugins('./AloneChat/plugins')
