"""
Client startup module for AloneChat application.
Provides the entry point for starting the chat client.
"""

import asyncio

from AloneChat.core.client import CursesClient
from AloneChat.core.client import StandardCommandlineClient

__all__ = ['client']


def client(host="localhost", port=8765, ui="tui", auto_connect=False):
    """
    Start the chat client with specified connection parameters.
    Args:
        host (str): Server hostname to connect to (default: localhost)
        port (int): Server port number (default: 8765)
        ui (str): User interface type ("text" for command-line, "tui" for Textual UI)
        auto_connect (bool): Whether to automatically connect to the server (default: False)
    """
    print("欢迎使用 AloneChat 客户端!")
    print(f"当前设置: 服务器={host}:{port}, UI={ui}")
    if auto_connect:
        _connect_to_server(host, port, ui)
    else:
        print("输入 'connect' 连接到服务器，'set host <hostname>' 设置服务器地址，'set port <port>' 设置端口，'exit' 退出")
        while True:
            command = input(">> ").strip().lower()
            command_parts = command.split()

            match command_parts:
                case ["exit"]:
                    print("再见!")
                    break

                case ["connect"]:
                    _connect_to_server(host, port, ui)

                case ["set", "host", hostname]:
                    host = hostname
                    print(f"服务器地址已设置为: {host}")

                case ["set", "port", port_str] if port_str.isdigit():
                    port = int(port_str)
                    print(f"端口已设置为: {port}")

                case ["set", "host"]:
                    print("用法: set host <hostname>")

                case ["set", "port"]:
                    print("用法: set port <port>")

                case ["set", "port", _]:
                    print("端口必须是数字")

                case ["help"]:
                    print("可用命令:")
                    print("  connect - 连接到服务器")
                    print("  set host <hostname> - 设置服务器地址")
                    print("  set port <port> - 设置服务器端口")
                    print("  exit - 退出客户端")

                case ["set", _]:
                    print("用法: set host <hostname> 或 set port <port>")

                case _:
                    print(f"未知命令: {command}，输入 'help' 查看可用命令")


def _connect_to_server(host, port, ui):
    """Helper function to connect to the server"""
    try:
        if ui == "text":
            _client = StandardCommandlineClient(host, port)
            asyncio.run(_client.run())
        elif ui == "tui":
            _client = CursesClient(host, port)
            _client.run()
        else:
            print(
                "Sorry. But we don't have such a beautiful UI yet."
                "We apologize, but we just have a text-based (ugly) UI and a curses-based TUI."
                "No need? You are a geek! Why not join us in developing a new UI?"
                "GitHub: https://github.com/alonechat/AloneChat , welcome you!"
            )
    except KeyboardInterrupt:
        print("已断开连接.")
    except Exception as e:
        print(f"连接失败: {e}")
