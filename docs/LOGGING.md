# AloneChat Unified Logging System

```
┌─────────────────────────────────────────┐
│         LoggingManager (Singleton)      │
├─────────────────────────────────────────┤
│  ┌─────────────┐    ┌───────────────┐   │
│  │   Console   │    │  File Handler │   │
│  │  Handler    │    │  (Rotating)   │   │
│  │  (Colored)  │    │               │   │
│  └─────────────┘    └───────────────┘   │
│         │                    │          │
│         ▼                    ▼          │
│  ┌───────────────────────────────────┐  │
│  │      LogConfig (dataclass)        │  │
│  │  - level, log_dir, max_bytes      │  │
│  │  - backup_count, format_string    │  │
│  └───────────────────────────────────┘  │
└─────────────────────────────────────────┘
```

## Overview

The AloneChat application features a unified logging system that provides consistent logging functionality across all components. The system supports multiple log levels, output destinations, and environment-specific configurations.

## Features

- **Standardized Log Formats**: Consistent formatting across all modules
- **Multiple Severity Levels**: DEBUG, INFO, WARNING, ERROR, CRITICAL (FATAL)
- **Dual Output**: Console and file-based logging
- **Log Rotation**: Automatic rotation based on file size
- **Environment-Specific Configs**: Different settings for dev/prod/test
- **Colored Console Output**: Color-coded log levels for better readability
- **Structured Logging**: JSON format support for log aggregation
- **Component-Specific Levels**: Fine-grained control over logging verbosity

## Quick Start

### Basic Usage

```python
from AloneChat.core.logging import get_logger

logger = get_logger(__name__)

logger.debug("Debug information")
logger.info("Application started")
logger.warning("Warning message")
logger.error("Error occurred", exc_info=True)
logger.critical("Critical failure")
```

### Automatic Configuration

```python
from AloneChat.core.logging import auto_configure

# Auto-detect environment from ALONECHAT_ENV variable
auto_configure()

# Or specify explicitly
auto_configure(env="development")
```

### Manual Configuration

```python
from AloneChat.core.logging import configure_logging, LogConfig

config = LogConfig(
    level="DEBUG",
    log_dir="./logs",
    max_bytes=10*1024*1024,  # 10MB
    backup_count=5,
    console_output=True,
    file_output=True
)

configure_logging(config)
```

## Configuration Options

### LogConfig Attributes

| Attribute | Type | Default | Description |
|-----------|------|---------|-------------|
| `level` | str | "INFO" | Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL) |
| `log_dir` | str | "./logs" | Directory for log files |
| `console_output` | bool | True | Enable console output |
| `file_output` | bool | True | Enable file output |
| `max_bytes` | int | 10MB | Maximum log file size before rotation |
| `backup_count` | int | 5 | Number of backup files to keep |
| `format_string` | str | None | Custom log format |
| `date_format` | str | "%Y-%m-%d %H:%M:%S" | Date format string |
| `component_levels` | Dict[str, str] | {} | Per-component log levels |

### Environment-Specific Configurations

#### Development
```python
from AloneChat.core.logging import create_development_config

config = create_development_config()
# - Level: DEBUG
# - Console: Enabled with colors
# - File: Enabled, 5MB rotation, 3 backups
# - Detailed format with file/line info
```

#### Production
```python
from AloneChat.core.logging import create_production_config

config = create_production_config()
# - Level: INFO
# - Console: Disabled
# - File: Enabled, 50MB rotation, 10 backups
# - Detailed format
```

#### Testing
```python
from AloneChat.core.logging import create_testing_config

config = create_testing_config()
# - Level: DEBUG
# - Console: Enabled, simple format
# - File: Disabled
```

## Logging Utilities

### Performance Timing

```python
from AloneChat.core.logging.utils import LogTimer, timed

# Context manager
with LogTimer("database_query"):
    result = db.execute(query)

# Decorator
@timed("api_call")
def fetch_data():
    return api.get_data()
```

### Request Logging

```python
from AloneChat.core.logging.utils import RequestLogger

request_logger = RequestLogger()

# HTTP request
request_logger.log_request(
    method="GET",
    path="/api/users",
    status_code=200,
    duration=0.123,
    user="john_doe"
)

# WebSocket event
request_logger.log_websocket_event(
    event_type="connect",
    user="john_doe"
)
```

