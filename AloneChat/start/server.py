"""
Server startup module for AloneChat application.
Provides the entry point for starting the chat server and API services.
"""

import signal
import sys
import threading
import time

import uvicorn

import AloneChat
import AloneChat.config as config
from AloneChat.api.routes import app
from AloneChat.core.logging import get_logger, auto_configure
from AloneChat.core.server import get_database, shutdown_user_service

logger = get_logger(__name__)

_shutdown_state = 0
_shutdown_lock = threading.Lock()


def _set_all_users_offline():
    """Set ALL users to offline status using single database query."""
    db = get_database()
    count = db.set_all_offline()
    logger.info("Set %d users to offline status", count)
    return count


def _graceful_shutdown():
    """Perform graceful shutdown - set users offline and flush buffer."""
    global _shutdown_state
    
    with _shutdown_lock:
        if _shutdown_state == 0:
            _shutdown_state = 1
            logger.info("")
            logger.info("=" * 50)
            logger.info("Graceful shutdown initiated (Ctrl+C again to force quit)")
            logger.info("Setting all users offline...")
            logger.info("=" * 50)
            logger.info("")
            
            try:
                _set_all_users_offline()
                shutdown_user_service()
                logger.info("Graceful shutdown complete. Press Ctrl+C again to force exit.")
            except Exception as e:
                logger.error("Error during graceful shutdown: %s", e)
            
        elif _shutdown_state == 1:
            _shutdown_state = 2
            logger.info("")
            logger.info("=" * 50)
            logger.info("Force quit requested - exiting immediately")
            logger.info("=" * 50)
            logger.info("")
            sys.exit(1)


def _signal_handler(signum, frame):
    """Handle shutdown signals with two-stage shutdown."""
    _graceful_shutdown()


def server(
    port: int = None,
    srv_only: bool = False,
    host: str = "0.0.0.0"
) -> None:
    """
    Start the chat server and API services.

    Args:
        port: Port number to listen on (default: from config)
        srv_only: If True, serve only the WebSocket server (no HTTP API)
        host: Host to bind to (default: 0.0.0.0 for all interfaces)
    """
    global _shutdown_state
    _shutdown_state = 0
    
    if port is None:
        port = config.config.DEFAULT_SERVER_PORT
    
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    _set_all_users_offline()
    
    logger.info(AloneChat.__doc__)
    logger.info("")
    logger.info("Server started. Press Ctrl+C to shutdown gracefully.")
    logger.info("Press Ctrl+C twice to force quit.")
    logger.info("")
    
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
        
        while _shutdown_state < 2:
            time.sleep(0.5)
            if _shutdown_state == 1:
                break
    except KeyboardInterrupt:
        _graceful_shutdown()
    except Exception as e:
        logger.exception("Server error: %s", e)
    finally:
        if _shutdown_state == 0:
            _graceful_shutdown()
        logger.info("Server shutdown complete")


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
        "--host",
        type=str,
        default="0.0.0.0",
        help="Host to bind to"
    )
    
    args = parser.parse_args()
    
    auto_configure()
    
    server(
        port=args.port,
        srv_only=args.srv_only,
        host=args.host
    )
