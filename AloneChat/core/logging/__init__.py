"""
Unified logging system for AloneChat application.

Provides consistent logging functionality across the application with:
- Standardized log formats
- Multiple severity levels (DEBUG, INFO, WARN, ERROR, FATAL)
- Console and file-based output
- Configurable log rotation
- Environment-specific configurations

Usage:
    from AloneChat.core.logging import get_logger
    
    logger = get_logger(__name__)
    logger.info("Application started")
    logger.error("An error occurred", exc_info=True)

Configuration:
    from AloneChat.core.logging import configure_logging, LogConfig
    
    config = LogConfig(
        level="DEBUG",
        log_dir="./logs",
        max_bytes=10*1024*1024,  # 10MB
        backup_count=5
    )
    configure_logging(config)
"""

import logging
import logging.handlers
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Union


class LogLevel:
    """Log level constants."""
    DEBUG = logging.DEBUG
    INFO = logging.INFO
    WARNING = logging.WARNING
    ERROR = logging.ERROR
    CRITICAL = logging.CRITICAL
    FATAL = logging.CRITICAL


@dataclass
class LogConfig:
    """
    Configuration for the logging system.
    
    Attributes:
        level: Minimum log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: Directory for log files
        console_output: Whether to output to console
        file_output: Whether to output to file
        max_bytes: Maximum size of log file before rotation (bytes)
        backup_count: Number of backup files to keep
        format_string: Custom format string for log messages
        date_format: Custom date format string
        component_levels: Dict mapping component names to log levels
    """
    level: str = "INFO"
    log_dir: str = "./logs"
    console_output: bool = True
    file_output: bool = True
    max_bytes: int = 10 * 1024 * 1024  # 10MB
    backup_count: int = 5
    format_string: Optional[str] = None
    date_format: str = "%Y-%m-%d %H:%M:%S"
    component_levels: Dict[str, str] = field(default_factory=dict)


class ColoredFormatter(logging.Formatter):
    """
    Formatter that adds color to console output.
    """
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[36m',      # Cyan
        'INFO': '\033[32m',       # Green
        'WARNING': '\033[33m',    # Yellow
        'ERROR': '\033[31m',      # Red
        'CRITICAL': '\033[35m',   # Magenta
        'RESET': '\033[0m'        # Reset
    }
    
    def __init__(self, fmt: str, datefmt: str = None, use_colors: bool = True):
        super().__init__(fmt, datefmt)
        self.use_colors = use_colors and sys.platform != 'win32'
    
    def format(self, record: logging.LogRecord) -> str:
        if self.use_colors:
            levelname = record.levelname
            if levelname in self.COLORS:
                record.levelname = f"{self.COLORS[levelname]}{levelname}{self.COLORS['RESET']}"
        
        return super().format(record)


class JsonFormatter(logging.Formatter):
    """
    Formatter that outputs log records as JSON.
    Useful for structured logging and log aggregation.
    """
    
    def format(self, record: logging.LogRecord) -> str:
        import json
        
        log_data = {
            'timestamp': datetime.fromtimestamp(record.created).isoformat(),
            'level': record.levelname,
            'logger': record.name,
            'message': record.getMessage(),
            'module': record.module,
            'function': record.funcName,
            'line': record.lineno,
        }
        
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        
        if hasattr(record, 'extra_data'):
            log_data.update(record.extra_data)
        
        return json.dumps(log_data, default=str)


def get_default_format() -> str:
    """Get the default log format string."""
    return "%(asctime)s - %(name)s - %(levelname)s - %(message)s"


def get_detailed_format() -> str:
    """Get a detailed log format string with more context."""
    return (
        "%(asctime)s - %(name)s - %(levelname)s - "
        "[%(filename)s:%(lineno)d - %(funcName)s] - %(message)s"
    )


