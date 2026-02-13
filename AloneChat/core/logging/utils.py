"""
Logging utilities and helpers for the AloneChat application.

Provides additional functionality for common logging patterns:
- Performance timing decorators
- Context managers for scoped logging
- Request/response logging
- Exception tracking
"""

import functools
import logging
import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Optional, TypeVar

from AloneChat.core.logging import get_logger

F = TypeVar('F', bound=Callable[..., Any])


class LogTimer:
    """
    Context manager for timing operations and logging the duration.
    
    Example:
        with LogTimer("database_query"):
            result = db.execute(query)
    """
    
    def __init__(
        self,
        operation: str,
        logger: Optional[logging.Logger] = None,
        level: int = logging.DEBUG
    ):
        """
        Initialize the timer.
        
        Args:
            operation: Name of the operation being timed
            logger: Logger to use (defaults to root logger)
            level: Log level for the timing message
        """
        self.operation = operation
        self.logger = logger or get_logger(__name__)
        self.level = level
        self.start_time: Optional[float] = None
        self.duration: Optional[float] = None
    
    def __enter__(self) -> 'LogTimer':
        """Start the timer."""
        self.start_time = time.perf_counter()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Stop the timer and log the duration."""
        if self.start_time is not None:
            self.duration = time.perf_counter() - self.start_time
            
            if exc_type is not None:
                self.logger.error(
                    "Operation '%s' failed after %.4f seconds: %s",
                    self.operation, self.duration, exc_val
                )
            else:
                self.logger.log(
                    self.level,
                    "Operation '%s' completed in %.4f seconds",
                    self.operation, self.duration
                )


def timed(
    operation: Optional[str] = None,
    logger: Optional[logging.Logger] = None,
    level: int = logging.DEBUG
) -> Callable[[F], F]:
    """
    Decorator to time function execution and log the duration.
    
    Args:
        operation: Name of the operation (defaults to function name)
        logger: Logger to use
        level: Log level for the timing message
        
    Returns:
        Decorator function
        
    Example:
        @timed("database_query")
        def fetch_data():
            return db.query()
    """
    def decorator(func: F) -> F:
        nonlocal operation
        if operation is None:
            operation = func.__name__
        
        log = logger or get_logger(func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.perf_counter()
            try:
                result = func(*args, **kwargs)
                duration = time.perf_counter() - start_time
                log.log(
                    level,
                    "Operation '%s' completed in %.4f seconds",
                    operation, duration
                )
                return result
            except Exception as e:
                duration = time.perf_counter() - start_time
                log.error(
                    "Operation '%s' failed after %.4f seconds: %s",
                    operation, duration, e
                )
                raise
        
        return wrapper
    return decorator


class RequestLogger:
    """
    Utility for logging HTTP/WebSocket requests and responses.
    
    Tracks request metrics including duration, status, and errors.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the request logger.
        
        Args:
            logger: Logger to use
        """
        self.logger = logger or get_logger(__name__)
    
    def log_request(
        self,
        method: str,
        path: str,
        status_code: int,
        duration: float,
        user: Optional[str] = None,
        extra: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log an HTTP request.
        
        Args:
            method: HTTP method
            path: Request path
            status_code: Response status code
            duration: Request duration in seconds
            user: Optional user identifier
            extra: Additional data to log
        """
        level = logging.INFO if status_code < 400 else logging.WARNING
        
        message = f"{method} {path} - {status_code} ({duration:.4f}s)"
        if user:
            message += f" - User: {user}"
        
        self.logger.log(level, message, extra=extra or {})
    
    def log_websocket_event(
        self,
        event_type: str,
        user: str,
        data: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log a WebSocket event.
        
        Args:
            event_type: Type of event (connect, disconnect, message)
            user: User identifier
            data: Additional event data
        """
        message = f"WebSocket {event_type} - User: {user}"
        
        if event_type == "connect":
            level = logging.INFO
        elif event_type == "disconnect":
            level = logging.INFO
        elif event_type == "error":
            level = logging.ERROR
        else:
            level = logging.DEBUG
        
        self.logger.log(level, message, extra=data or {})


@contextmanager
def log_context(
    operation: str,
    logger: Optional[logging.Logger] = None,
    enter_message: Optional[str] = None,
    exit_message: Optional[str] = None
):
    """
    Context manager for scoped logging.
    
    Args:
        operation: Name of the operation
        logger: Logger to use
        enter_message: Message to log on entry
        exit_message: Message to log on exit
        
    Example:
        with log_context("data_processing"):
            process_data()
    """
    log = logger or get_logger(__name__)
    
    if enter_message is None:
        enter_message = f"Starting: {operation}"
    if exit_message is None:
        exit_message = f"Completed: {operation}"
    
    log.debug(enter_message)
    try:
        yield
        log.debug(exit_message)
    except Exception as e:
        log.error(f"Failed: {operation} - {e}")
        raise


class ExceptionLogger:
    """
    Utility for consistent exception logging.
    
    Provides methods for logging exceptions with additional context.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the exception logger.
        
        Args:
            logger: Logger to use
        """
        self.logger = logger or get_logger(__name__)
    
    def log_exception(
        self,
        exception: Exception,
        context: Optional[str] = None,
        level: int = logging.ERROR
    ) -> None:
        """
        Log an exception with context.
        
        Args:
            exception: The exception to log
            context: Additional context about where/why the exception occurred
            level: Log level
        """
        if context:
            self.logger.log(level, f"{context}: {exception}", exc_info=True)
        else:
            self.logger.log(level, str(exception), exc_info=True)
    
    def log_warning(self, message: str, exception: Optional[Exception] = None) -> None:
        """
        Log a warning message, optionally with an exception.
        
        Args:
            message: Warning message
            exception: Optional exception to include
        """
        if exception:
            self.logger.warning(f"{message}: {exception}")
        else:
            self.logger.warning(message)


def log_call(
    logger: Optional[logging.Logger] = None,
    level: int = logging.DEBUG,
    log_args: bool = True,
    log_result: bool = False
) -> Callable[[F], F]:
    """
    Decorator to log function calls.
    
    Args:
        logger: Logger to use
        level: Log level
        log_args: Whether to log function arguments
        log_result: Whether to log function result
        
    Returns:
        Decorator function
        
    Example:
        @log_call(log_args=True)
        def process_data(data):
            return transform(data)
    """
    def decorator(func: F) -> F:
        log = logger or get_logger(func.__module__)
        
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            func_name = func.__name__
            
            if log_args:
                args_str = ", ".join([
                    str(a) for a in args
                ] + [
                    f"{k}={v}" for k, v in kwargs.items()
                ])
                log.log(level, f"Calling {func_name}({args_str})")
            else:
                log.log(level, f"Calling {func_name}")
            
            try:
                result = func(*args, **kwargs)
                
                if log_result:
                    log.log(level, f"{func_name} returned: {result}")
                else:
                    log.log(level, f"{func_name} completed successfully")
                
                return result
            except Exception as e:
                log.error(f"{func_name} raised {type(e).__name__}: {e}")
                raise
        
        return wrapper
    return decorator


class MetricsCollector:
    """
    Collect and log application metrics.
    
    Tracks counts, timings, and other metrics for monitoring.
    """
    
    def __init__(self, logger: Optional[logging.Logger] = None):
        """
        Initialize the metrics collector.
        
        Args:
            logger: Logger to use
        """
        self.logger = logger or get_logger(__name__)
        self._counts: Dict[str, int] = {}
        self._timings: Dict[str, list] = {}
    
    def increment(self, metric: str, value: int = 1) -> None:
        """
        Increment a counter metric.
        
        Args:
            metric: Metric name
            value: Amount to increment
        """
        self._counts[metric] = self._counts.get(metric, 0) + value
    
    def record_timing(self, metric: str, duration: float) -> None:
        """
        Record a timing metric.
        
        Args:
            metric: Metric name
            duration: Duration in seconds
        """
        if metric not in self._timings:
            self._timings[metric] = []
        self._timings[metric].append(duration)
    
    def log_summary(self) -> None:
        """Log a summary of all collected metrics."""
        if self._counts:
            self.logger.info("=== Metrics Summary (Counts) ===")
            for metric, count in sorted(self._counts.items()):
                self.logger.info(f"  {metric}: {count}")
        
        if self._timings:
            self.logger.info("=== Metrics Summary (Timings) ===")
            for metric, timings in sorted(self._timings.items()):
                if timings:
                    avg = sum(timings) / len(timings)
                    min_val = min(timings)
                    max_val = max(timings)
                    self.logger.info(
                        f"  {metric}: avg={avg:.4f}s, min={min_val:.4f}s, max={max_val:.4f}s, count={len(timings)}"
                    )
    
    def reset(self) -> None:
        """Reset all metrics."""
        self._counts.clear()
        self._timings.clear()


__all__ = [
    'LogTimer',
    'timed',
    'RequestLogger',
    'log_context',
    'ExceptionLogger',
    'log_call',
    'MetricsCollector',
]
