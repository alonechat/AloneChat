"""
Tests for the logging system in AloneChat.

Tests cover:
- All log levels (DEBUG, INFO, WARNING, ERROR, CRITICAL)
- Log configuration
- Log formatters
- Exception logging with exc_info
- Log handlers
"""

import io
import logging
import sys
from unittest.mock import MagicMock, patch

import pytest

from AloneChat.core.logging import (
    LogConfig,
    LogLevel,
    LoggingManager,
    ColoredFormatter,
    JsonFormatter,
    get_logger,
    configure_logging,
    get_logging_manager,
    create_development_config,
    create_production_config,
    create_testing_config,
    get_default_format,
    get_detailed_format,
)
from AloneChat.core.logging.utils import (
    LogTimer,
    timed,
    RequestLogger,
    log_context,
    ExceptionLogger,
    log_call,
    MetricsCollector,
)


class TestLogLevels:
    """Tests for all log levels."""

    def setup_method(self):
        """Set up test fixtures."""
        self.log_capture = io.StringIO()
        self.handler = logging.StreamHandler(self.log_capture)
        self.handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        
        self.logger = logging.getLogger('test_logger')
        self.logger.setLevel(logging.DEBUG)
        self.logger.handlers = [self.handler]

    def teardown_method(self):
        """Clean up after tests."""
        self.logger.handlers.clear()
        self.log_capture.close()

    def test_debug_level(self):
        """Test DEBUG level logging."""
        self.logger.debug("Debug message")
        output = self.log_capture.getvalue()
        assert "DEBUG - Debug message" in output

    def test_info_level(self):
        """Test INFO level logging."""
        self.logger.info("Info message")
        output = self.log_capture.getvalue()
        assert "INFO - Info message" in output

    def test_warning_level(self):
        """Test WARNING level logging."""
        self.logger.warning("Warning message")
        output = self.log_capture.getvalue()
        assert "WARNING - Warning message" in output

    def test_error_level(self):
        """Test ERROR level logging."""
        self.logger.error("Error message")
        output = self.log_capture.getvalue()
        assert "ERROR - Error message" in output

    def test_critical_level(self):
        """Test CRITICAL level logging."""
        self.logger.critical("Critical message")
        output = self.log_capture.getvalue()
        assert "CRITICAL - Critical message" in output

    def test_exception_with_exc_info(self):
        """Test exception logging with exc_info=True includes traceback."""
        try:
            raise ValueError("Test exception")
        except ValueError:
            self.logger.error("Exception occurred", exc_info=True)
        
        output = self.log_capture.getvalue()
        assert "ERROR - Exception occurred" in output
        assert "ValueError: Test exception" in output
        assert "Traceback" in output

    def test_warning_with_exc_info(self):
        """Test warning logging with exc_info=True includes traceback."""
        try:
            raise RuntimeError("Test warning exception")
        except RuntimeError:
            self.logger.warning("Warning with exception", exc_info=True)
        
        output = self.log_capture.getvalue()
        assert "WARNING - Warning with exception" in output
        assert "RuntimeError: Test warning exception" in output


class TestLogLevelConstants:
    """Tests for LogLevel constants."""

    def test_debug_constant(self):
        """Test DEBUG level constant."""
        assert LogLevel.DEBUG == logging.DEBUG
        assert LogLevel.DEBUG == 10

    def test_info_constant(self):
        """Test INFO level constant."""
        assert LogLevel.INFO == logging.INFO
        assert LogLevel.INFO == 20

    def test_warning_constant(self):
        """Test WARNING level constant."""
        assert LogLevel.WARNING == logging.WARNING
        assert LogLevel.WARNING == 30

    def test_error_constant(self):
        """Test ERROR level constant."""
        assert LogLevel.ERROR == logging.ERROR
        assert LogLevel.ERROR == 40

    def test_critical_constant(self):
        """Test CRITICAL level constant."""
        assert LogLevel.CRITICAL == logging.CRITICAL
        assert LogLevel.CRITICAL == 50

    def test_fatal_alias(self):
        """Test FATAL is alias for CRITICAL."""
        assert LogLevel.FATAL == LogLevel.CRITICAL


