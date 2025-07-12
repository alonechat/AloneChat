import asyncio
from AloneChat.core.client import StandardCommandlineClient

__all__ = ['client']

def client(host="localhost", port=8765):
    _client = StandardCommandlineClient(host, port)
    try:
        asyncio.run(_client.run())
    except KeyboardInterrupt:
        print("Now quit. Bye!")