### Exception Logging

```python
from AloneChat.core.logging.utils import ExceptionLogger

exception_logger = ExceptionLogger()

try:
    risky_operation()
except Exception as e:
    exception_logger.log_exception(e, context="Processing payment")
```

### Metrics Collection

```python
from AloneChat.core.logging.utils import MetricsCollector

metrics = MetricsCollector()

# Record metrics
metrics.increment("requests.total")
metrics.increment("requests.errors")
metrics.record_timing("request.duration", 0.123)

# Log summary
metrics.log_summary()
```

## Integration with Server Components

### WebSocket Manager

```python
from AloneChat.core.server import UnifiedWebSocketManager
from AloneChat.core.logging import get_logger

logger = get_logger(__name__)

manager = UnifiedWebSocketManager()

# The manager uses the unified logging system internally
# Logs are automatically written to configured destinations
```

### Custom Hooks with Logging

```python
from AloneChat.core.server import HookPhase, HookContext

def log_connection(ctx: HookContext) -> HookContext:
    logger = get_logger("hooks.connection")
    
    if ctx.phase == HookPhase.POST_CONNECT:
        logger.info("User connected: %s", ctx.user_id)
    elif ctx.phase == HookPhase.POST_DISCONNECT:
        logger.info("User disconnected: %s", ctx.user_id)
    
    return ctx

manager.register_hook(HookPhase.POST_CONNECT, log_connection)
manager.register_hook(HookPhase.POST_DISCONNECT, log_connection)
```

## Log File Locations

By default, log files are stored in the following locations:

- **Development**: `./logs/dev/`
- **Production**: `./logs/prod/`
- **Testing**: `./logs/test/`

### File Structure

```
logs/
├── dev/
│   ├── alonechat.log          # Main log file
│   └── alonechat_errors.log   # Error-only log
├── prod/
│   ├── alonechat.log
│   ├── alonechat.log.1        # Rotated backup
│   ├── alonechat.log.2
│   └── alonechat_errors.log
└── test/
    └── alonechat.log
```

## Command-Line Usage

### Environment Selection

```bash
# Start with development logging
python -m AloneChat server --env development

# Start with production logging
python -m AloneChat server --env production

# Start with testing logging
python -m AloneChat server --env testing
```

### Environment Variable

```bash
export ALONECHAT_ENV=production
python -m AloneChat server
```

## Best Practices

### 1. Use Module-Level Loggers

```python
# Good
logger = get_logger(__name__)

# Avoid
logger = get_logger("my_module")  # Hardcoded name
```

### 2. Log at Appropriate Levels

```python
logger.debug("Detailed information for debugging")
logger.info("General information about application flow")
logger.warning("Something unexpected but not critical")
logger.error("An error occurred", exc_info=True)
logger.critical("Application cannot continue")
```

### 3. Include Context

```python
# Good
logger.info("User %s logged in from %s", username, ip_address)

# Avoid
logger.info("User logged in")
```

### 4. Use Structured Data

```python
# Good
logger.info("Processing request", extra={
    "request_id": req_id,
    "user_id": user_id,
    "duration": duration
})
```

### 5. Handle Sensitive Data

```python
# Never log sensitive information
logger.info("User password: %s", password)  # BAD!

# Instead, log safe identifiers
logger.info("User authentication attempt for user_id: %s", user_id)
```

## Troubleshooting

### Logs Not Appearing

1. Check log level configuration
2. Verify log directory permissions
3. Ensure handlers are properly configured

### Disk Space Issues

1. Adjust `max_bytes` and `backup_count`
2. Implement log cleanup policies
3. Monitor log directory size

### Performance Impact

1. Use appropriate log levels in production
2. Disable console output in high-throughput scenarios
3. Use async logging for critical paths

## Migration Guide

### From Standard Logging

```python
# Old way
import logging
logger = logging.getLogger(__name__)

# New way
from AloneChat.core.logging import get_logger
logger = get_logger(__name__)
```

### Configuration Migration

```python
# Old way
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)

# New way
from AloneChat.core.logging import auto_configure
auto_configure()
```

## API Reference

See the module docstrings for detailed API documentation:
- `AloneChat.core.logging` - Core logging functionality
- `AloneChat.core.logging.utils` - Logging utilities and helpers
