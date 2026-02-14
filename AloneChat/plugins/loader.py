"""
Plugin loader module.

Handles discovering, loading, and validating plugins from the filesystem.
"""

import importlib.util
import logging
import sys
from pathlib import Path
from typing import Dict, List, Optional, Type

from AloneChat.plugins.base import (
    PluginBase,
    CommandPluginBase,
    PluginMetadata,
)
from AloneChat.plugins.exceptions import (
    PluginLoadError,
)
from AloneChat.plugins.registry import PluginRegistry

logger = logging.getLogger(__name__)


class PluginLoader:
    """
    Discovers and loads plugins from the filesystem.
    
    Supports loading plugins from:
    - Local directories
    - Python packages
    - Entry points (future)
    """
    
    PLUGIN_CLASS_NAME = "Plugin"
    PLUGIN_METADATA_ATTR = "_metadata"
    
    def __init__(self, registry: Optional[PluginRegistry] = None):
        """
        Initialize the plugin loader.
        
        Args:
            registry: Plugin registry to use (creates new if not provided)
        """
        self._registry = registry or PluginRegistry()
        self._search_paths: List[Path] = []
    
    @property
    def registry(self) -> PluginRegistry:
        """Get the plugin registry."""
        return self._registry
    
    def add_search_path(self, path: str | Path) -> None:
        """
        Add a path to search for plugins.
        
        Args:
            path: Directory path to add
        """
        path = Path(path)
        if path not in self._search_paths:
            self._search_paths.append(path)
            logger.debug("Added plugin search path: %s", path)
    
    def discover_plugins(self, path: str | Path = None) -> List[Dict]:
        """
        Discover available plugins in the given path.
        
        Args:
            path: Directory to search (uses search_paths if not provided)
            
        Returns:
            List of plugin discovery information dictionaries
        """
        discovered = []
        
        if path:
            paths = [Path(path)]
        else:
            paths = self._search_paths
        
        for search_path in paths:
            if not search_path.exists():
                logger.warning("Plugin search path does not exist: %s", search_path)
                continue
            
            for item in search_path.iterdir():
                if item.is_file() and item.suffix == ".py":
                    if item.stem.startswith("_"):
                        continue
                    
                    plugin_info = self._inspect_module(item)
                    if plugin_info:
                        discovered.append(plugin_info)
                        
                elif item.is_dir():
                    init_file = item / "__init__.py"
                    if init_file.exists():
                        plugin_info = self._inspect_package(item)
                        if plugin_info:
                            discovered.append(plugin_info)
        
        logger.info("Discovered %d plugins", len(discovered))
        return discovered
    
    def _inspect_module(self, module_path: Path) -> Optional[Dict]:
        """
        Inspect a Python module for plugin classes.
        
        Args:
            module_path: Path to the module file
            
        Returns:
            Plugin discovery info or None
        """
        try:
            spec = importlib.util.spec_from_file_location(
                module_path.stem, module_path
            )
            if not spec or not spec.loader:
                return None
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[module_path.stem] = module
            
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                logger.debug("Failed to load module %s: %s", module_path, e)
                return None
            
            plugin_class = self._find_plugin_class(module)
            if plugin_class:
                return {
                    "name": plugin_class.get_name(),
                    "module_path": str(module_path),
                    "module_name": module_path.stem,
                    "plugin_class": plugin_class,
                    "metadata": plugin_class.metadata,
                }
            
        except Exception as e:
            logger.debug("Error inspecting module %s: %s", module_path, e)
        
        return None
    
    def _inspect_package(self, package_path: Path) -> Optional[Dict]:
        """
        Inspect a Python package for plugin classes.
        
        Args:
            package_path: Path to the package directory
            
        Returns:
            Plugin discovery info or None
        """
        try:
            init_path = package_path / "__init__.py"
            spec = importlib.util.spec_from_file_location(
                package_path.name, init_path,
                submodule_search_locations=[str(package_path)]
            )
            if not spec or not spec.loader:
                return None
            
            module = importlib.util.module_from_spec(spec)
            sys.modules[package_path.name] = module
            
            try:
                spec.loader.exec_module(module)
            except Exception as e:
                logger.debug("Failed to load package %s: %s", package_path, e)
                return None
            
            plugin_class = self._find_plugin_class(module)
            if plugin_class:
                return {
                    "name": plugin_class.get_name(),
                    "module_path": str(package_path),
                    "module_name": package_path.name,
                    "plugin_class": plugin_class,
                    "metadata": plugin_class.metadata,
                }
            
        except Exception as e:
            logger.debug("Error inspecting package %s: %s", package_path, e)
        
        return None
    
    def _find_plugin_class(self, module) -> Optional[Type[PluginBase]]:
        """
        Find a plugin class in a module.
        
        Args:
            module: Python module to search
            
        Returns:
            Plugin class or None
        """
        excluded_names = {
            'PluginBase',
            'CommandPluginBase',
            'HandlerPluginBase',
            'MiddlewarePluginBase',
            'LegacyPluginAdapter',
            'PluginHandler',
        }
        
        for name in dir(module):
            obj = getattr(module, name)
            
            if not isinstance(obj, type):
                continue
            
            if not issubclass(obj, PluginBase):
                continue
            
            if obj.__name__ in excluded_names:
                continue
            
            try:
                import inspect
                sig = inspect.signature(obj.__init__)
                required_params = [
                    p for p in sig.parameters.values()
                    if p.default is inspect.Parameter.empty
                    and p.kind not in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
                ]
                if len(required_params) > 1:
                    continue
            except Exception:
                pass
            
            if hasattr(obj, self.PLUGIN_METADATA_ATTR):
                return obj
            
            if name == self.PLUGIN_CLASS_NAME:
                return obj
        
        return None
    
    def load_plugin(self, plugin_info: Dict) -> PluginBase:
        """
        Load a plugin from discovery info.
        
        Args:
            plugin_info: Plugin discovery information
            
        Returns:
            Loaded plugin instance
            
        Raises:
            PluginLoadError: If loading fails
        """
        try:
            plugin_class: Type[PluginBase] = plugin_info["plugin_class"]
            instance = plugin_class()
            
            self._registry.register(
                instance,
                module_path=plugin_info.get("module_path")
            )
            
            logger.info(
                "Loaded plugin: %s v%s",
                plugin_info["name"],
                plugin_info["metadata"].version
            )
            return instance
            
        except Exception as e:
            raise PluginLoadError(
                f"Failed to load plugin: {e}",
                plugin_name=plugin_info.get("name", "unknown")
            ) from e
    
    def load_from_directory(
        self,
        directory: str | Path,
        auto_register: bool = True
    ) -> List[PluginBase]:
        """
        Load all plugins from a directory.
        
        Args:
            directory: Directory to load plugins from
            auto_register: Whether to automatically register plugins
            
        Returns:
            List of loaded plugin instances
        """
        directory = Path(directory)
        discovered = self.discover_plugins(directory)
        loaded = []
        
        for plugin_info in discovered:
            try:
                instance = self.load_plugin(plugin_info)
                loaded.append(instance)
            except PluginLoadError as e:
                logger.error("Failed to load plugin: %s", e)
        
        return loaded
    
    def load_from_entry_points(self, group: str = "alonechat.plugins") -> List[PluginBase]:
        """
        Load plugins from package entry points.
        
        Args:
            group: Entry point group name
            
        Returns:
            List of loaded plugin instances
        """
        loaded = []
        
        try:
            import importlib.metadata
            
            entry_points = importlib.metadata.entry_points()
            
            if hasattr(entry_points, 'select'):
                eps = entry_points.select(group=group)
            else:
                eps = entry_points.get(group, [])
            
            for ep in eps:
                try:
                    plugin_class = ep.load()
                    
                    if not (isinstance(plugin_class, type) and 
                            issubclass(plugin_class, PluginBase)):
                        logger.warning(
                            "Entry point %s does not reference a Plugin class",
                            ep.name
                        )
                        continue
                    
                    instance = plugin_class()
                    self._registry.register(instance)
                    loaded.append(instance)
                    
                    logger.info(
                        "Loaded plugin from entry point: %s",
                        ep.name
                    )
                    
                except Exception as e:
                    logger.error(
                        "Failed to load plugin from entry point %s: %s",
                        ep.name, e
                    )
                    
        except ImportError:
            logger.debug("importlib.metadata not available")
        
        return loaded
    
    @staticmethod
    def validate_plugin(plugin: PluginBase) -> List[str]:
        """
        Validate a plugin instance.
        
        Args:
            plugin: Plugin instance to validate
            
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        metadata = plugin.metadata
        
        if not metadata.name:
            errors.append("Plugin name is required")
        elif not isinstance(metadata.name, str):
            errors.append("Plugin name must be a string")
        
        if not metadata.version:
            errors.append("Plugin version is required")
        
        try:
            plugin.initialize(EmptyContext())
        except NotImplementedError:
            errors.append("Plugin must implement initialize() method")
        except Exception:
            pass
        
        try:
            plugin.shutdown()
        except NotImplementedError:
            errors.append("Plugin must implement shutdown() method")
        except Exception:
            pass
        
        return errors


class EmptyContext:
    """Empty context for plugin validation."""
    pass


class LegacyPluginAdapter(CommandPluginBase):
    """
    Adapter for legacy plugins that use the old Plugin interface.
    
    This allows backward compatibility with plugins written for the
    old plugin system.
    """
    
    _metadata = PluginMetadata(
        name="legacy_adapter",
        version="1.0.0",
        description="Legacy plugin adapter"
    )
    
    def __init__(self, legacy_plugin, name: str = None):
        """
        Initialize adapter with a legacy plugin.
        
        Args:
            legacy_plugin: Legacy plugin instance
            name: Optional plugin name override
        """
        self._legacy_plugin = legacy_plugin
        self._name = name or getattr(legacy_plugin, 'name', 'legacy')
        self._metadata = PluginMetadata(
            name=self._name,
            version=getattr(legacy_plugin, 'version', '1.0.0'),
            description=getattr(legacy_plugin, 'description', ''),
        )
    
    def initialize(self, context) -> None:
        """Initialize the legacy plugin."""
        if hasattr(self._legacy_plugin, 'initialize'):
            self._legacy_plugin.initialize(context)
    
    def shutdown(self) -> None:
        """Shutdown the legacy plugin."""
        if hasattr(self._legacy_plugin, 'shutdown'):
            self._legacy_plugin.shutdown()
    
    def can_handle(self, content: str) -> bool:
        """Check if legacy plugin can handle content."""
        if hasattr(self._legacy_plugin, 'can_handle'):
            return self._legacy_plugin.can_handle(content)
        return True
    
    def execute(self, content: str, sender: str, target: str = None) -> str:
        """Execute legacy plugin."""
        if hasattr(self._legacy_plugin, 'execute'):
            return self._legacy_plugin.execute(content, sender, target)
        if hasattr(self._legacy_plugin, '__call__'):
            return self._legacy_plugin(content)
        return content


def load_legacy_plugins(directory: str) -> Dict[str, Dict]:
    """
    Load plugins using the legacy format for backward compatibility.
    
    Args:
        directory: Directory containing legacy plugins
        
    Returns:
        Dictionary of plugin name to plugin specification
    """
    plugins = {}
    directory_path = Path(directory)
    
    if not directory_path.exists():
        logger.warning("Legacy plugin directory does not exist: %s", directory)
        return plugins
    
    sys.path.insert(0, str(directory_path.parent))
    
    for item in directory_path.iterdir():
        if item.is_file() and item.suffix == ".py" and not item.stem.startswith("_"):
            try:
                spec = importlib.util.spec_from_file_location(item.stem, item)
                if spec and spec.loader:
                    module = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(module)
                    
                    if hasattr(module, 'PluginImpl'):
                        plugins[item.stem] = {
                            "type": "command",
                            "handler": module.PluginImpl,
                            "name": item.stem,
                        }
                        logger.debug("Loaded legacy plugin: %s", item.stem)
                        
            except Exception as e:
                logger.error("Failed to load legacy plugin %s: %s", item, e)
    
    return plugins
