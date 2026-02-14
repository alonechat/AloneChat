"""
Plugin registry module.

Provides a centralized registry for tracking loaded plugins,
their states, and dependencies.
"""

import logging
from typing import Dict, List, Optional, Set, TYPE_CHECKING

from AloneChat.plugins.base import (
    PluginBase,
    PluginInfo,
    PluginState,
)
from AloneChat.plugins.exceptions import (
    PluginCircularDependencyError,
    PluginNotFoundError,
    PluginRegistrationError,
)

if TYPE_CHECKING:
    pass

logger = logging.getLogger(__name__)


class PluginRegistry:
    """
    Central registry for managing plugin information.
    
    The registry tracks all loaded plugins, their states, dependencies,
    and provides lookup capabilities.
    """
    
    def __init__(self):
        """Initialize the plugin registry."""
        self._plugins: Dict[str, PluginInfo] = {}
        self._plugins_by_tag: Dict[str, Set[str]] = {}
        self._plugins_by_provides: Dict[str, Set[str]] = {}
        self._dependency_graph: Dict[str, Set[str]] = {}
    
    def register(self, plugin: PluginBase, module_path: str = None) -> PluginInfo:
        """
        Register a plugin in the registry.
        
        Args:
            plugin: Plugin instance to register
            module_path: Optional path to the plugin module
            
        Returns:
            PluginInfo for the registered plugin
            
        Raises:
            PluginRegistrationError: If registration fails
        """
        metadata = plugin.metadata
        name = metadata.name
        
        if name in self._plugins:
            raise PluginRegistrationError(
                f"Plugin '{name}' is already registered",
                plugin_name=name
            )
        
        info = PluginInfo(
            metadata=metadata,
            state=PluginState.LOADED,
            module_path=module_path,
            instance=plugin
        )
        
        self._plugins[name] = info
        
        for tag in metadata.tags:
            if tag not in self._plugins_by_tag:
                self._plugins_by_tag[tag] = set()
            self._plugins_by_tag[tag].add(name)
        
        for provided in metadata.provides:
            if provided not in self._plugins_by_provides:
                self._plugins_by_provides[provided] = set()
            self._plugins_by_provides[provided].add(name)
        
        self._dependency_graph[name] = set(metadata.dependencies)
        
        logger.debug("Registered plugin: %s v%s", name, metadata.version)
        return info
    
    def unregister(self, name: str) -> Optional[PluginInfo]:
        """
        Unregister a plugin from the registry.
        
        Args:
            name: Name of the plugin to unregister
            
        Returns:
            Removed PluginInfo or None if not found
        """
        info = self._plugins.pop(name, None)
        if not info:
            return None
        
        metadata = info.metadata
        
        for tag in metadata.tags:
            if tag in self._plugins_by_tag:
                self._plugins_by_tag[tag].discard(name)
                if not self._plugins_by_tag[tag]:
                    del self._plugins_by_tag[tag]
        
        for provided in metadata.provides:
            if provided in self._plugins_by_provides:
                self._plugins_by_provides[provided].discard(name)
                if not self._plugins_by_provides[provided]:
                    del self._plugins_by_provides[provided]
        
        self._dependency_graph.pop(name, None)
        
        logger.debug("Unregistered plugin: %s", name)
        return info
    
    def get(self, name: str) -> Optional[PluginInfo]:
        """
        Get plugin info by name.
        
        Args:
            name: Plugin name
            
        Returns:
            PluginInfo or None if not found
        """
        return self._plugins.get(name)
    
    def get_instance(self, name: str) -> Optional[PluginBase]:
        """
        Get plugin instance by name.
        
        Args:
            name: Plugin name
            
        Returns:
            Plugin instance or None if not found
        """
        info = self._plugins.get(name)
        return info.instance if info else None
    
    def get_all(self) -> Dict[str, PluginInfo]:
        """
        Get all registered plugins.
        
        Returns:
            Dictionary of plugin name to PluginInfo
        """
        return self._plugins.copy()
    
    def get_by_tag(self, tag: str) -> List[PluginInfo]:
        """
        Get all plugins with a specific tag.
        
        Args:
            tag: Tag to search for
            
        Returns:
            List of PluginInfo objects
        """
        plugin_names = self._plugins_by_tag.get(tag, set())
        return [
            self._plugins[name]
            for name in plugin_names
            if name in self._plugins
        ]
    
    def get_by_provides(self, capability: str) -> List[PluginInfo]:
        """
        Get all plugins that provide a specific capability.
        
        Args:
            capability: Capability to search for
            
        Returns:
            List of PluginInfo objects
        """
        plugin_names = self._plugins_by_provides.get(capability, set())
        return [
            self._plugins[name]
            for name in plugin_names
            if name in self._plugins
        ]
    
    def get_by_state(self, state: PluginState) -> List[PluginInfo]:
        """
        Get all plugins in a specific state.
        
        Args:
            state: State to filter by
            
        Returns:
            List of PluginInfo objects
        """
        return [
            info for info in self._plugins.values()
            if info.state == state
        ]
    
    def update_state(self, name: str, state: PluginState, 
                     error_message: str = None) -> bool:
        """
        Update the state of a plugin.
        
        Args:
            name: Plugin name
            state: New state
            error_message: Optional error message
            
        Returns:
            True if state was updated, False if plugin not found
        """
        info = self._plugins.get(name)
        if not info:
            return False
        
        old_state = info.state
        info.state = state
        info.error_message = error_message
        
        logger.debug(
            "Plugin '%s' state changed: %s -> %s",
            name, old_state.value, state.value
        )
        return True
    
    def check_dependencies(self, name: str) -> List[str]:
        """
        Check if all dependencies for a plugin are satisfied.
        
        Args:
            name: Plugin name to check
            
        Returns:
            List of missing dependency names
            
        Raises:
            PluginNotFoundError: If plugin not found
        """
        if name not in self._plugins:
            raise PluginNotFoundError(f"Plugin '{name}' not found", plugin_name=name)
        
        info = self._plugins[name]
        missing = []
        
        for dep in info.metadata.dependencies:
            if dep not in self._plugins:
                missing.append(dep)
            elif self._plugins[dep].state != PluginState.ACTIVE:
                missing.append(dep)
        
        return missing
    
    def resolve_load_order(self) -> List[str]:
        """
        Resolve the order in which plugins should be loaded.
        
        Uses topological sort to ensure dependencies are loaded first.
        
        Returns:
            List of plugin names in load order
            
        Raises:
            PluginCircularDependencyError: If circular dependencies detected
        """
        visited = set()
        temp_visited = set()
        order = []
        
        def visit(name: str, path: List[str]):
            if name in temp_visited:
                cycle = path[path.index(name):] + [name]
                raise PluginCircularDependencyError(name, cycle)
            
            if name in visited:
                return
            
            temp_visited.add(name)
            
            for dep in self._dependency_graph.get(name, set()):
                if dep in self._plugins:
                    visit(dep, path + [name])
            
            temp_visited.remove(name)
            visited.add(name)
            order.append(name)
        
        for name in self._plugins:
            if name not in visited:
                visit(name, [])
        
        return order
    
    def get_dependents(self, name: str) -> List[str]:
        """
        Get all plugins that depend on the given plugin.
        
        Args:
            name: Plugin name
            
        Returns:
            List of dependent plugin names
        """
        dependents = []
        for plugin_name, deps in self._dependency_graph.items():
            if name in deps:
                dependents.append(plugin_name)
        return dependents
    
    def clear(self) -> None:
        """Clear all registered plugins."""
        self._plugins.clear()
        self._plugins_by_tag.clear()
        self._plugins_by_provides.clear()
        self._dependency_graph.clear()
        logger.debug("Plugin registry cleared")
    
    def __contains__(self, name: str) -> bool:
        """Check if a plugin is registered."""
        return name in self._plugins
    
    def __len__(self) -> int:
        """Get the number of registered plugins."""
        return len(self._plugins)
    
    def __iter__(self):
        """Iterate over plugin names."""
        return iter(self._plugins)
