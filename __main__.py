import argparse
import asyncio
from AloneChat.start import client, server

def main():
    # 创建主解析器
    parser = argparse.ArgumentParser(prog='AloneChat', description='AloneChat starter')
    subparsers = parser.add_subparsers(dest='command', required=True, help='Available commands')

    # 创建服务器子命令
    server_parser = subparsers.add_parser('server', help='Startup SERVER')
    server_parser.add_argument('--port', type=int, default=8765, help='SERVER port (default: 8080)')
    # server_parser.add_argument('--debug', action='store_true', help='Enable debug mode')

    # 创建客户端子命令
    client_parser = subparsers.add_parser('client', help='Startup CLIENT')
    client_parser.add_argument('--host', default='localhost', help='CLIENT listening address (default: localhost)')
    client_parser.add_argument('--port', type=int, default=8765, help='CLIENT port (default: 8080)')

    # 解析参数并执行对应命令
    args = parser.parse_args()

    if args.command == 'server':
        server.server(port=args.port)
    elif args.command == 'client':
        asyncio.run(client.client(host=args.host, port=args.port))

if __name__ == '__main__':
    main()