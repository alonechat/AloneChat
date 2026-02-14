# AloneChat Unified WebSocket Server and Manager

```
Unified WebSocket manager that composes all server components.

This is the main entry point that orchestrates authentication,
session management, message routing, and command processing.

Enhanced with plugin system integration for pre/post processing hooks.

Architecture:
    ┌─────────────────────────────────────────────────────────────────┐
    │                    UnifiedWebSocketManager                      │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
    │  │ Auth        │  │ Session     │  │ Plugin Manager          │  │
    │  │ Middleware  │  │ Manager     │  │ (Pre/Post Hooks)        │  │
    │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
    │  │ Connection  │  │ Message     │  │ Command                 │  │
    │  │ Registry    │  │ Router      │  │ Processor               │  │
    │  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
    └─────────────────────────────────────────────────────────────────┘

```