PLUGIN_MODULES = {
    'admin': ['kick'],
    'encryption': ['aes']
}

def load_plugins():
    plugins = []
    for category, modules in PLUGIN_MODULES.items():
        for module in modules:
            mod = __import__(f'plugins.{category}.{module}', fromlist=['PluginImpl'])
            plugins.append(mod.PluginImpl())
    return plugins