# AloneChat

A secure, modular chat application with WebSocket-based real-time communication, plugin extensibility, and unified logging.

> [!WARNING]
> 
> Because windows-curses is not supported on python 3.14 and above, this project is currently only compatible with python 3.13 and below on Windows.
> Or you can build `https://github.com/pmbarrett314/windows-curses` as a workaround, but it may not be stable.
>
> Curses on Windows really be a curse.

## Features

- **Real-time Communication**: WebSocket-based messaging with JWT authentication
- **Plugin System**: Modular architecture with lifecycle management and hooks
- **Unified Logging**: Comprehensive logging with file rotation and environment configs
- **Multiple UI Modes**: GUI (modern) and TUI (terminal) interfaces
- **REST API**: HTTP API for client-server communication
- **Session Management**: User presence tracking and automatic cleanup

## Architecture

```
AloneChat/.
├── AloneChat
│   ├── __init__.py
│   ├── api
│   │   ├── __init__.py
│   │   ├── client.py
│   │   ├── routes.py
│   │   ├── routes_api.py
│   │   └── routes_base.py
│   ├── config.py
│   ├── core
│   │   ├── __init__.py
│   │   ├── client
│   │   │   ├── __init__.py
│   │   │   ├── auth
│   │   │   │   ├── __init__.py
│   │   │   │   └── auth_flow.py
│   │   │   ├── cli
│   │   │   │   ├── __init__.py
│   │   │   │   ├── parser.py
│   │   │   │   └── selector.py
│   │   │   ├── client_base.py
│   │   │   ├── curses_client.py
│   │   │   ├── gui
│   │   │   │   ├── __init__.py
│   │   │   │   ├── client.py
│   │   │   │   ├── components
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── common.py
│   │   │   │   │   └── message_card.py
│   │   │   │   ├── controllers
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── auth_view.py
│   │   │   │   │   ├── chat_view.py
│   │   │   │   │   └── search_dialog.py
│   │   │   │   ├── models
│   │   │   │   │   ├── __init__.py
│   │   │   │   │   ├── data.py
│   │   │   │   │   └── theme.py
│   │   │   │   └── services
│   │   │   │       ├── __init__.py
│   │   │   │       ├── async_service.py
│   │   │   │       ├── conversation_manager.py
│   │   │   │       ├── persistence_service.py
│   │   │   │       └── search_service.py
│   │   │   ├── gui_client.py
│   │   │   ├── input
│   │   │   │   ├── __init__.py
│   │   │   │   ├── handler.py
│   │   │   │   └── key_mappings.py
│   │   │   ├── runner.py
│   │   │   ├── ui
│   │   │   │   ├── __init__.py
│   │   │   │   ├── message_buffer.py
│   │   │   │   └── renderer.py
│   │   │   └── utils
│   │   │       ├── __init__.py
│   │   │       ├── constants.py
│   │   │       └── exceptions.py
│   │   ├── logging
│   │   │   ├── __init__.py
│   │   │   └── utils.py
│   │   ├── message
│   │   │   ├── __init__.py
│   │   │   └── protocol.py
│   │   └── server
│   │       ├── __init__.py
│   │       ├── auth
│   │       │   └── __init__.py
│   │       ├── command.py
│   │       ├── commands
│   │       │   └── __init__.py
│   │       ├── interfaces
│   │       │   └── __init__.py
│   │       ├── manager.py
│   │       ├── routing
│   │       │   └── __init__.py
│   │       ├── session
│   │       │   └── __init__.py
│   │       ├── transport
│   │       │   └── __init__.py
│   │       ├── utils
│   │       │   ├── __init__.py
│   │       │   └── helpers.py
│   │       └── websocket_manager.py
│   ├── plugins
│   │   ├── __init__.py
│   │   ├── base.py
│   │   ├── context.py
│   │   ├── exceptions.py
│   │   ├── loader.py
│   │   ├── manager.py
│   │   └── registry.py
│   ├── start
│   │   ├── api.py
│   │   ├── client.py
│   │   └── server.py
│   └── test
│       ├── __init__.py
│       ├── test_api.py
│       ├── test_fix.py
│       └── test_server_refactor.py
├── CHANGELOG.md
├── LICENSE
├── NOTICE
├── README-zh.md
├── README.md
├── SECURITY.md
├── TODOs.md
├── __main__.py
├── docs
│   ├── LOGGING.md
│   └── WS_SERVER.md
├── feedback.json
├── logs
│   ├── dev
│   └── gui_state.json
├── qodana.yaml
├── requirements-dev.txt
├── requirements.txt
├── tools
│   ├── generate_hashes.py
│   ├── key_press.py
│   ├── packing.py
│   └── update_version.py
└── user_credentials.json
```

## Installation

```bash
# Clone the repository
git clone https://github.com/your-repo/AloneChat.git
cd AloneChat

# Create virtual environment
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

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `ALONECHAT_ENV` | Environment (development/production/testing) | development |
| `JWT_SECRET` | JWT signing secret | (change in production!) |

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
- GUI powered by [customtkinter](https://github.com/TomSchimansky/CustomTkinter)
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
