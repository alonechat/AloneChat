# AloneChat

>[contect to us](http://47.98.235.177:38479/feedback.html)

A secure, modular chat application with WebSocket-based real-time communication, 
plugin extensibility, and unified logging.

## Features

- **Real-time Communication**: WebSocket-based messaging with JWT authentication
- **Plugin System**: Modular architecture with lifecycle management and hooks
- **Unified Logging**: Comprehensive logging with file rotation and environment configs
- **Multiple UI Modes**: GUI (modern) and TUI (terminal) interfaces
- **REST API**: HTTP API for client-server communication
- **Session Management**: User presence tracking and automatic cleanup
- **Friends (Required for Private Chat)**: Friend requests + accept/reject; only friends can private chat

## Architecture

TODO

## Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/AloneChat.git
cd AloneChat

# Create virtual environment (optional but recommended)
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Install dependencies
pip install -r requirements.txt
```

## Quick Start

### Start Server

```bash
# Start server with WebSocket + HTTP API
python -m AloneChat server --port 8765

# Start WebSocket server only
python -m AloneChat srv-only --port 8765

# Start with specific environment
python -m AloneChat server --env production
```

### Start Client

```bash
# Start GUI client
python -m AloneChat client

# Start TUI client
python -m AloneChat client --ui tui

# Connect to specific server
python -m AloneChat client --api-host localhost --api-port 8766
```

## Configuration

### ClickHouse defaults (local dev)

By default, AloneChat assumes ClickHouse is running locally on:

- HTTP: `127.0.0.1:8123`
- Native: `127.0.0.1:9000`

### Environment Variables

| Variable        | Description                                  | Default                 |
|-----------------|----------------------------------------------|-------------------------|
| `ALONECHAT_ENV` | Environment (development/production/testing) | development             |
| `JWT_SECRET`    | JWT signing secret                           | (change in production!) |
| `CLICKHOUSE_HOST` | ClickHouse native host (driver)            | 127.0.0.1               |
| `CLICKHOUSE_PORT` | ClickHouse native port (driver)            | 9000                    |
| `CLICKHOUSE_DATABASE` | ClickHouse database name               | alonechat               |
| `CLICKHOUSE_HTTP_HOST` | ClickHouse HTTP host (browser)        | 127.0.0.1               |
| `CLICKHOUSE_HTTP_PORT` | ClickHouse HTTP port (browser)        | 8123                    |

### Command-Line Options

```bash
python -m AloneChat server [OPTIONS]

Options:
  --port, -p      WebSocket port (default: 8765)
  --host          Host to bind to (default: 0.0.0.0)
  --env, -e       Environment configuration
  --no-plugins    Disable plugin system
  --verbose, -v   Enable verbose logging

```

## Friends & Private Chat

AloneChat includes a minimal friend mechanism:

- Send friend request: `POST /api/friends/request`
- Accept / reject: `POST /api/friends/accept`, `POST /api/friends/reject`
- List friends: `GET /api/friends/list`
- List requests: `GET /api/friends/requests?direction=incoming|outgoing`

**Important:** private chats are friend-gated. If you try to private chat without being friends, the API returns `403 NOT_FRIENDS`.
```

## Plugin Development

### Creating a Plugin

```python
from AloneChat.plugins import CommandPluginBase, PluginMetadata

class MyPlugin(CommandPluginBase):
    _metadata = PluginMetadata(
        name="my_plugin",
        version="1.0.0",
        description="My custom plugin",
        author="Your Name",
        dependencies=[]
    )
    
    def initialize(self, context):
        self.context = context
    
    def shutdown(self):
        pass
    
    def can_handle(self, content: str) -> bool:
        return content.startswith("/mycommand")
    
    def execute(self, content: str, sender: str, target: str = None) -> str:
        return f"Executed: {content}"
```

### Plugin Hooks

```python
from AloneChat.core.server import HookPhase, HookContext
manager = ...  # Get reference to UnifiedWebSocketManager

def my_hook(ctx: HookContext) -> HookContext:
    if ctx.phase == HookPhase.PRE_MESSAGE:
        # Process message before handling
        pass
    return ctx

manager.register_hook(HookPhase.PRE_MESSAGE, my_hook)
```

See [docs/LOGGING.md](docs/LOGGING.md) for logging documentation.

## Logging

The unified logging system provides consistent logging across all components:

```python
from AloneChat.core.logging import get_logger, auto_configure

auto_configure()
logger = get_logger(__name__)

logger.info("Application started")
logger.error("An error occurred", exc_info=True)
```

### Log Levels

- `DEBUG`: Detailed debugging information
- `INFO`: General application flow
- `WARNING`: Unexpected but non-critical issues
- `ERROR`: Error conditions
- `CRITICAL`: Application cannot continue

### Log Files

- Development: `./logs/dev/alonechat.log`
- Production: `./logs/prod/alonechat.log`
- Errors: `./logs/*/alonechat_errors.log`

## API Reference

### HTTP Endpoints

| Endpoint    | Method | Description         |
|-------------|--------|---------------------|
| `/login`    | POST   | User authentication |
| `/register` | POST   | User registration   |
| `/send`     | POST   | Send message        |
| `/recv`     | GET    | Get message history |

### WebSocket Protocol

Messages are JSON-serialized with the following structure:

```json
{
    "type": "TEXT|JOIN|LEAVE|HEARTBEAT",
    "sender": "username",
    "content": "message content",
    "target": "optional_target_user",
    "timestamp": "ISO-8601 timestamp"
}
```

## Development

TODO

## Project Structure

### Core Modules

| Module         | Description                               |
|----------------|-------------------------------------------|
| `core/server`  | WebSocket server, authentication, routing |
| `core/client`  | Client UI and communication               |
| `core/message` | Message protocol definitions              |
| `core/logging` | Unified logging system                    |
| `plugins`      | Plugin system and built-in plugins        |
| `api`          | HTTP REST API                             |

### Key Classes

| Class                     | Module                 | Description                 |
|---------------------------|------------------------|-----------------------------|
| `UnifiedWebSocketManager` | `core.server`          | Main server orchestrator    |
| `PluginManager`           | `plugins`              | Plugin lifecycle management |
| `LoggingManager`          | `core.logging`         | Centralized logging         |
| `CommandProcessor`        | `core.server.commands` | Command handling            |

## Security

- JWT-based authentication with configurable secrets
- Token expiration and validation
- User session management
- Input validation and sanitization

> [!IMPORTANT]
> Always change `JWT_SECRET` in production environments!

## Acknowledgments

- Built with [websockets](https://github.com/python-websockets/websockets)
- GUI powered by [customtkinter](https://github.com/TomSchimansky/CustomTkinter)a dn
- Authentication via [PyJWT](https://github.com/jpadilla/pyjwt)

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

> [!NOTE] 
> Do not study @hi-zcy... and his commit style -- @hi-zcy

## License

`Apache License Version 2.0`—full text in `LICENSE` file.


## Friends (GUI)

The GUI client now includes a **Friends** tab in the left sidebar:
- Send friend requests
- Accept/Reject incoming requests
- View your friend list
- Double-click a friend to open a private chat (private messaging is restricted to friends by the server)

Friend APIs used:
- `POST /api/friends/request`
- `POST /api/friends/accept`
- `POST /api/friends/reject`
- `GET /api/friends/list`
- `GET /api/friends/requests`
