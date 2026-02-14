"""
Server module for AloneChat.

This module provides WebSocket server functionality with a modular architecture:

Architecture Overview:
---------------------

The server is organized into the following components:

1. **Authentication** (`auth/`)
   - JWTAuthenticator: Handles JWT token validation
   - AuthenticationMiddleware: Wraps auth logic
   - Token extractors for various transport formats

2. **Session Management** (`session/`)
   - SessionManager: High-level session coordination
   - InMemorySessionStore: In-memory session storage
   - UserSession: Session data model

3. **Transport Layer** (`transport/`)
   - WebSocketConnection: Connection wrapper
   - WebSocketConnectionRegistry: Connection management
   - ConnectionHealthMonitor: Automatic cleanup

4. **Message Routing** (`routing/`)
   - MessageRouter: Routes messages to destinations
   - BroadcastServiceImpl: High-level broadcasting

5. **Command Processing** (`commands/`)
   - CommandProcessor: Processes chat commands
   - CommandRegistry: Manages command handlers
   - Plugin-based command loading

6. **Unified Manager** (`websocket_manager.py`)
   - UnifiedWebSocketManager: Main entry point that composes all components
   - MessageProcessingPipeline: Plugin-aware message processing
   - ConnectionContext: Per-connection state management

7. **Plugin Integration** (`interfaces/`)
   - HookPhase: Lifecycle phases for hooks
   - HookContext: Context passed to hooks
   - PluginAwareComponent: Base class for hook-enabled components

Migration Guide:
---------------

The old `manager.py` and `command.py` are deprecated but still available
for backward compatibility. New code should use the UnifiedWebSocketManager:

    # Old way (deprecated):
    from AloneChat.core.server import WebSocketManager
    manager = WebSocketManager()
    
    # New way (recommended):
    from AloneChat.core.server import UnifiedWebSocketManager, HookPhase
    
    manager = UnifiedWebSocketManager()
    
    # Register hooks for plugin integration
    def my_hook(ctx):
        # Pre-process message
        return ctx
    
    manager.register_hook(HookPhase.PRE_MESSAGE, my_hook)
    
    async with manager.run("localhost", 8765):
        await asyncio.Future()

Backward Compatibility:
----------------------

The following legacy exports are maintained for backward compatibility:
- UserSession: Now an alias to session.UserSession
- SessionManager: Now an alias to session.SessionManager
- WebSocketManager: Legacy manager (deprecated, use UnifiedWebSocketManager)

"""

import warnings

from AloneChat.core.server import command as _command_module
from AloneChat.core.server.auth import (
    JWTAuthenticator,
    AuthenticationMiddleware,
    DefaultTokenExtractor,
)
from AloneChat.core.server.commands import (
    CommandHandler,
    CommandRegistry,
    CommandProcessor,
    CommandContext,
    CommandPriority,
    create_default_processor,
)
from AloneChat.core.server.interfaces import (
    Authenticator,
    AuthResult,
    SessionStore,
    TransportConnection,
    MessageHandler,
    BroadcastService,
    ConnectionRegistry,
    ServerLifecycle,
    HookPhase,
    HookContext,
    HookFunction,
    HookRegistry,
    PluginAwareComponent,
    ProcessingResult,
    MessageProcessor,
)
from AloneChat.core.server.routing import (
    MessageRouter,
    BroadcastServiceImpl,
    DeliveryResult,
    DeliveryStatus,
)
from AloneChat.core.server.session import (
    UserSession,
    InMemorySessionStore,
    SessionManager,
)
from AloneChat.core.server.transport import (
    WebSocketConnection,
    WebSocketConnectionRegistry,
    ConnectionHealthMonitor,
    TransportFactory,
)
from AloneChat.core.server.utils.helpers import (
    MessageBuilder,
    create_server_message,
    create_error_message,
    create_join_message,
    create_leave_message,
    SafeSender,
)
from AloneChat.core.server.websocket_manager import (
    UnifiedWebSocketManager,
    ConnectionContext,
    MessageProcessingPipeline,
    create_server,
)

COMMANDS = _command_module.COMMANDS
CommandSystem = _command_module.CommandSystem


def _deprecated_warning(old_name, new_name):
    """Issue deprecation warning."""
    warnings.warn(
        f"{old_name} is deprecated. Use {new_name} instead.",
        DeprecationWarning,
        stacklevel=3
    )


# WebSocketManager is now an alias to UnifiedWebSocketManager
# The legacy WebSocketManager has been removed
WebSocketManager = UnifiedWebSocketManager

__all__ = [
    'Authenticator',
    'AuthResult',
    'SessionStore',
    'TransportConnection',
    'MessageHandler',
    'BroadcastService',
    'ConnectionRegistry',
    'ServerLifecycle',
    'HookPhase',
    'HookContext',
    'HookFunction',
    'HookRegistry',
    'PluginAwareComponent',
    'ProcessingResult',
    'MessageProcessor',
    
    'JWTAuthenticator',
    'AuthenticationMiddleware',
    'DefaultTokenExtractor',
    
    'UserSession',
    'InMemorySessionStore',
    'SessionManager',
    
    'WebSocketConnection',
    'WebSocketConnectionRegistry',
    'ConnectionHealthMonitor',
    'TransportFactory',
    
    'MessageRouter',
    'BroadcastServiceImpl',
    'DeliveryResult',
    'DeliveryStatus',
    
    'CommandHandler',
    'CommandRegistry',
    'CommandProcessor',
    'CommandContext',
    'CommandPriority',
    'create_default_processor',
    
    'UnifiedWebSocketManager',
    'ConnectionContext',
    'MessageProcessingPipeline',
    'create_server',
    
    'MessageBuilder',
    'create_server_message',
    'create_error_message',
    'create_join_message',
    'create_leave_message',
    'SafeSender',
    
    'WebSocketManager',
    'COMMANDS',
    'CommandSystem',
]
