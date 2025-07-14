"""
Entry point for AloneChat application.
This module provides a command-line interface to start either a server or client.
"""

import argparse

from AloneChat.start import client, server


def main():
    # Initialize argument parser for command line interface
    parser = argparse.ArgumentParser(prog='AloneChat', description='AloneChat starter')
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # Setup server command line arguments
    server_parser = subparsers.add_parser('server', help='Startup SERVER')
    server_parser.add_argument('--port', type=int, default=8765, help='SERVER port (default: 8080)')
    # server_parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    # Setup client command line arguments
    client_parser = subparsers.add_parser('client', help='Startup CLIENT')
    client_parser.add_argument('--host', default='localhost', help='CLIENT listening address (default: localhost)')
    client_parser.add_argument('--port', type=int, default=8765, help='CLIENT port (default: 8080)')

    args = parser.parse_args()

    # Launch either server or client based on command line arguments
    if args.command == 'server':
        server.server(port=args.port)
    elif args.command == 'client':
        client.client(host=args.host, port=args.port)

if __name__ == '__main__':
    main()