class TestLogConfig:
    """Tests for LogConfig dataclass."""

    def test_default_config(self):
        """Test default configuration values."""
        config = LogConfig()
        
        assert config.level == "INFO"
        assert config.log_dir == "./logs"
        assert config.console_output is True
        assert config.file_output is True
        assert config.max_bytes == 10 * 1024 * 1024
        assert config.backup_count == 5
        assert config.component_levels == {}

    def test_custom_config(self):
        """Test custom configuration values."""
        config = LogConfig(
            level="DEBUG",
            log_dir="/var/log/alonechat",
            console_output=False,
            file_output=True,
            max_bytes=20 * 1024 * 1024,
            backup_count=10,
        )
        
        assert config.level == "DEBUG"
        assert config.log_dir == "/var/log/alonechat"
        assert config.console_output is False
        assert config.file_output is True
        assert config.max_bytes == 20 * 1024 * 1024
        assert config.backup_count == 10


class TestColoredFormatter:
    """Tests for ColoredFormatter."""

    def test_format_debug(self):
        """Test formatting DEBUG level."""
        formatter = ColoredFormatter('%(levelname)s - %(message)s', use_colors=True)
        record = logging.LogRecord(
            name='test', level=logging.DEBUG, pathname='', lineno=0,
            msg='Debug message', args=(), exc_info=None
        )
        
        result = formatter.format(record)
        assert '\033[36m' in result  # Cyan color
        assert 'DEBUG' in result

    def test_format_info(self):
        """Test formatting INFO level."""
        formatter = ColoredFormatter('%(levelname)s - %(message)s', use_colors=True)
        record = logging.LogRecord(
            name='test', level=logging.INFO, pathname='', lineno=0,
            msg='Info message', args=(), exc_info=None
        )
        
        result = formatter.format(record)
        assert '\033[32m' in result  # Green color

    def test_format_warning(self):
        """Test formatting WARNING level."""
        formatter = ColoredFormatter('%(levelname)s - %(message)s', use_colors=True)
        record = logging.LogRecord(
            name='test', level=logging.WARNING, pathname='', lineno=0,
            msg='Warning message', args=(), exc_info=None
        )
        
        result = formatter.format(record)
        assert '\033[33m' in result  # Yellow color

    def test_format_error(self):
        """Test formatting ERROR level."""
        formatter = ColoredFormatter('%(levelname)s - %(message)s', use_colors=True)
        record = logging.LogRecord(
            name='test', level=logging.ERROR, pathname='', lineno=0,
            msg='Error message', args=(), exc_info=None
        )
        
        result = formatter.format(record)
        assert '\033[31m' in result  # Red color

    def test_format_critical(self):
        """Test formatting CRITICAL level."""
        formatter = ColoredFormatter('%(levelname)s - %(message)s', use_colors=True)
        record = logging.LogRecord(
            name='test', level=logging.CRITICAL, pathname='', lineno=0,
            msg='Critical message', args=(), exc_info=None
        )
        
        result = formatter.format(record)
        assert '\033[35m' in result  # Magenta color

    def test_no_colors_on_windows(self):
        """Test that colors are disabled on Windows."""
        with patch('sys.platform', 'win32'):
            formatter = ColoredFormatter('%(levelname)s - %(message)s', use_colors=True)
            assert formatter.use_colors is False


class TestJsonFormatter:
    """Tests for JsonFormatter."""

    def test_format_basic(self):
        """Test basic JSON formatting."""
        import json
        
        formatter = JsonFormatter()
        record = logging.LogRecord(
            name='test.logger', level=logging.INFO, pathname='test.py', lineno=42,
            msg='Test message', args=(), exc_info=None
        )
        record.funcName = 'test_func'
        record.module = 'test'
        
        result = formatter.format(record)
        data = json.loads(result)
        
        assert data['level'] == 'INFO'
        assert data['logger'] == 'test.logger'
        assert data['message'] == 'Test message'
        assert data['module'] == 'test'
        assert data['function'] == 'test_func'
        assert data['line'] == 42

    def test_format_with_exception(self):
        """Test JSON formatting with exception info."""
        import json
        
        formatter = JsonFormatter()
        
        try:
            raise ValueError("Test error")
        except ValueError:
            import sys
            exc_info = sys.exc_info()
        
        record = logging.LogRecord(
            name='test.logger', level=logging.ERROR, pathname='test.py', lineno=42,
            msg='Error occurred', args=(), exc_info=exc_info
        )
        record.funcName = 'test_func'
        record.module = 'test'
        
        result = formatter.format(record)
        data = json.loads(result)
        
        assert 'exception' in data
        assert 'ValueError: Test error' in data['exception']


