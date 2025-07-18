"""
Entry point for AloneChat application.
This module provides a command-line interface to start either a server or client.
"""

import argparse

from AloneChat.start import client, server, API
from AloneChat.test import main as test_main


def main():
    # Initialize argument parser for command line interface
    parser = argparse.ArgumentParser(prog='AloneChat', description='AloneChat starter')
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Setup server command line arguments
    server_parser = subparsers.add_parser('server', help='Startup SERVER')
    server_parser.add_argument('--port', type=int, default=8765, help='SERVER port (default: 8765)')

    # Setup client command line arguments
    client_parser = subparsers.add_parser('client', help='Startup CLIENT')
    client_parser.add_argument('--host', default='localhost', help='CLIENT listening address (default: localhost)')
    client_parser.add_argument('--port', type=int, default=8765, help='CLIENT port (default: 8766)')
    client_parser.add_argument('--ui', choices=['text', 'tui'], default='tui',
                               help='User interface type (default: text)')

    # noinspection PyPep8Naming
    API_parser = subparsers.add_parser('api', help='Startup API')
    API_parser.add_argument('--port', type=int, default=8766, help='API server port (default: 8766)')

    test_parser = subparsers.add_parser('test', help='Run Test')
    test_parser.add_argument('--host', default='localhost', help='Test server listening address (default: localhost)')
    test_parser.add_argument('--port', type=int, default=8765, help='Test server port (default: 8765)')
    test_parser.add_argument('message', help='Message to send in test')

    args = parser.parse_args()

    # Launch either server or client based on command line arguments
    if args.command == 'server':
        server.server(port=args.port)
    elif args.command == 'client':
        if args.ui == 'tui':
            client.client(host=args.host, port=args.port, ui='tui')
        elif args.ui == 'text':
            client.client(host=args.host, port=args.port, ui='text')
    elif args.command == 'api':
        API.API(port=args.port)
    elif args.command == 'test':
        test_main(args.message, host=args.host, port=args.port)

if __name__ == '__main__':
    main()