"""
Server startup module for AloneChat application.
Provides the entry point for starting the chat server and API services.
Supports multi-process + multi-thread parallelization.
"""

import multiprocessing as mp
import os
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
from AloneChat.core.server.database import initialize_database, shutdown_database
from AloneChat.core.server.message import shutdown_message_service
from AloneChat.core.server.parallel import (
    get_parallel_manager,
    initialize_parallel,
    shutdown_parallel,
)

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
                shutdown_message_service()
                shutdown_database()
                shutdown_parallel()
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


def _run_uvicorn(host: str, port: int, workers: int = 1):
    """Run uvicorn server with specified workers."""
    if workers > 1:
        uvicorn.run(
            "AloneChat.api.routes:app",
            host=host,
            port=port,
            workers=workers,
            log_level="warning",
            access_log=False,
        )
    else:
        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="warning",
            access_log=False,
        )


def server(
    port: int = None,
    srv_only: bool = False,
    host: str = "0.0.0.0",
    workers: int = None
) -> None:
    """
    Start the chat server and API services.

    Args:
        port: Port number to listen on (default: from config)
        srv_only: If True, serve only the WebSocket server (no HTTP API)
        host: Host to bind to (default: 0.0.0.0 for all interfaces)
        workers: Number of worker processes (default: from config)
    """
    global _shutdown_state
    _shutdown_state = 0
    
    if port is None:
        port = config.config.DEFAULT_SERVER_PORT
    
    if workers is None:
        workers = config.config.WORKERS
    
    mp.set_start_method('spawn', force=True)
    
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    initialize_database()
    
    initialize_parallel()
    
    _set_all_users_offline()
    
    logger.info(AloneChat.__doc__)
    logger.info("")
    logger.info("=" * 50)
    logger.info("Server Configuration:")
    logger.info("  Host: %s", host)
    logger.info("  Port: %d", port)
    logger.info("  Workers: %d", workers)
    logger.info("  Process Workers: %d", config.config.PROCESS_WORKERS)
    logger.info("  Thread Workers: %d", config.config.THREAD_WORKERS)
    logger.info("  IO Workers: %d", config.config.IO_WORKERS)
    logger.info("  DB Workers: %d", config.config.DB_WORKERS)
    logger.info("  DB Pool Size: %d", config.config.DB_POOL_SIZE)
    logger.info("=" * 50)
    logger.info("")
    logger.info("Server started. Press Ctrl+C to shutdown gracefully.")
    logger.info("Press Ctrl+C twice to force quit.")
    logger.info("")
    
    def start_http_server():
        """Start the HTTP API server."""
        try:
            _run_uvicorn(host, port + 1, workers=1)
        except Exception as e:
            logger.exception("HTTP server error: %s", e)
    
    try:
        if not srv_only:
            if workers > 1:
                logger.info("Starting multi-process server with %d workers", workers)
                _run_uvicorn(host, port + 1, workers)
            else:
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


def server_multiprocess(
    port: int = None,
    host: str = "0.0.0.0",
    workers: int = None
) -> None:
    """
    Start the server in multi-process mode using gunicorn-style workers.
    
    This is optimized for production deployments with multiple CPU cores.
    
    Args:
        port: Port number to listen on
        host: Host to bind to
        workers: Number of worker processes
    """
    if port is None:
        port = config.config.DEFAULT_SERVER_PORT
    
    if workers is None:
        workers = config.config.WORKERS
    
    if workers < 1:
        workers = 1
    
    mp.set_start_method('spawn', force=True)
    
    signal.signal(signal.SIGINT, _signal_handler)
    signal.signal(signal.SIGTERM, _signal_handler)
    
    initialize_database()
    
    logger.info(AloneChat.__doc__)
    logger.info("")
    logger.info("=" * 50)
    logger.info("Multi-Process Server Starting")
    logger.info("  Workers: %d", workers)
    logger.info("  Host: %s:%d", host, port + 1)
    logger.info("=" * 50)
    logger.info("")
    
    _run_uvicorn(host, port + 1, workers)


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
    parser.add_argument(
        "--workers", "-w",
        type=int,
        default=None,
        help="Number of worker processes"
    )
    parser.add_argument(
        "--multiprocess",
        action="store_true",
        help="Run in multi-process mode"
    )
    
    args = parser.parse_args()
    
    auto_configure()
    
    if args.multiprocess:
        server_multiprocess(
            port=args.port,
            host=args.host,
            workers=args.workers
        )
    else:
        server(
            port=args.port,
            srv_only=args.srv_only,
            host=args.host,
            workers=args.workers
        )
