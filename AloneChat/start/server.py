"""
Server startup module for AloneChat application.
Provides the entry point for starting the chat server and api services.

Enhanced with plugin system integration, lifecycle hooks, and unified logging.
"""

import asyncio
import threading
from typing import Callable

import uvicorn

import AloneChat.config as config
from AloneChat.api.routes import app
from AloneChat.core.logging import get_logger, auto_configure
from AloneChat.core.server import UnifiedWebSocketManager, HookPhase, HookContext

logger = get_logger(__name__)


def _reset_user_statuses():
    """Reset all user online statuses to offline."""
    from AloneChat.api.routes import load_user_credentials, save_user_credentials
    
    user_credentials = load_user_credentials()
    for username in user_credentials:
        user_credentials[username]['is_online'] = False
    save_user_credentials(user_credentials)
    logger.info("All user credentials saved. All statuses reset to 'offline'.")


def _create_user_status_callback(is_online: bool) -> Callable[[str], None]:
    """
    Create a callback function for user status updates.
    
    Args:
        is_online: Whether the user is coming online or going offline
        
    Returns:
        Callback function
    """
    def callback(username: str) -> None:
        try:
            from AloneChat.api.routes import update_user_online_status
            update_user_online_status(username, is_online)
        except Exception as e:
            logger.error("Failed to update user status for %s: %s", username, e)
    
    return callback


def _setup_default_hooks(manager: UnifiedWebSocketManager) -> None:
    """
    Set up default hooks for the WebSocket manager.
    
    Args:
        manager: UnifiedWebSocketManager instance
    """
    def log_connections(ctx: HookContext) -> HookContext:
        if ctx.phase == HookPhase.POST_CONNECT:
            logger.info("User connected: %s", ctx.user_id)
        elif ctx.phase == HookPhase.POST_DISCONNECT:
            logger.info("User disconnected: %s", ctx.user_id)
        return ctx
    
    manager.register_hook(HookPhase.POST_CONNECT, log_connections, priority=100)
    manager.register_hook(HookPhase.POST_DISCONNECT, log_connections, priority=100)


def server(
    port: int = None,
    srv_only: bool = False,
    enable_plugins: bool = True,
    host: str = "0.0.0.0"
) -> None:
    """
    Start the chat server and API services on the specified port.

    Args:
        port: Port number to listen on (default: from config)
        srv_only: If True, serve only the WebSocket server (no HTTP API)
        enable_plugins: Whether to enable the plugin system
        host: Host to bind to (default: 0.0.0.0 for all interfaces)
    """
    if port is None:
        port = config.config.DEFAULT_SERVER_PORT
    
    _reset_user_statuses()
    
    manager = UnifiedWebSocketManager(
        on_user_connect=_create_user_status_callback(True),
        on_user_disconnect=_create_user_status_callback(False),
        enable_plugins=enable_plugins
    )
    
    _setup_default_hooks(manager)
    
    async def start_websocket_server():
        """Start the WebSocket server."""
        try:
            async with manager.run(host, port):
                logger.info("WebSocket server running on ws://%s:%s", host, port)
                await asyncio.Future()
        except asyncio.CancelledError:
            logger.info("WebSocket server cancelled")
        except Exception as e:
            logger.exception("WebSocket server error: %s", e)
        finally:
            logger.info("WebSocket server stopped")
    
    def start_http_server():
        """Start the HTTP API server."""
        try:
            uvicorn.run(
                app,
                host=host,
                port=port + 1,
                log_level="warning"
            )
        except Exception as e:
            logger.exception("HTTP server error: %s", e)
    
    try:
        if not srv_only:
            http_thread = threading.Thread(target=start_http_server, daemon=True)
            http_thread.start()
            logger.info("HTTP API server starting on http://%s:%s", host, port + 1)
        
        asyncio.run(start_websocket_server())
    except KeyboardInterrupt:
        logger.info("Server shutdown requested by user")
    except Exception as e:
        logger.exception("Server error: %s", e)
    finally:
        logger.info("Server shutdown complete")


def server_legacy(
    port: int = None,
    srv_only: bool = False
) -> None:
    """
    Start the chat server using the legacy WebSocketManager.
    
    Deprecated: Use server() instead.
    
    Args:
        port: Port number to listen on
        srv_only: If True, serve only the WebSocket server
    """
    import warnings
    warnings.warn(
        "server_legacy() is deprecated. Use server() instead.",
        DeprecationWarning,
        stacklevel=2
    )
    
    from AloneChat.core.server.manager import WebSocketManager
    
    if port is None:
        port = config.config.DEFAULT_SERVER_PORT
    
    _reset_user_statuses()
    
    ws_manager = WebSocketManager(port=port)
    
    async def start_websocket_server():
        await ws_manager.run()
    
    def start_http_server():
        uvicorn.run(app, host="0.0.0.0", port=port + 1)
    
    try:
        if not srv_only:
            http_thread = threading.Thread(target=start_http_server, daemon=True)
            http_thread.start()
        
        asyncio.run(start_websocket_server())
    except KeyboardInterrupt:
        print("Closed by user.")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Start AloneChat server")
    parser.add_argument(
        "--port", "-p",
        type=int,
        default=None,
        help="Port number to listen on"
    )
    parser.add_argument(
        "--srv-only",
        action="store_true",
        help="Run only WebSocket server (no HTTP API)"
    )
    parser.add_argument(
        "--no-plugins",
        action="store_true",
        help="Disable plugin system"
    )
    parser.add_argument(
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to"
    )
    parser.add_argument(
        "--legacy",
        action="store_true",
        help="Use legacy WebSocketManager (deprecated)"
    )
    
    args = parser.parse_args()
    
    # Initialize unified logging system
    auto_configure()
    
    if args.legacy:
        # noinspection PyDeprecation
        server_legacy(port=args.port, srv_only=args.srv_only)
    else:
        server(
            port=args.port,
            srv_only=args.srv_only,
            enable_plugins=not args.no_plugins,
            host=args.host
        )
