"""
Entry point for AloneChat application.
This module provides a command-line interface to start either a server or client.
"""

import argparse

from AloneChat.start import client, server, api
from AloneChat.test import main as test_main
from AloneChat.core.client.utils import DEFAULT_HOST, DEFAULT_API_PORT


def parse():
    # Initialize argument parser for command line interface
    parser = argparse.ArgumentParser(prog='AloneChat', description='AloneChat starter')
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Setup server command line arguments
    server_parser = subparsers.add_parser('server', help='Startup SERVER')
    server_parser.add_argument('--port', type=int, default=8765, help='SERVER port (default: 8765)')

    # Setup client command line arguments
    client_parser = subparsers.add_parser('client', help='Startup CLIENT')
    client_parser.add_argument('--host', default=DEFAULT_HOST, help='CLIENT listening address (default: localhost)')
    client_parser.add_argument('--port', type=int, default=DEFAULT_API_PORT, help='CLIENT API port (default: 8766)')
    client_parser.add_argument(
        '--ui',
        choices=['tui', 'gui', 'gui-cli'],
        default='tui',
        help='User interface type: tui (curses chat), gui (modern GUI), gui-cli (terminal in GUI window) (default: tui)'
    )
    client_parser.add_argument(
        '--auto-connect',
        action='store_true',
        help='Automatically connect to server without showing CLI menu'
    )

    # Add 'srv-only' command
    srv_parser = subparsers.add_parser('srv-only', help='Startup server (ws server)')
    srv_parser.add_argument('--port', type=int, default=8765, help='server port (default: 8765)')

    # Add 'api-only' command
    api_parser = subparsers.add_parser('api-only', help='Startup api (alias for api)')
    api_parser.add_argument('--port', type=int, default=8766, help='api server port (default: 8766)')

    test_parser = subparsers.add_parser('test', help='Run Test')
    test_parser.add_argument('--host', default=DEFAULT_HOST, help='Test server listening address (default: localhost)')
    test_parser.add_argument('--port', type=int, default=8765, help='Test server port (default: 8765)')
    test_parser.add_argument('message', help='Message to send in test')

    args = parser.parse_args()

    return args


def main():
    args = parse()

    # Launch either server or client based on command line arguments
    if args.command == 'server':
        server.server(port=args.port)
    elif args.command == 'client':
        # Handle different UI types
        ui = args.ui
        auto_connect = getattr(args, 'auto_connect', False)
        client.client(host=args.host, port=args.port, ui=ui, auto_connect=auto_connect)
    elif args.command == 'srv-only':
        server.server(port=args.port, srv_only=True)
    elif args.command == 'api-only':
        api.api(port=args.port)
    elif args.command == 'test':
        test_main(host=args.host, port=args.port, message=args.message)
    else:
        raise Exception('Unknown command')


if __name__ == '__main__':
    main()
