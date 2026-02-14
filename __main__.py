"""
Entry point for AloneChat application.
This module provides a command-line interface to start either a server or client.

Enhanced with unified logging system integration.
"""

import argparse
import sys

from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT
from AloneChat.core.logging import auto_configure, get_logger

logger = get_logger(__name__)


def parse():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        prog='AloneChat',
        description='AloneChat - A secure chat application'
    )
    
    # Global options
    parser.add_argument(
        '--env', '-e',
        choices=['development', 'production', 'testing', 'dev', 'prod', 'test'],
        default=None,
        help='Environment configuration (default: auto-detect)'
    )
    parser.add_argument(
        '--verbose', '-v',
        action='store_true',
        help='Enable verbose logging'
    )
    
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Setup server command line arguments
    server_parser = subparsers.add_parser('server', help='Start the server (WebSocket + HTTP API)')
    server_parser.add_argument('--port', type=int, default=None, help='WebSocket port (default: 8765)')
    server_parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    server_parser.add_argument('--no-plugins', action='store_true', help='Disable plugin system')

    # Setup client command line arguments
    client_parser = subparsers.add_parser('client', help='Start the client')
    client_parser.add_argument('--api-host', default=DEFAULT_HOST, help='API server hostname (default: localhost)')
    client_parser.add_argument('--api-port', type=int, default=DEFAULT_API_PORT, help='API server port (default: 8766)')
    client_parser.add_argument(
        '--ui',
        choices=['gui','tui','qt'],
        default='gui',
        help='User interface type: gui (Tk GUI), qt (Qt GUI), tui (terminal UI) (default: gui)'
    )

    # Add 'srv-only' command
    srv_parser = subparsers.add_parser('srv-only', help='Start WebSocket server only')
    srv_parser.add_argument('--port', type=int, default=None, help='WebSocket port (default: 8765)')
    srv_parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')
    srv_parser.add_argument('--no-plugins', action='store_true', help='Disable plugin system')

    # Add 'api-only' command
    api_parser = subparsers.add_parser('api-only', help='Start HTTP API server only')
    api_parser.add_argument('--port', type=int, default=None, help='API server port (default: 8766)')
    api_parser.add_argument('--host', type=str, default='0.0.0.0', help='Host to bind to (default: 0.0.0.0)')

    args = parser.parse_args()

    return args


def main():
    """Main entry point."""
    args = parse()

    # Lazy imports so server startup does not require client GUI dependencies
    from AloneChat.start import server, api, client

    # Initialize logging system
    try:
        auto_configure(env=args.env)
        logger.info("AloneChat starting...")
        logger.info("Command: %s", args.command)
    except Exception as e:
        print(f"Failed to initialize logging: {e}", file=sys.stderr)
        sys.exit(1)

    # Launch based on command
    try:
        if args.command == 'server':
            server.server(
                port=args.port,
                host=args.host,
                enable_plugins=not args.no_plugins
            )
        elif args.command == 'client':
            ui = args.ui
            client.client(api_host=args.api_host, api_port=args.api_port, ui=ui)
        elif args.command == 'srv-only':
            server.server(
                port=args.port,
                host=args.host,
                srv_only=True,
                enable_plugins=not args.no_plugins
            )
        elif args.command == 'api-only':
            api.api(port=args.port, host=args.host)
        else:
            raise ValueError(f'Unknown command: {args.command}')
    except KeyboardInterrupt:
        logger.info("Shutdown requested by user")
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        sys.exit(1)


if __name__ == '__main__':
    main()
