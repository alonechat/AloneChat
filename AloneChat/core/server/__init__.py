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

Migration Guide:
---------------

The old `manager.py` and `command.py` are deprecated but still available
for backward compatibility. New code should use the UnifiedWebSocketManager:

    # Old way (deprecated):
    from AloneChat.core.server import WebSocketManager
    manager = WebSocketManager()
    
    # New way (recommended):
    from AloneChat.core.server import UnifiedWebSocketManager
    manager = UnifiedWebSocketManager()
    await manager.start("localhost", 8765)

Backward Compatibility:
----------------------

The following legacy exports are maintained for backward compatibility:
- UserSession: Now an alias to session.UserSession
- SessionManager: Now an alias to session.SessionManager
- WebSocketManager: Legacy manager (deprecated, use UnifiedWebSocketManager)

"""

# New modular components
from AloneChat.core.server.interfaces import (
    Authenticator,
    AuthResult,
    SessionStore,
    TransportConnection,
    MessageHandler,
    BroadcastService,
    ConnectionRegistry,
)

from AloneChat.core.server.auth import (
    JWTAuthenticator,
    AuthenticationMiddleware,
    DefaultTokenExtractor,
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

from AloneChat.core.server.routing import (
    MessageRouter,
    BroadcastServiceImpl,
    DeliveryResult,
    DeliveryStatus,
)

from AloneChat.core.server.commands import (
    CommandHandler,
    CommandRegistry,
    CommandProcessor,
    CommandContext,
    CommandPriority,
    create_default_processor,
)

from AloneChat.core.server.websocket_manager import (
    UnifiedWebSocketManager,
    ConnectionContext,
)

from AloneChat.core.server.utils.helpers import (
    MessageBuilder,
    create_server_message,
    create_error_message,
    create_join_message,
    create_leave_message,
    SafeSender,
)

# Legacy imports for backward compatibility
# These are deprecated and will be removed in future versions
import warnings
from AloneChat.core.server import manager as _manager_module
from AloneChat.core.server import command as _command_module

# Legacy exports (deprecated)
WebSocketManager = _manager_module.WebSocketManager
COMMANDS = _command_module.COMMANDS
CommandSystem = _command_module.CommandSystem

def _deprecated_warning(old_name, new_name):
    """Issue deprecation warning."""
    warnings.warn(
        f"{old_name} is deprecated. Use {new_name} instead.",
        DeprecationWarning,
        stacklevel=3
    )

# Wrap legacy classes to emit warnings
class _DeprecatedWebSocketManager(WebSocketManager):
    """Wrapper that emits deprecation warning."""
    
    def __init__(self, *args, **kwargs):
        _deprecated_warning("WebSocketManager", "UnifiedWebSocketManager")
        super().__init__(*args, **kwargs)

# Replace with warning-enabled versions
WebSocketManager = _DeprecatedWebSocketManager

__all__ = [
    # Interfaces
    'Authenticator',
    'AuthResult',
    'SessionStore',
    'TransportConnection',
    'MessageHandler',
    'BroadcastService',
    'ConnectionRegistry',
    
    # Authentication
    'JWTAuthenticator',
    'AuthenticationMiddleware',
    'DefaultTokenExtractor',
    
    # Session Management
    'UserSession',
    'InMemorySessionStore',
    'SessionManager',
    
    # Transport
    'WebSocketConnection',
    'WebSocketConnectionRegistry',
    'ConnectionHealthMonitor',
    'TransportFactory',
    
    # Routing
    'MessageRouter',
    'BroadcastServiceImpl',
    'DeliveryResult',
    'DeliveryStatus',
    
    # Commands
    'CommandHandler',
    'CommandRegistry',
    'CommandProcessor',
    'CommandContext',
    'CommandPriority',
    'create_default_processor',
    
    # Main Manager
    'UnifiedWebSocketManager',
    'ConnectionContext',
    
    # Utilities
    'MessageBuilder',
    'create_server_message',
    'create_error_message',
    'create_join_message',
    'create_leave_message',
    'SafeSender',
    
    # Legacy (deprecated)
    'WebSocketManager',
    'COMMANDS',
    'CommandSystem',
]
