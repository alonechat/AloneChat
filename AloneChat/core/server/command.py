"""
A command processing system for AloneChat client.
Handles parsing and processing of chat commands.

This module provides backward compatibility with the legacy command system
while using the new plugin architecture internally.
"""

import logging
import warnings
from typing import Optional

from AloneChat.core.message.protocol import Message, MessageType
from AloneChat.plugins import PluginManager, create_plugin_manager

logger = logging.getLogger(__name__)

_manager: Optional[PluginManager] = None


def _get_manager() -> PluginManager:
    """
    Get or create the global plugin manager.
    
    Returns:
        PluginManager instance
    """
    global _manager
    if _manager is None:
        _manager = create_plugin_manager(
            plugin_paths=["./AloneChat/plugins"],
            auto_load=True,
            auto_init=True
        )
    return _manager


def load() -> dict | None:
    """
    Load plugins using the legacy interface.
    
    This function is provided for backward compatibility.
    
    Returns:
        Dictionary of plugin specifications or None
    """
    warnings.warn(
        "load() is deprecated. Use PluginManager directly.",
        DeprecationWarning,
        stacklevel=2
    )
    
    try:
        manager = _get_manager()
        return manager.load_legacy("./AloneChat/plugins")
    except Exception as e:
        logger.error("Failed to load plugins: %s", e)
        return None


COMMANDS = {}


class CommandSystem:
    """
    Static class for processing chat commands.
    
    This class provides backward compatibility with the legacy command system
    while using the new plugin architecture internally.
    
    Deprecated: Use PluginManager directly for new code.
    """

    # noinspection PyDeprecation
    @classmethod
    def _ensure_loaded(cls):
        """Ensure plugins are loaded."""
        if not COMMANDS:
            loaded = load()
            if loaded:
                COMMANDS.update(loaded)
    
    @classmethod
    def process(cls, input_str: str, sender: str, target: str = None) -> Message:
        """
        Process input string and convert to the appropriate message type.

        Args:
            input_str (str): User input string to process
            sender (str): Username of the message sender
            target (str, optional): Target user for the message, if needed

        Returns:
            Message: Processed message object
        """
        try:
            # Use the new command processor for proper command handling
            from AloneChat.core.server.commands import create_default_processor
            
            processor = create_default_processor()
            result = processor.process(input_str, sender, target)
            
            return result
            
        except Exception as e:
            logger.error("Error processing command: %s", e)
            return Message(MessageType.TEXT, sender, input_str, target=target)
    
    @classmethod
    def process_legacy(cls, input_str: str, sender: str, target: str = None) -> Message:
        """
        Process input using legacy command handling.
        
        Args:
            input_str: User input string to process
            sender: Username of the message sender
            target: Target user for the message, if needed
            
        Returns:
            Message: Processed message object
        """
        cls._ensure_loaded()
        
        for cmd in COMMANDS:
            if "handler" in cmd:
                try:
                    handler = cmd["handler"]
                    if callable(handler):
                        input_str = handler(input_str)
                except Exception as e:
                    logger.error("Error in command handler: %s", e)
        
        return Message(MessageType.TEXT, sender, input_str)
