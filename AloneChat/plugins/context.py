"""
Plugin context module.

Provides context objects that are passed to plugins during initialization
and execution, giving them access to system resources and services.
"""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from AloneChat.plugins.base import PluginBase
    from AloneChat.plugins.manager import PluginManager


@dataclass
class PluginContext:
    """
    Context provided to plugins during initialization.
    
    This class provides plugins with access to system resources,
    configuration, and other plugins through a controlled interface.
    
    Attributes:
        plugin_name: Name of the plugin receiving this context
        config: Plugin-specific configuration
        data_dir: Directory for plugin data storage
        logger: Logger instance for the plugin
        services: Dictionary of available services
    """
    
    plugin_name: str
    config: Dict[str, Any] = field(default_factory=dict)
    data_dir: Optional[str] = None
    logger: Optional[Any] = None
    services: Dict[str, Any] = field(default_factory=dict)
    
    _manager: Optional["PluginManager"] = field(default=None, repr=False)
    _event_handlers: Dict[str, List[Callable]] = field(
        default_factory=lambda: {}, repr=False
    )
    
    def get_service(self, service_name: str) -> Optional[Any]:
        """
        Get a service by name.
        
        Args:
            service_name: Name of the service
            
        Returns:
            Service instance or None if not found
        """
        return self.services.get(service_name)
    
    def register_service(self, service_name: str, service: Any) -> None:
        """
        Register a service provided by this plugin.
        
        Args:
            service_name: Name of the service
            service: Service instance
        """
        self.services[service_name] = service
        if self._manager:
            self._manager._register_service(self.plugin_name, service_name, service)
    
    def get_plugin(self, plugin_name: str) -> Optional["PluginBase"]:
        """
        Get another plugin by name.
        
        Args:
            plugin_name: Name of the plugin to get
            
        Returns:
            Plugin instance or None if not found
        """
        if self._manager:
            return self._manager.get_plugin(plugin_name)
        return None
    
    def get_config(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value.
        
        Args:
            key: Configuration key
            default: Default value if key not found
            
        Returns:
            Configuration value or default
        """
        return self.config.get(key, default)
    
    def log(self, level: str, message: str, *args) -> None:
        """
        Log a message using the plugin's logger.
        
        Args:
            level: Log level (debug, info, warning, error)
            message: Log message
            *args: Format arguments
        """
        if self.logger:
            log_method = getattr(self.logger, level, None)
            if log_method:
                log_method(message, *args)
    
    def on_event(self, event_name: str, handler: Callable) -> None:
        """
        Register an event handler.
        
        Args:
            event_name: Name of the event
            handler: Handler function
        """
        if event_name not in self._event_handlers:
            self._event_handlers[event_name] = []
        self._event_handlers[event_name].append(handler)
        
        if self._manager:
            self._manager._register_event_handler(
                self.plugin_name, event_name, handler
            )
    
    def emit_event(self, event_name: str, *args, **kwargs) -> None:
        """
        Emit an event to all registered handlers.
        
        Args:
            event_name: Name of the event
            *args: Event arguments
            **kwargs: Event keyword arguments
        """
        if self._manager:
            self._manager._emit_event(event_name, *args, **kwargs)


@dataclass
class CommandContext:
    """
    Context for command execution.
    
    Provides information about the command being executed and
    methods for creating responses.
    """
    
    content: str
    sender: str
    target: Optional[str] = None
    original_message: Optional[Any] = None
    plugin_context: Optional[PluginContext] = None
    
    def reply(self, content: str, message_type: Any = None) -> Any:
        """
        Create a reply message.
        
        Args:
            content: Reply content
            message_type: Optional message type
            
        Returns:
            Message object
        """
        from AloneChat.core.message.protocol import Message, MessageType
        
        msg_type = message_type or MessageType.TEXT
        return Message(msg_type, "SERVER", content, target=self.sender)
    
    def transform(self, new_content: str) -> "CommandContext":
        """
        Create a new context with transformed content.
        
        Args:
            new_content: New content string
            
        Returns:
            New CommandContext with updated content
        """
        return CommandContext(
            content=new_content,
            sender=self.sender,
            target=self.target,
            original_message=self.original_message,
            plugin_context=self.plugin_context
        )