class TestLoggingManager:
    """Tests for LoggingManager."""

    def test_singleton_pattern(self):
        """Test that LoggingManager is a singleton."""
        manager1 = LoggingManager()
        manager2 = LoggingManager()
        
        assert manager1 is manager2

    def test_get_logger(self):
        """Test getting a logger instance."""
        manager = LoggingManager()
        logger = manager.get_logger('test.module')
        
        assert isinstance(logger, logging.Logger)
        assert logger.name == 'test.module'

    def test_configure_with_console_only(self):
        """Test configuration with console output only."""
        manager = LoggingManager()
        config = LogConfig(
            level="DEBUG",
            console_output=True,
            file_output=False,
        )
        
        manager.configure(config)
        
        root_logger = logging.getLogger()
        assert len([h for h in root_logger.handlers if isinstance(h, logging.StreamHandler)]) >= 1


class TestLogTimer:
    """Tests for LogTimer context manager."""

    def test_timer_success(self):
        """Test timer logs duration on success."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        test_logger = logging.getLogger('timer_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        with LogTimer("test_operation", logger=test_logger):
            pass
        
        output = log_capture.getvalue()
        assert "test_operation" in output
        assert "completed" in output

    def test_timer_with_exception(self):
        """Test timer logs error on exception."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(logging.Formatter('%(message)s'))
        
        test_logger = logging.getLogger('timer_exception_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        with pytest.raises(ValueError):
            with LogTimer("failing_operation", logger=test_logger):
                raise ValueError("Test error")
        
        output = log_capture.getvalue()
        assert "failing_operation" in output
        assert "failed" in output


class TestTimedDecorator:
    """Tests for timed decorator."""

    def test_timed_success(self):
        """Test timed decorator logs on success."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        test_logger = logging.getLogger('timed_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        @timed("test_func", logger=test_logger)
        def my_func():
            return "result"
        
        result = my_func()
        
        assert result == "result"
        output = log_capture.getvalue()
        assert "test_func" in output


class TestExceptionLogger:
    """Tests for ExceptionLogger."""

    def test_log_exception(self):
        """Test logging an exception."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        
        test_logger = logging.getLogger('exception_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        exc_logger = ExceptionLogger(test_logger)
        
        try:
            raise ValueError("Test exception")
        except ValueError as e:
            exc_logger.log_exception(e, context="Test context")
        
        output = log_capture.getvalue()
        assert "ERROR" in output
        assert "Test context" in output

    def test_log_warning_with_exception(self):
        """Test logging a warning with exception."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        handler.setFormatter(logging.Formatter('%(levelname)s - %(message)s'))
        
        test_logger = logging.getLogger('warning_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        exc_logger = ExceptionLogger(test_logger)
        exc_logger.log_warning("Warning message", exception=ValueError("Test"))
        
        output = log_capture.getvalue()
        assert "WARNING" in output
        assert "Warning message" in output


class TestRequestLogger:
    """Tests for RequestLogger."""

    def test_log_request_success(self):
        """Test logging successful HTTP request."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        test_logger = logging.getLogger('request_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        req_logger = RequestLogger(test_logger)
        req_logger.log_request("GET", "/api/test", 200, 0.05, user="testuser")
        
        output = log_capture.getvalue()
        assert "GET" in output
        assert "/api/test" in output
        assert "200" in output

    def test_log_request_error(self):
        """Test logging failed HTTP request."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        test_logger = logging.getLogger('request_error_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        req_logger = RequestLogger(test_logger)
        req_logger.log_request("POST", "/api/error", 500, 0.1)
        
        output = log_capture.getvalue()
        assert "POST" in output
        assert "500" in output

    def test_log_websocket_connect(self):
        """Test logging WebSocket connect event."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        test_logger = logging.getLogger('ws_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        req_logger = RequestLogger(test_logger)
        req_logger.log_websocket_event("connect", "testuser")
        
        output = log_capture.getvalue()
        assert "connect" in output
        assert "testuser" in output


class TestMetricsCollector:
    """Tests for MetricsCollector."""

    def test_increment(self):
        """Test incrementing a counter."""
        collector = MetricsCollector()
        collector.increment("requests")
        collector.increment("requests", 5)
        
        assert collector._counts["requests"] == 6

    def test_record_timing(self):
        """Test recording timing."""
        collector = MetricsCollector()
        collector.record_timing("query_time", 0.1)
        collector.record_timing("query_time", 0.2)
        
        assert len(collector._timings["query_time"]) == 2

    def test_reset(self):
        """Test resetting metrics."""
        collector = MetricsCollector()
        collector.increment("requests")
        collector.record_timing("time", 0.1)
        
        collector.reset()
        
        assert collector._counts == {}
        assert collector._timings == {}


class TestEnvironmentConfigs:
    """Tests for environment-specific configurations."""

    def test_development_config(self):
        """Test development configuration."""
        config = create_development_config()
        
        assert config.level == "DEBUG"
        assert config.console_output is True
        assert config.file_output is True

    def test_production_config(self):
        """Test production configuration."""
        config = create_production_config()
        
        assert config.level == "INFO"
        assert config.console_output is False
        assert config.file_output is True

    def test_testing_config(self):
        """Test testing configuration."""
        config = create_testing_config()
        
        assert config.level == "DEBUG"
        assert config.console_output is True
        assert config.file_output is False


class TestFormatStrings:
    """Tests for format string functions."""

    def test_default_format(self):
        """Test default format string."""
        fmt = get_default_format()
        
        assert '%(asctime)s' in fmt
        assert '%(name)s' in fmt
        assert '%(levelname)s' in fmt
        assert '%(message)s' in fmt

    def test_detailed_format(self):
        """Test detailed format string."""
        fmt = get_detailed_format()
        
        assert '%(asctime)s' in fmt
        assert '%(name)s' in fmt
        assert '%(levelname)s' in fmt
        assert '%(filename)s' in fmt
        assert '%(lineno)d' in fmt
        assert '%(funcName)s' in fmt
        assert '%(message)s' in fmt


class TestLogCallDecorator:
    """Tests for log_call decorator."""

    def test_log_call_with_args(self):
        """Test log_call decorator logs arguments."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        test_logger = logging.getLogger('logcall_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        @log_call(logger=test_logger, log_args=True)
        def add(a, b):
            return a + b
        
        result = add(1, 2)
        
        assert result == 3
        output = log_capture.getvalue()
        assert "add" in output

    def test_log_call_with_exception(self):
        """Test log_call decorator logs exceptions."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        test_logger = logging.getLogger('logcall_exception_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        @log_call(logger=test_logger)
        def failing_func():
            raise ValueError("Test error")
        
        with pytest.raises(ValueError):
            failing_func()
        
        output = log_capture.getvalue()
        assert "ValueError" in output


class TestLogContext:
    """Tests for log_context context manager."""

    def test_log_context_success(self):
        """Test log_context logs entry and exit."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        test_logger = logging.getLogger('logctx_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        with log_context("test_operation", logger=test_logger):
            pass
        
        output = log_capture.getvalue()
        assert "Starting: test_operation" in output
        assert "Completed: test_operation" in output

    def test_log_context_with_exception(self):
        """Test log_context logs failure on exception."""
        log_capture = io.StringIO()
        handler = logging.StreamHandler(log_capture)
        
        test_logger = logging.getLogger('logctx_exception_test')
        test_logger.setLevel(logging.DEBUG)
        test_logger.handlers = [handler]
        
        with pytest.raises(ValueError):
            with log_context("failing_operation", logger=test_logger):
                raise ValueError("Test error")
        
        output = log_capture.getvalue()
        assert "Failed: failing_operation" in output


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
