# AloneChat

>[contect to us](http://47.98.235.177:38479/feedback.html)

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

- **Proposing features**: Edit README to shape our roadmap!
- **Reporting bugs**: File an issue!
- **Submitting code**: Fork → PR!
- **We need to hear you**: File an issue！We are happy to and some new things according to you!

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
