"""
Plugin manager module.

Provides the main interface for managing plugins throughout their lifecycle,
including loading, initialization, activation, and shutdown.
"""

import logging
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional

from AloneChat.plugins.base import (
    PluginBase,
    CommandPluginBase,
    PluginMetadata,
    PluginState,
)
from AloneChat.plugins.context import PluginContext
from AloneChat.plugins.exceptions import (
    PluginDependencyError,
    PluginError,
    PluginInitError,
    PluginNotFoundError,
    PluginStateError,
)
from AloneChat.plugins.loader import PluginLoader, load_legacy_plugins
from AloneChat.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


class PluginManager:
    """
    Main interface for plugin management.
    
    Handles the complete plugin lifecycle:
    - Discovery and loading
    - Dependency resolution
    - Initialization and activation
    - Configuration management
    - Event handling
    - Shutdown and cleanup
    
    Example usage:
        ```
        manager = PluginManager()
        manager.add_plugin_path("./plugins")
        manager.load_all()
        manager.initialize_all()
        
        # Use plugins
        manager.process_command("/help", "user1")
        
        # Cleanup
        manager.shutdown_all()
        ```
    """
    
    def __init__(self, config: Dict[str, Any] = None):
        """
        Initialize the plugin manager.
        
        Args:
            config: Optional configuration dictionary
        """
        self._config = config or {}
        self._registry = PluginRegistry()
        self._loader = PluginLoader(self._registry)
        self._contexts: Dict[str, PluginContext] = {}
        self._services: Dict[str, Dict[str, Any]] = {}
        self._event_handlers: Dict[str, Dict[str, List[Callable]]] = {}
        self._plugin_paths: List[Path] = []
        self._initialized = False
    
    @property
    def registry(self) -> PluginRegistry:
        """Get the plugin registry."""
        return self._registry
    
    @property
    def loader(self) -> PluginLoader:
        """Get the plugin loader."""
        return self._loader
    
    def add_plugin_path(self, path: str | Path) -> None:
        """
        Add a path to search for plugins.
        
        Args:
            path: Directory path to add
        """
        path = Path(path)
        self._plugin_paths.append(path)
        self._loader.add_search_path(path)
    
    def set_config(self, plugin_name: str, config: Dict[str, Any]) -> None:
        """
        Set configuration for a specific plugin.
        
        Args:
            plugin_name: Name of the plugin
            config: Configuration dictionary
        """
        if plugin_name not in self._config:
            self._config[plugin_name] = {}
        self._config[plugin_name].update(config)
    
    def get_config(self, plugin_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific plugin.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            Configuration dictionary
        """
        return self._config.get(plugin_name, {})
    
    def discover(self) -> List[Dict]:
        """
        Discover all available plugins.
        
        Returns:
            List of discovered plugin information
        """
        all_discovered = []
        for path in self._plugin_paths:
            discovered = self._loader.discover_plugins(path)
            all_discovered.extend(discovered)
        return all_discovered
    
    def load_plugin(self, plugin_info: Dict) -> PluginBase:
        """
        Load a single plugin.
        
        Args:
            plugin_info: Plugin discovery information
            
        Returns:
            Loaded plugin instance
            
        Raises:
            PluginLoadError: If loading fails
        """
        return self._loader.load_plugin(plugin_info)
    
    def load_all(self) -> List[PluginBase]:
        """
        Load all discovered plugins.
        
        Returns:
            List of loaded plugin instances
        """
        loaded = []
        
        for path in self._plugin_paths:
            try:
                plugins = self._loader.load_from_directory(path)
                loaded.extend(plugins)
            except Exception as e:
                logger.error("Failed to load plugins from %s: %s", path, e)
        
        logger.info("Loaded %d plugins", len(loaded))
        return loaded
    
    @staticmethod
    def load_legacy(directory: str) -> Dict[str, Dict]:
        """
        Load plugins using the legacy format.
        
        Args:
            directory: Directory containing legacy plugins
            
        Returns:
            Dictionary of plugin specifications
        """
        return load_legacy_plugins(directory)
    
    def initialize_plugin(self, name: str) -> None:
        """
        Initialize a specific plugin.
        
        Args:
            name: Name of the plugin to initialize
            
        Raises:
            PluginNotFoundError: If plugin not found
            PluginInitError: If initialization fails
            PluginDependencyError: If dependencies not met
        """
        info = self._registry.get(name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{name}' not found", plugin_name=name)
        
        if info.state == PluginState.INITIALIZED or info.state == PluginState.ACTIVE:
            return
        
        missing = self._registry.check_dependencies(name)
        if missing:
            raise PluginDependencyError(name, missing[0])
        
        try:
            context = self._create_context(name)
            self._contexts[name] = context
            
            info.instance.initialize(context)
            self._registry.update_state(name, PluginState.INITIALIZED)
            
            logger.info("Initialized plugin: %s", name)
            
        except Exception as e:
            self._registry.update_state(name, PluginState.ERROR, str(e))
            raise PluginInitError(
                f"Failed to initialize plugin: {e}",
                plugin_name=name
            ) from e
    
    def initialize_all(self) -> None:
        """
        Initialize all loaded plugins in dependency order.
        
        Raises:
            PluginInitError: If any plugin fails to initialize
        """
        load_order = self._registry.resolve_load_order()
        
        for name in load_order:
            info = self._registry.get(name)
            if info and info.state == PluginState.LOADED:
                if info.metadata.enabled:
                    try:
                        self.initialize_plugin(name)
                    except PluginError as e:
                        logger.error("Failed to initialize plugin %s: %s", name, e)
                        if name in [p.name for p in self._get_required_plugins()]:
                            raise
                else:
                    self._registry.update_state(name, PluginState.DISABLED)
        
        self._initialized = True
        logger.info("All plugins initialized")
    
    def activate_plugin(self, name: str) -> None:
        """
        Activate a plugin.
        
        Args:
            name: Name of the plugin to activate
        """
        info = self._registry.get(name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{name}' not found", plugin_name=name)
        
        if info.state != PluginState.INITIALIZED:
            raise PluginStateError(
                f"Plugin must be initialized before activation (current: {info.state.value})",
                plugin_name=name
            )
        
        try:
            info.instance.on_enable()
            self._registry.update_state(name, PluginState.ACTIVE)
            logger.info("Activated plugin: %s", name)
            
        except Exception as e:
            self._registry.update_state(name, PluginState.ERROR, str(e))
            raise
    
    def deactivate_plugin(self, name: str) -> None:
        """
        Deactivate a plugin.
        
        Args:
            name: Name of the plugin to deactivate
        """
        info = self._registry.get(name)
        if not info:
            return
        
        if info.state == PluginState.ACTIVE:
            try:
                info.instance.on_disable()
                self._registry.update_state(name, PluginState.INITIALIZED)
                logger.info("Deactivated plugin: %s", name)
                
            except Exception as e:
                logger.error("Failed to deactivate plugin %s: %s", name, e)
    
    def shutdown_plugin(self, name: str) -> None:
        """
        Shutdown a specific plugin.
        
        Args:
            name: Name of the plugin to shut down
        """
        info = self._registry.get(name)
        if not info:
            return
        
        if info.state in (PluginState.ACTIVE, PluginState.INITIALIZED):
            try:
                if info.state == PluginState.ACTIVE:
                    info.instance.on_disable()
                info.instance.shutdown()
                
            except Exception as e:
                logger.error("Error during plugin shutdown %s: %s", name, e)
            finally:
                self._registry.update_state(name, PluginState.UNLOADED)
                self._contexts.pop(name, None)
                logger.info("Shutdown plugin: %s", name)
    
    def shutdown_all(self) -> None:
        """Shutdown all plugins in reverse dependency order."""
        load_order = self._registry.resolve_load_order()
        shutdown_order = list(reversed(load_order))
        
        for name in shutdown_order:
            self.shutdown_plugin(name)
        
        self._registry.clear()
        self._contexts.clear()
        self._services.clear()
        self._event_handlers.clear()
        self._initialized = False
        
        logger.info("All plugins shut down")
    
    def reload_plugin(self, name: str) -> None:
        """
        Reload a plugin.
        
        Args:
            name: Name of the plugin to reload
        """
        info = self._registry.get(name)
        if not info:
            raise PluginNotFoundError(f"Plugin '{name}' not found", plugin_name=name)
        
        module_path = info.module_path
        
        self.shutdown_plugin(name)
        self._registry.unregister(name)
        
        if module_path:
            discovered = self._loader.discover_plugins(Path(module_path).parent)
            for plugin_info in discovered:
                if plugin_info["name"] == name:
                    self._loader.load_plugin(plugin_info)
                    self.initialize_plugin(name)
                    break
    
    def get_plugin(self, name: str) -> Optional[PluginBase]:
        """
        Get a plugin instance by name.
        
        Args:
            name: Plugin name
            
        Returns:
            Plugin instance or None
        """
        return self._registry.get_instance(name)
    
    def get_plugins_by_tag(self, tag: str) -> List[PluginBase]:
        """
        Get all plugins with a specific tag.
        
        Args:
            tag: Tag to search for
            
        Returns:
            List of plugin instances
        """
        infos = self._registry.get_by_tag(tag)
        return [info.instance for info in infos if info.instance]
    
    def get_plugins_by_state(self, state: PluginState) -> List[PluginBase]:
        """
        Get all plugins in a specific state.
        
        Args:
            state: State to filter by
            
        Returns:
            List of plugin instances
        """
        infos = self._registry.get_by_state(state)
        return [info.instance for info in infos if info.instance]
    
    def get_command_plugins(self) -> List[CommandPluginBase]:
        """
        Get all command plugins.
        
        Returns:
            List of command plugin instances
        """
        plugins = []
        for info in self._registry.get_all().values():
            if (info.state == PluginState.ACTIVE and 
                isinstance(info.instance, CommandPluginBase)):
                plugins.append(info.instance)
        
        plugins.sort(key=lambda p: p.metadata.priority.value)
        return plugins
    
    def process_command(
        self,
        content: str,
        sender: str,
        target: str = None
    ) -> str:
        """
        Process content through command plugins.
        
        Args:
            content: Input content to process
            sender: Username of the sender
            target: Optional target user
            
        Returns:
            Processed content
        """
        result = content
        
        for plugin in self.get_command_plugins():
            try:
                if plugin.can_handle(result):
                    result = plugin.execute(result, sender, target)
            except Exception as e:
                logger.error(
                    "Error in command plugin %s: %s",
                    plugin.get_name(), e
                )
        
        return result
    
    def _create_context(self, plugin_name: str) -> PluginContext:
        """
        Create a context for a plugin.
        
        Args:
            plugin_name: Name of the plugin
            
        Returns:
            PluginContext instance
        """
        return PluginContext(
            plugin_name=plugin_name,
            config=self.get_config(plugin_name),
            logger=logging.getLogger(f"plugin.{plugin_name}"),
            services=self._get_all_services(),
            _manager=self
        )
    
    def _register_service(
        self,
        plugin_name: str,
        service_name: str,
        service: Any
    ) -> None:
        """
        Register a service provided by a plugin.
        
        Args:
            plugin_name: Name of the plugin providing the service
            service_name: Name of the service
            service: Service instance
        """
        if plugin_name not in self._services:
            self._services[plugin_name] = {}
        self._services[plugin_name][service_name] = service
    
    def _get_all_services(self) -> Dict[str, Any]:
        """Get all registered services."""
        all_services = {}
        for plugin_services in self._services.values():
            all_services.update(plugin_services)
        return all_services
    
    def _register_event_handler(
        self,
        plugin_name: str,
        event_name: str,
        handler: Callable
    ) -> None:
        """
        Register an event handler for a plugin.
        
        Args:
            plugin_name: Name of the plugin
            event_name: Name of the event
            handler: Handler function
        """
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = {}
        if plugin_name not in self._event_handlers[event_name]:
            self._event_handlers[event_name][plugin_name] = []
        self._event_handlers[event_name][plugin_name].append(handler)
    
    def _emit_event(self, event_name: str, *args, **kwargs) -> None:
        """
        Emit an event to all registered handlers.
        
        Args:
            event_name: Name of the event
            *args: Event arguments
            **kwargs: Event keyword arguments
        """
        handlers = self._event_handlers.get(event_name, {})
        for plugin_name, plugin_handlers in handlers.items():
            for handler in plugin_handlers:
                try:
                    handler(*args, **kwargs)
                except Exception as e:
                    logger.error(
                        "Error in event handler for %s in plugin %s: %s",
                        event_name, plugin_name, e
                    )
    
    def _get_required_plugins(self) -> List[PluginMetadata]:
        """Get list of plugins marked as required."""
        required = []
        for info in self._registry.get_all().values():
            if info.metadata.enabled:
                required.append(info.metadata)
        return required
    
    def __enter__(self):
        """Context manager entry."""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.shutdown_all()
        return False
    
    def __contains__(self, name: str) -> bool:
        """Check if a plugin is registered."""
        return name in self._registry
    
    def __len__(self) -> int:
        """Get the number of registered plugins."""
        return len(self._registry)


def create_plugin_manager(
    plugin_paths: List[str] = None,
    config: Dict[str, Any] = None,
    auto_load: bool = True,
    auto_init: bool = True
) -> PluginManager:
    """
    Factory function to create and configure a plugin manager.
    
    Args:
        plugin_paths: List of paths to search for plugins
        config: Configuration dictionary
        auto_load: Whether to automatically load plugins
        auto_init: Whether to automatically initialize plugins
        
    Returns:
        Configured PluginManager instance
    """
    manager = PluginManager(config)
    
    if plugin_paths:
        for path in plugin_paths:
            manager.add_plugin_path(path)
    
    if auto_load:
        manager.load_all()
    
    if auto_init and auto_load:
        manager.initialize_all()
    
    return manager
