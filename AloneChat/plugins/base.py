"""
Base classes and interfaces for the plugin system.

This module provides the abstract base classes that all plugins must implement,
along with metadata classes for plugin configuration.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, List, Optional, Set


class PluginState(Enum):
    """Lifecycle states for plugins."""
    UNLOADED = "unloaded"
    LOADED = "loaded"
    INITIALIZED = "initialized"
    ACTIVE = "active"
    DISABLED = "disabled"
    ERROR = "error"


class PluginPriority(Enum):
    """Priority levels for plugin execution order."""
    HIGHEST = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    LOWEST = 4


@dataclass
class PluginMetadata:
    """
    Metadata describing a plugin.
    
    Attributes:
        name: Unique identifier for the plugin
        version: Plugin version string
        description: Human-readable description
        author: Plugin author
        priority: Execution priority
        dependencies: List of required plugin names
        optional_dependencies: List of optional plugin names
        provides: List of capabilities this plugin provides
        tags: Classification tags for the plugin
        enabled: Whether the plugin is enabled by default
    """
    name: str
    version: str = "1.0.0"
    description: str = ""
    author: str = ""
    priority: PluginPriority = PluginPriority.NORMAL
    dependencies: List[str] = field(default_factory=list)
    optional_dependencies: List[str] = field(default_factory=list)
    provides: List[str] = field(default_factory=list)
    tags: Set[str] = field(default_factory=set)
    enabled: bool = True


@dataclass
class PluginInfo:
    """
    Runtime information about a loaded plugin.
    
    Attributes:
        metadata: Plugin metadata
        state: Current plugin state
        module_path: Path to the plugin module
        error_message: Error message if state is ERROR
        load_time: Timestamp when plugin was loaded
        instance: Reference to plugin instance
    """
    metadata: PluginMetadata
    state: PluginState = PluginState.UNLOADED
    module_path: Optional[str] = None
    error_message: Optional[str] = None
    load_time: Optional[float] = None
    instance: Optional["PluginBase"] = None


class PluginBase(ABC):
    """
    Abstract base class for all plugins.
    
    All plugins must inherit from this class and implement its abstract methods.
    The plugin system provides lifecycle management through these methods.
    """
    
    _metadata: PluginMetadata = PluginMetadata(name="base")

    # noinspection PyPropertyDefinition
    @classmethod
    @property
    def metadata(cls) -> PluginMetadata:
        """Get plugin metadata."""
        return cls._metadata
    
    @classmethod
    def get_name(cls) -> str:
        """Get plugin name."""
        return cls._metadata.name
    
    @classmethod
    def get_version(cls) -> str:
        """Get plugin version."""
        return cls._metadata.version
    
    @abstractmethod
    def initialize(self, context: "PluginContext") -> None:
        """
        Initialize the plugin with the given context.
        
        Called once when the plugin is loaded. Use this to set up
        resources, register handlers, and prepare the plugin for use.
        
        Args:
            context: Plugin context providing access to system resources
        """
        pass
    
    @abstractmethod
    def shutdown(self) -> None:
        """
        Clean up plugin resources.
        
        Called when the plugin is being unloaded. Release any resources,
        unregister handlers, and prepare for removal.
        """
        pass
    
    def on_enable(self) -> None:
        """Called when the plugin is enabled."""
        pass
    
    def on_disable(self) -> None:
        """Called when the plugin is disabled."""
        pass
    
    def on_error(self, error: Exception) -> None:
        """
        Called when an error occurs during plugin execution.
        
        Args:
            error: The exception that occurred
        """
        pass


class CommandPluginBase(PluginBase):
    """
    Base class for plugins that provide command functionality.
    
    Command plugins can process user input and transform messages.
    """
    
    @abstractmethod
    def can_handle(self, content: str) -> bool:
        """
        Check if this plugin can handle the given content.
        
        Args:
            content: Input content to check
            
        Returns:
            True if this plugin can process the content
        """
        pass
    
    @abstractmethod
    def execute(self, content: str, sender: str, target: Optional[str] = None) -> str:
        """
        Execute the plugin's functionality.
        
        Args:
            content: Input content to process
            sender: Username of the message sender
            target: Optional target user
            
        Returns:
            Transformed content string
        """
        pass


class HandlerPluginBase(PluginBase):
    """
    Base class for plugins that provide message handlers.
    
    Handler plugins can intercept and process messages at various stages.
    """
    
    @abstractmethod
    def handle(self, message: Any, context: "PluginContext") -> Optional[Any]:
        """
        Handle a message.
        
        Args:
            message: Message to handle
            context: Plugin context
            
        Returns:
            Modified message or None to stop processing
        """
        pass


class MiddlewarePluginBase(PluginBase):
    """
    Base class for middleware plugins.
    
    Middleware plugins can intercept and modify the message pipeline.
    """
    
    @abstractmethod
    def process(self, data: Any, next_handler: Callable) -> Any:
        """
        Process data through the middleware chain.
        
        Args:
            data: Data to process
            next_handler: Next handler in the chain
            
        Returns:
            Processed data
        """
        pass
