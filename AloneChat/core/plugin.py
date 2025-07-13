from abc import ABC, abstractmethod

import AloneChat.plugins as _plugins


class Plugin(ABC):
    @abstractmethod
    def initialize(self, context):
        pass

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass


class PluginManager:
    def __init__(self, path):
        self.__path = path
        self.plugins = {}

    def load(self):
        _plugins.load_plugins(path=self.__path)
        self.plugins = _plugins.PLUGIN_MODULES
