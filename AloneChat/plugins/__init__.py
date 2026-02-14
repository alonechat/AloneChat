"""
Plugin system for AloneChat application.

This package provides a modular plugin architecture with:
- Clear separation of concerns
- Standardized interfaces for plugin registration
- Lifecycle management
- Dependency handling
- Backward compatibility with legacy plugins

Architecture Overview:
---------------------

1. **Base Classes** (`base.py`)
   - PluginBase: Abstract base for all plugins
   - CommandPluginBase: For command-processing plugins
   - HandlerPluginBase: For message handler plugins
   - MiddlewarePluginBase: For middleware plugins
   - PluginMetadata: Plugin configuration data
   - PluginInfo: Runtime plugin information

2. **Exceptions** (`exceptions.py`)
   - PluginError: Base exception
   - PluginLoadError: Loading failures
   - PluginInitError: Initialization failures
   - PluginDependencyError: Dependency resolution failures
   - And more specialized exceptions

3. **Context** (`context.py`)
   - PluginContext: Context passed to plugins
   - CommandContext: Context for command execution

4. **Registry** (`registry.py`)
   - PluginRegistry: Central plugin tracking
   - Dependency graph management
   - State management

5. **Loader** (`loader.py`)
   - PluginLoader: Discovers and loads plugins
   - LegacyPluginAdapter: Backward compatibility
   - Plugin validation

6. **Manager** (`manager.py`)
   - PluginManager: Main interface
   - Lifecycle management
   - Event handling
   - Service registration

Usage Example:
-------------

    from AloneChat.plugins import PluginManager, CommandPluginBase, PluginMetadata

    # Create a custom plugin
    class MyPlugin(CommandPluginBase):
        _metadata = PluginMetadata(
            name="my_plugin",
            version="1.0.0",
            description="My custom plugin"
        )
        
        def initialize(self, context):
            self.context = context
        
        def shutdown(self):
            pass
        
        def can_handle(self, content: str) -> bool:
            return content.startswith("/mycommand")
        
        def execute(self, content: str, sender: str, target: str = None) -> str:
            return f"Processed: {content}"

    # Use the plugin manager
    ```
    manager = PluginManager()
    manager.add_plugin_path("./plugins")
    manager.load_all()
    manager.initialize_all()
    ```
    
    # Process commands
    result = manager.process_command("/mycommand test", "user1")

Legacy Compatibility:
--------------------

The old plugin interface is still supported through LoadPluginsLocally
and the legacy adapter. Old plugins will continue to work.

"""

from AloneChat.plugins.base import (
    PluginBase,
    CommandPluginBase,
    HandlerPluginBase,
    MiddlewarePluginBase,
    PluginMetadata,
    PluginInfo,
    PluginPriority,
    PluginState,
)
from AloneChat.plugins.context import (
    PluginContext,
    CommandContext,
)
from AloneChat.plugins.exceptions import (
    PluginError,
    PluginLoadError,
    PluginInitError,
    PluginDependencyError,
    PluginCircularDependencyError,
    PluginNotFoundError,
    PluginStateError,
    PluginValidationError,
    PluginRegistrationError,
    PluginConfigError,
)
from AloneChat.plugins.loader import (
    PluginLoader,
    LegacyPluginAdapter,
    load_legacy_plugins,
)
from AloneChat.plugins.manager import (
    PluginManager,
    create_plugin_manager,
)
from AloneChat.plugins.registry import PluginRegistry


def LoadPluginsLocally():
    """
    Legacy function for backward compatibility.
    
    Returns:
        Dictionary of legacy plugin specifications
    """
    from pathlib import Path
    
    plugins_dir = Path(__file__).parent
    return load_legacy_plugins(str(plugins_dir))


__all__ = [
    'PluginBase',
    'CommandPluginBase',
    'HandlerPluginBase',
    'MiddlewarePluginBase',
    'PluginMetadata',
    'PluginInfo',
    'PluginPriority',
    'PluginState',
    'PluginContext',
    'CommandContext',
    'PluginError',
    'PluginLoadError',
    'PluginInitError',
    'PluginDependencyError',
    'PluginCircularDependencyError',
    'PluginNotFoundError',
    'PluginStateError',
    'PluginValidationError',
    'PluginRegistrationError',
    'PluginConfigError',
    'PluginLoader',
    'LegacyPluginAdapter',
    'load_legacy_plugins',
    'PluginManager',
    'create_plugin_manager',
    'PluginRegistry',
    'LoadPluginsLocally',
]
