"""
Help Plugin
"""
from AloneChat.plugins import Plugin, _PluginImpl


class HelpPlugin(Plugin):
    def initialize(self, context=None):
        pass

    @staticmethod
    def execute(*args, **kwargs):
        return "TODO: Implement this message..."


class PluginImpl(_PluginImpl):
    def __init__(self, plugin: Plugin = HelpPlugin, context=None):
        super().__init__(plugin, context)

    def __call__(self, *args, **kwargs):
        return self.plugin.execute(*args, **kwargs)