class LoggingManager:
    """
    Centralized logging manager for the application.
    
    Handles configuration, setup, and management of loggers across
    all components.
    """
    
    _instance: Optional['LoggingManager'] = None
    _initialized: bool = False
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if self._initialized:
            return
        
        self._config: Optional[LogConfig] = None
        self._handlers: List[logging.Handler] = []
        self._initialized = True
    
    def configure(self, config: LogConfig) -> None:
        """
        Configure the logging system.
        
        Args:
            config: Logging configuration
        """
        self._config = config
        
        # Create log directory if needed
        if config.file_output:
            Path(config.log_dir).mkdir(parents=True, exist_ok=True)
        
        # Get root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, config.level.upper()))
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        self._handlers = []
        
        # Add console handler
        if config.console_output:
            console_handler = logging.StreamHandler(sys.stdout)
            console_handler.setLevel(getattr(logging, config.level.upper()))
            
            fmt = config.format_string or get_default_format()
            formatter = ColoredFormatter(fmt, config.date_format)
            console_handler.setFormatter(formatter)
            
            root_logger.addHandler(console_handler)
            self._handlers.append(console_handler)
        
        # Add file handler with rotation
        if config.file_output:
            log_file = os.path.join(config.log_dir, "alonechat.log")
            file_handler = logging.handlers.RotatingFileHandler(
                log_file,
                maxBytes=config.max_bytes,
                backupCount=config.backup_count,
                encoding='utf-8'
            )
            file_handler.setLevel(getattr(logging, config.level.upper()))
            
            fmt = config.format_string or get_detailed_format()
            formatter = logging.Formatter(fmt, config.date_format)
            file_handler.setFormatter(formatter)
            
            root_logger.addHandler(file_handler)
            self._handlers.append(file_handler)
            
            # Add error file handler for errors only
            error_log_file = os.path.join(config.log_dir, "alonechat_errors.log")
            error_handler = logging.handlers.RotatingFileHandler(
                error_log_file,
                maxBytes=config.max_bytes,
                backupCount=config.backup_count,
                encoding='utf-8'
            )
            error_handler.setLevel(logging.ERROR)
            error_handler.setFormatter(formatter)
            
            root_logger.addHandler(error_handler)
            self._handlers.append(error_handler)
        
        # Configure component-specific levels
        for component, level in config.component_levels.items():
            component_logger = logging.getLogger(component)
            component_logger.setLevel(getattr(logging, level.upper()))
        
        logging.info("Logging system configured with level: %s", config.level)
    
    def get_logger(self, name: str) -> logging.Logger:
        """
        Get a logger instance.
        
        Args:
            name: Logger name (typically __name__)
            
        Returns:
            Configured logger instance
        """
        return logging.getLogger(name)
    
    def set_level(self, level: Union[str, int]) -> None:
        """
        Set the global log level.
        
        Args:
            level: Log level (string or logging constant)
        """
        if isinstance(level, str):
            level = getattr(logging, level.upper())
        
        root_logger = logging.getLogger()
        root_logger.setLevel(level)
        
        for handler in self._handlers:
            handler.setLevel(level)
    
    def add_handler(self, handler: logging.Handler) -> None:
        """
        Add a custom handler to the logging system.
        
        Args:
            handler: Handler to add
        """
        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        self._handlers.append(handler)
    
    def shutdown(self) -> None:
        """Shutdown the logging system gracefully."""
        logging.info("Shutting down logging system")
        logging.shutdown()


# Global logging manager instance
_logging_manager = LoggingManager()


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance.
    
    Args:
        name: Logger name (typically __name__)
        
    Returns:
        Configured logger instance
    """
    return _logging_manager.get_logger(name)


def configure_logging(config: LogConfig) -> None:
    """
    Configure the logging system.
    
    Args:
        config: Logging configuration
    """
    _logging_manager.configure(config)


def get_logging_manager() -> LoggingManager:
    """Get the global logging manager instance."""
    return _logging_manager


def create_development_config() -> LogConfig:
    """
    Create a logging configuration for development environment.
    
    Returns:
        Development logging configuration
    """
    return LogConfig(
        level="DEBUG",
        log_dir="./logs/dev",
        console_output=True,
        file_output=True,
        max_bytes=5 * 1024 * 1024,  # 5MB
        backup_count=3,
        format_string=get_detailed_format(),
        component_levels={
            "websockets": "WARNING",
            "urllib3": "WARNING",
        }
    )


def create_production_config() -> LogConfig:
    """
    Create a logging configuration for production environment.
    
    Returns:
        Production logging configuration
    """
    return LogConfig(
        level="INFO",
        log_dir="./logs/prod",
        console_output=False,
        file_output=True,
        max_bytes=50 * 1024 * 1024,  # 50MB
        backup_count=10,
        format_string=get_detailed_format(),
        component_levels={
            "websockets": "ERROR",
            "urllib3": "ERROR",
        }
    )


def create_testing_config() -> LogConfig:
    """
    Create a logging configuration for testing environment.
    
    Returns:
        Testing logging configuration
    """
    return LogConfig(
        level="DEBUG",
        log_dir="./logs/test",
        console_output=True,
        file_output=False,
        format_string="%(levelname)s - %(message)s",
        component_levels={
            "websockets": "ERROR",
        }
    )


def auto_configure(env: Optional[str] = None) -> None:
    """
    Automatically configure logging based on environment.
    
    Args:
        env: Environment name (development, production, testing).
             If None, tries to detect from environment variables.
    """
    if env is None:
        env = os.environ.get("ALONECHAT_ENV", "development").lower()
    
    configs = {
        "development": create_development_config(),
        "dev": create_development_config(),
        "production": create_production_config(),
        "prod": create_production_config(),
        "testing": create_testing_config(),
        "test": create_testing_config(),
    }
    
    config = configs.get(env, create_development_config())
    configure_logging(config)
    
    logger = get_logger(__name__)
    logger.info("Logging auto-configured for environment: %s", env)


__all__ = [
    'LogLevel',
    'LogConfig',
    'LoggingManager',
    'ColoredFormatter',
    'JsonFormatter',
    'get_logger',
    'configure_logging',
    'get_logging_manager',
    'create_development_config',
    'create_production_config',
    'create_testing_config',
    'auto_configure',
    'get_default_format',
    'get_detailed_format',
]
