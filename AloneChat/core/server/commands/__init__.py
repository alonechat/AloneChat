"""
Command processing system for the server.

Provides a modular and extensible command architecture with
support for plugins and custom command handlers.

This module integrates the new plugin system with the command processing
architecture, providing both new interfaces and backward compatibility.
"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum
from typing import Dict, List, Optional, Callable

from AloneChat.core.message.protocol import Message, MessageType
from AloneChat.plugins import (
    PluginManager,
    CommandPluginBase,
    create_plugin_manager,
)

logger = logging.getLogger(__name__)


class CommandPriority(Enum):
    """Priority levels for command execution order."""
    HIGHEST = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3
    LOWEST = 4


@dataclass
class CommandContext:
    """Context passed to command handlers."""
    content: str
    sender: str
    target: Optional[str]
    original_message: Optional[Message] = None
    
    def reply(self, content: str, message_type: MessageType = MessageType.TEXT) -> Message:
        """Create a reply message."""
        return Message(message_type, "SERVER", content, target=self.sender)


class CommandHandler(ABC):
    """
    Abstract base class for command handlers.
    
    Implement this class to create custom commands.
    """
    
    name: str = ""
    description: str = ""
    aliases: List[str] = []
    priority: CommandPriority = CommandPriority.NORMAL
    
    @abstractmethod
    def can_handle(self, context: CommandContext) -> bool:
        """
        Check if this handler can process the given context.
        
        Args:
            context: Command context
            
        Returns:
            True if this handler can process the command
        """
        pass
    
    @abstractmethod
    def execute(self, context: CommandContext) -> Optional[Message]:
        """
        Execute the command.
        
        Args:
            context: Command context
            
        Returns:
            Response message or None if no response needed
        """
        pass
    
    def get_help(self) -> str:
        """Get help text for this command."""
        return f"{self.name}: {self.description}"


class CommandRegistry:
    """
    Registry for command handlers.
    
    Manages command handlers and provides lookup capabilities.
    """
    
    def __init__(self):
        """Initialize command registry."""
        self._handlers: List[CommandHandler] = []
        self._handlers_by_name: Dict[str, CommandHandler] = {}
    
    def register(self, handler: CommandHandler) -> None:
        """
        Register a command handler.
        
        Args:
            handler: Command handler to register
        """
        self._handlers.append(handler)
        self._handlers_by_name[handler.name] = handler
        
        for alias in handler.aliases:
            self._handlers_by_name[alias] = handler
        
        self._handlers.sort(key=lambda h: h.priority.value)
        
        logger.debug("Registered command handler: %s", handler.name)
    
    def unregister(self, name: str) -> Optional[CommandHandler]:
        """
        Unregister a command handler.
        
        Args:
            name: Command name or alias
            
        Returns:
            Removed handler or None
        """
        handler = self._handlers_by_name.pop(name, None)
        if handler:
            self._handlers.remove(handler)
            
            for alias in handler.aliases:
                self._handlers_by_name.pop(alias, None)
            
            logger.debug("Unregistered command handler: %s", handler.name)
        
        return handler
    
    def get_handler(self, name: str) -> Optional[CommandHandler]:
        """
        Get handler by name or alias.
        
        Args:
            name: Command name
            
        Returns:
            Command handler or None
        """
        return self._handlers_by_name.get(name)
    
    def get_all_handlers(self) -> List[CommandHandler]:
        """Get all registered handlers sorted by priority."""
        return self._handlers.copy()
    
    def clear(self) -> None:
        """Clear all handlers."""
        self._handlers.clear()
        self._handlers_by_name.clear()


class CommandProcessor:
    """
    Processes incoming messages and executes commands.
    
    Coordinates command execution and message transformation.
    Integrates with the new plugin system for extensibility.
    """
    
    def __init__(self, registry: Optional[CommandRegistry] = None):
        """
        Initialize command processor.
        
        Args:
            registry: Command registry (creates new if not provided)
        """
        self._registry = registry or CommandRegistry()
        self._pre_processors: List[Callable[[CommandContext], CommandContext]] = []
        self._post_processors: List[Callable[[CommandContext, Optional[Message]], None]] = []
        self._plugin_manager: Optional[PluginManager] = None
    
    def register_pre_processor(
        self,
        processor: Callable[[CommandContext], CommandContext]
    ) -> None:
        """
        Register a pre-processor for command context.
        
        Args:
            processor: Function to process context before command execution
        """
        self._pre_processors.append(processor)
    
    def register_post_processor(
        self,
        processor: Callable[[CommandContext, Optional[Message]], None]
    ) -> None:
        """
        Register a post-processor for command results.
        
        Args:
            processor: Function to process result after command execution
        """
        self._post_processors.append(processor)
    
    def set_plugin_manager(self, manager: PluginManager) -> None:
        """
        Set the plugin manager for command processing.
        
        Args:
            manager: PluginManager instance
        """
        self._plugin_manager = manager
    
    def process(
        self,
        content: str,
        sender: str,
        target: Optional[str] = None,
        original_message: Optional[Message] = None
    ) -> Message:
        """
        Process input and execute appropriate commands.
        
        Args:
            content: Input content
            sender: Sender username
            target: Optional target user
            original_message: Original message object
            
        Returns:
            Processed message or response
        """
        context = CommandContext(
            content=content,
            sender=sender,
            target=target,
            original_message=original_message
        )
        
        # Run pre-processors
        for processor in self._pre_processors:
            try:
                context = processor(context)
            except Exception as e:
                logger.exception("Error in pre-processor: %s", e)
        
        # Execute command handlers (including plugin-based handlers)
        result = None
        for handler in self._registry.get_all_handlers():
            try:
                if handler.can_handle(context):
                    result = handler.execute(context)
                    if result is not None:
                        break
            except Exception as e:
                logger.exception("Error executing command %s: %s", handler.name, e)
                result = context.reply(f"Error executing command: {e}")
                break
        
        # Run post-processors
        for processor in self._post_processors:
            try:
                processor(context, result)
            except Exception as e:
                logger.exception("Error in post-processor: %s", e)
        
        if result is not None:
            return result
        
        return Message(MessageType.TEXT, sender, context.content, target=target)
    
    @property
    def registry(self) -> CommandRegistry:
        """Get command registry."""
        return self._registry


class HelpCommandHandler(CommandHandler):
    """Handler for /help command."""
    
    name = "help"
    description = "Show available commands"
    aliases = ["?", "h"]
    
    def __init__(self, processor: CommandProcessor):
        """Initialize with reference to processor."""
        self._processor = processor
    
    def can_handle(self, context: CommandContext) -> bool:
        """Check if content starts with /help or /?"""
        return context.content.strip().lower().startswith(("/help", "/?", "/h "))
    
    def execute(self, context: CommandContext) -> Message:
        """Show help message."""
        handlers = self._processor.registry.get_all_handlers()
        help_text = "Available commands:\n"
        for handler in handlers:
            help_text += f"  /{handler.name} - {handler.description}\n"
        
        return context.reply(help_text.strip(), MessageType.HELP)


class EchoCommandHandler(CommandHandler):
    """Handler for /echo command."""
    
    name = "echo"
    description = "Echo back the message"
    
    def can_handle(self, context: CommandContext) -> bool:
        """Check if content starts with /echo"""
        return context.content.strip().lower().startswith("/echo ")
    
    def execute(self, context: CommandContext) -> Message:
        """Echo the message content."""
        text = context.content[6:].strip()
        return context.reply(f"Echo: {text}")


class PluginCommandLoader:
    """
    Loads command handlers from plugins.
    
    Integrates with the plugin system to load custom commands.
    """
    
    def __init__(self, processor: CommandProcessor):
        """
        Initialize plugin loader.
        
        Args:
            processor: Command processor to register handlers with
        """
        self._processor = processor
    
    def load_from_plugin_manager(self, plugin_manager: PluginManager) -> int:
        """
        Load commands from plugin manager.
        
        Args:
            plugin_manager: Plugin manager instance
            
        Returns:
            Number of commands loaded
        """
        count = 0
        try:
            command_plugins = plugin_manager.get_command_plugins()
            
            for plugin in command_plugins:
                handler = self._create_handler_from_plugin(plugin)
                if handler:
                    self._processor.registry.register(handler)
                    count += 1
                    
        except Exception as e:
            logger.exception("Error loading plugin commands: %s", e)
        
        return count
    
    @staticmethod
    def _create_handler_from_plugin(plugin: CommandPluginBase) -> Optional[CommandHandler]:
        """
        Create command handler from plugin.
        
        Args:
            plugin: Command plugin instance
            
        Returns:
            Command handler or None
        """
        class PluginHandler(CommandHandler):
            name = plugin.get_name()
            description = plugin.metadata.description
            priority = CommandPriority(plugin.metadata.priority.value)
            
            def can_handle(self, context: CommandContext) -> bool:
                return plugin.can_handle(context.content)
            
            def execute(self, context: CommandContext) -> Optional[Message]:
                result = plugin.execute(
                    context.content,
                    context.sender,
                    context.target
                )
                if result is None:
                    return None
                
                # Handle different return types from plugins
                if isinstance(result, Message):
                    # Plugin returned a Message object directly
                    return result
                elif isinstance(result, str):
                    # Plugin returned a string - convert to Message
                    if result != context.content:
                        return context.reply(result)
                
                return None
        
        return PluginHandler()


def create_default_processor() -> CommandProcessor:
    """
    Create a command processor with default commands.
    
    Returns:
        Configured CommandProcessor
    """
    processor = CommandProcessor()
    
    processor.registry.register(HelpCommandHandler(processor))
    processor.registry.register(EchoCommandHandler())
    
    try:
        manager = create_plugin_manager(
            plugin_paths=["./AloneChat/plugins"],
            auto_load=True,
            auto_init=True
        )
        processor.set_plugin_manager(manager)
        
        loader = PluginCommandLoader(processor)
        count = loader.load_from_plugin_manager(manager)
        if count > 0:
            logger.info("Loaded %d plugin commands", count)
    except Exception as e:
        logger.debug("Could not load plugin commands: %s", e)
    
    return processor
