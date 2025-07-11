from abc import ABC, abstractmethod
import importlib.util
import os


class Plugin(ABC):
    @abstractmethod
    def initialize(self, context):
        pass

    @abstractmethod
    def execute(self, *args, **kwargs):
        pass


class PluginManager:
    def __init__(self):
        self.plugins = {}

    def load_plugin(self, path):
        spec = importlib.util.spec_from_file_location("plugin", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        if hasattr(module, 'PluginImpl'):
            plugin = module.PluginImpl()
            self.plugins[plugin.__class__.__name__] = plugin
            return True
        return False

    def load_all(self, directory):
        for filename in os.listdir(directory):
            if filename.endswith('.py'):
                self.load_plugin(os.path.join(directory, filename))