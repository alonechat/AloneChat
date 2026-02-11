"""
Command processing system for the server.

Provides a modular and extensible command architecture with
support for plugins and custom command handlers.
"""

import logging
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Callable, Type
from dataclasses import dataclass
from enum import Enum

from AloneChat.core.message.protocol import Message, MessageType

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
    
    # Command metadata
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
        
        # Register aliases
        for alias in handler.aliases:
            self._handlers_by_name[alias] = handler
        
        # Sort handlers by priority
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
            
            # Remove all aliases
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
        # Create context
        context = CommandContext(
            content=content,
            sender=sender,
            target=target,
            original_message=original_message
        )
        
        # Apply pre-processors
        for processor in self._pre_processors:
            try:
                context = processor(context)
            except Exception as e:
                logger.exception("Error in pre-processor: %s", e)
        
        # Try to execute commands
        result = None
        for handler in self._registry.get_all_handlers():
            try:
                if handler.can_handle(context):
                    result = handler.execute(context)
                    if result is not None:
                        # Command was executed and produced a result
                        break
            except Exception as e:
                logger.exception("Error executing command %s: %s", handler.name, e)
                result = context.reply(f"Error executing command: {e}")
                break
        
        # Apply post-processors
        for processor in self._post_processors:
            try:
                processor(context, result)
            except Exception as e:
                logger.exception("Error in post-processor: %s", e)
        
        # Return result or default message
        if result is not None:
            return result
        
        # No command handled it, return as regular text message
        return Message(MessageType.TEXT, sender, content, target=target)
    
    @property
    def registry(self) -> CommandRegistry:
        """Get command registry."""
        return self._registry


# Built-in command handlers

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
        text = context.content[6:].strip()  # Remove "/echo "
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
    
    def load_from_plugin_manager(self, plugin_manager) -> int:
        """
        Load commands from plugin manager.
        
        Args:
            plugin_manager: Plugin manager instance
            
        Returns:
            Number of commands loaded
        """
        count = 0
        try:
            loaded = plugin_manager.load()
            if loaded:
                for cmd_spec in loaded:
                    # Create handler from plugin spec
                    handler = self._create_handler_from_spec(cmd_spec)
                    if handler:
                        self._processor.registry.register(handler)
                        count += 1
        except Exception as e:
            logger.exception("Error loading plugin commands: %s", e)
        
        return count
    
    def _create_handler_from_spec(self, spec: Dict) -> Optional[CommandHandler]:
        """
        Create command handler from plugin specification.
        
        Args:
            spec: Plugin specification dictionary
            
        Returns:
            Command handler or None
        """
        # This is a simplified version - extend based on actual plugin format
        class PluginHandler(CommandHandler):
            name = spec.get("name", "unknown")
            description = spec.get("description", "")
            
            def can_handle(self, context: CommandContext) -> bool:
                cmd = spec.get("command", "")
                return context.content.strip().lower().startswith(f"/{cmd}")
            
            def execute(self, context: CommandContext) -> Optional[Message]:
                handler_fn = spec.get("handler")
                if handler_fn:
                    result = handler_fn(context.content)
                    if result:
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
    
    # Register built-in commands
    processor.registry.register(HelpCommandHandler(processor))
    processor.registry.register(EchoCommandHandler())
    
    # Try to load plugin commands
    try:
        from AloneChat.core.client.plugin_loader import PluginManager
        loader = PluginCommandLoader(processor)
        count = loader.load_from_plugin_manager(PluginManager())
        if count > 0:
            logger.info("Loaded %d plugin commands", count)
    except Exception as e:
        logger.debug("Could not load plugin commands: %s", e)
    
    return processor
