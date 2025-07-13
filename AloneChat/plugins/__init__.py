import sys

PLUGIN_MODULES = dict()


def load_plugins(path):
    sys.path.append(path)
    plugins = []
    for category, modules in PLUGIN_MODULES.items():
        for module in modules:
            mod = __import__(f'plugins.{category}.{module}', fromlist=['PluginImpl'])
            plugins.append(mod.PluginImpl())
    return plugins
