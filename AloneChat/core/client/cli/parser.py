"""
Command parser for AloneChat client.
Provides independent command-line parsing logic that can be used by any UI.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, List, Callable, Any

from ..utils import DEFAULT_HOST, DEFAULT_API_PORT


class CommandType(Enum):
    """Types of commands supported by the client."""
    # Connection commands
    CONNECT = auto()
    DISCONNECT = auto()
    RECONNECT = auto()
    
    # Configuration commands
    SET_HOST = auto()
    SET_PORT = auto()
    SET_USERNAME = auto()
    SET_UI = auto()
    
    # Information commands
    HELP = auto()
    STATUS = auto()
    
    # Control commands
    EXIT = auto()
    QUIT = auto()
    
    # Chat commands
    SEND = auto()
    JOIN = auto()
    LEAVE = auto()
    
    # Unknown/invalid
    UNKNOWN = auto()
    EMPTY = auto()


@dataclass
class Command:
    """Represents a parsed command."""
    type: CommandType
    raw: str
    args: List[str]
    kwargs: dict
    error_message: Optional[str] = None
    
    @property
    def is_valid(self) -> bool:
        """Check if command is valid."""
        return self.type not in (CommandType.UNKNOWN, CommandType.EMPTY)
    
    @property
    def has_error(self) -> bool:
        """Check if command has an error."""
        return self.error_message is not None


class CommandParser:
    """
    Independent command parser for AloneChat client.
    Parses command strings into Command objects.
    """
    
    # Command aliases mapping
    COMMAND_ALIASES = {
        # Connection
        'connect': CommandType.CONNECT,
        'conn': CommandType.CONNECT,
        'disconnect': CommandType.DISCONNECT,
        'dc': CommandType.DISCONNECT,
        'reconnect': CommandType.RECONNECT,
        
        # Configuration
        'host': CommandType.SET_HOST,
        'port': CommandType.SET_PORT,
        'username': CommandType.SET_USERNAME,
        'user': CommandType.SET_USERNAME,
        'ui': CommandType.SET_UI,
        
        # Information
        'help': CommandType.HELP,
        '?': CommandType.HELP,
        'status': CommandType.STATUS,
        'info': CommandType.STATUS,
        
        # Control
        'exit': CommandType.EXIT,
        'quit': CommandType.QUIT,
        'q': CommandType.QUIT,
        
        # Chat
        'send': CommandType.SEND,
        's': CommandType.SEND,
        'join': CommandType.JOIN,
        'j': CommandType.JOIN,
        'leave': CommandType.LEAVE,
        'part': CommandType.LEAVE,
    }
    
    def __init__(self):
        """Initialize the command parser."""
        self._command_handlers: dict[CommandType, Callable[[Command], Any]] = {}
    
    def register_handler(self, command_type: CommandType, handler: Callable[[Command], Any]) -> None:
        """
        Register a handler for a specific command type.
        
        Args:
            command_type: Type of command to handle
            handler: Function to call when command is received
        """
        self._command_handlers[command_type] = handler
    
    def parse(self, input_line: str) -> Command:
        """
        Parse a command string into a Command object.
        
        Args:
            input_line: Raw input string from user
            
        Returns:
            Parsed Command object
        """
        stripped = input_line.strip()
        
        if not stripped:
            return Command(
                type=CommandType.EMPTY,
                raw=input_line,
                args=[],
                kwargs={}
            )
        
        parts = stripped.split()
        command_word = parts[0].lower()
        args = parts[1:]
        
        # Check for set commands (set host <value>, set port <value>, etc.)
        if command_word == 'set' and len(args) >= 1:
            return self._parse_set_command(args, input_line)
        
        # Look up command type
        command_type = self.COMMAND_ALIASES.get(command_word, CommandType.UNKNOWN)
        
        # Parse command-specific arguments
        kwargs = self._parse_args(command_type, args)
        
        # Validate command
        error = self._validate_command(command_type, args, kwargs)
        
        return Command(
            type=command_type,
            raw=input_line,
            args=args,
            kwargs=kwargs,
            error_message=error
        )
    
    @staticmethod
    def _parse_set_command(args: List[str], raw: str) -> Command:
        """Parse 'set' subcommands."""
        if len(args) < 1:
            return Command(
                type=CommandType.UNKNOWN,
                raw=raw,
                args=args,
                kwargs={},
                error_message="Usage: set <host|port|username|ui> <value>"
            )
        
        subcommand = args[0].lower()
        value_args = args[1:]
        
        type_mapping = {
            'host': CommandType.SET_HOST,
            'port': CommandType.SET_PORT,
            'username': CommandType.SET_USERNAME,
            'user': CommandType.SET_USERNAME,
            'ui': CommandType.SET_UI,
        }
        
        command_type = type_mapping.get(subcommand, CommandType.UNKNOWN)
        
        if command_type == CommandType.UNKNOWN:
            return Command(
                type=CommandType.UNKNOWN,
                raw=raw,
                args=args,
                kwargs={'subcommand': subcommand},
                error_message=f"Unknown setting: {subcommand}"
            )
        
        # Validate value exists
        if not value_args:
            setting_name = subcommand
            return Command(
                type=command_type,
                raw=raw,
                args=args,
                kwargs={'value': None},
                error_message=f"Usage: set {setting_name} <value>"
            )
        
        value = ' '.join(value_args)
        
        # Validate port is numeric
        if command_type == CommandType.SET_PORT:
            if not value.isdigit():
                return Command(
                    type=command_type,
                    raw=raw,
                    args=args,
                    kwargs={'value': value},
                    error_message="Port must be a number"
                )
            value = int(value)
        
        return Command(
            type=command_type,
            raw=raw,
            args=args,
            kwargs={'value': value}
        )
    
    @staticmethod
    def _parse_args(command_type: CommandType, args: List[str]) -> dict:
        """Parse command arguments based on command type."""
        kwargs = {}
        
        match command_type:
            case CommandType.SEND:
                if args:
                    kwargs['message'] = ' '.join(args)
            
            case CommandType.JOIN:
                if args:
                    kwargs['channel'] = args[0]
            
            case CommandType.SET_HOST | CommandType.SET_PORT | CommandType.SET_USERNAME | CommandType.SET_UI:
                if args:
                    kwargs['value'] = ' '.join(args)
        
        return kwargs
    
    @staticmethod
    def _validate_command(command_type: CommandType, args: List[str], kwargs: dict) -> Optional[str]:
        """Validate command arguments and return error message if invalid."""
        match command_type:
            case CommandType.UNKNOWN:
                return f"Unknown command. Type 'help' for available commands."
            
            case CommandType.SEND:
                if 'message' not in kwargs:
                    return "Usage: send <message>"
            
            case CommandType.JOIN:
                if 'channel' not in kwargs:
                    return "Usage: join <channel>"
        
        return None
    
    def execute(self, command: Command) -> Any:
        """
        Execute a command by calling its registered handler.
        
        Args:
            command: Command to execute
            
        Returns:
            Result from handler or None if no handler registered
        """
        handler = self._command_handlers.get(command.type)
        if handler:
            return handler(command)
        return None
    
    @staticmethod
    def get_help_text() -> str:
        """Get formatted help text."""
        return """
Available Commands:
==================

Connection:
  connect, conn          Connect to the server
  disconnect, dc         Disconnect from the server
  reconnect              Reconnect to the server

Configuration:
  set host <hostname>    Set server address
  set port <port>        Set server port
  set username <name>    Set username
  set ui <tui|gui|text>  Set UI type

Chat:
  send <message>         Send a message
  join <channel>         Join a channel
  leave                  Leave current channel

Information:
  help, ?                Show this help
  status, info           Show connection status

Control:
  exit, quit, q          Exit the client

==================
"""


class CommandExecutor:
    """
    High-level command executor that combines parsing and execution.
    Maintains client state and handles command execution.
    """

    def __init__(self):
        """Initialize the command executor."""
        self.parser = CommandParser()
        self.host = DEFAULT_HOST
        self.port = DEFAULT_API_PORT
        self.username = ""
        self.ui_type = "tui"
        self.connected = False

        # Register default handlers
        self._register_default_handlers()
    
    def _register_default_handlers(self) -> None:
        """Register default command handlers."""
        self.parser.register_handler(CommandType.HELP, self._handle_help)
        self.parser.register_handler(CommandType.STATUS, self._handle_status)
        self.parser.register_handler(CommandType.SET_HOST, self._handle_set_host)
        self.parser.register_handler(CommandType.SET_PORT, self._handle_set_port)
        self.parser.register_handler(CommandType.SET_USERNAME, self._handle_set_username)
        self.parser.register_handler(CommandType.SET_UI, self._handle_set_ui)
    
    @staticmethod
    def _handle_help(cmd: Command) -> str:
        """Handle help command."""
        return CommandParser.get_help_text()
    
    def _handle_status(self, cmd: Command) -> str:
        """Handle status command."""
        status = f"""Connection Status:
  Host: {self.host}
  Port: {self.port}
  Username: {self.username or '(not set)'}
  UI Type: {self.ui_type}
  Connected: {'Yes' if self.connected else 'No'}
"""
        return status
    
    def _handle_set_host(self, cmd: Command) -> str:
        """Handle set host command."""
        value = cmd.kwargs.get('value')
        if value:
            self.host = value
            return f"Host set to: {value}"
        return "Error: No host specified"
    
    def _handle_set_port(self, cmd: Command) -> str:
        """Handle set port command."""
        value = cmd.kwargs.get('value')
        if value:
            self.port = int(value)
            return f"Port set to: {value}"
        return "Error: No port specified"
    
    def _handle_set_username(self, cmd: Command) -> str:
        """Handle set username command."""
        value = cmd.kwargs.get('value')
        if value:
            self.username = value
            return f"Username set to: {value}"
        return "Error: No username specified"
    
    def _handle_set_ui(self, cmd: Command) -> str:
        """Handle set ui command."""
        value = cmd.kwargs.get('value')
        if value and value.lower() in ('tui', 'gui', 'text'):
            self.ui_type = value.lower()
            return f"UI set to: {value}"
        return "Error: UI must be 'tui', 'gui', or 'text'"
    
    def process(self, input_line: str) -> tuple[Command, Any]:
        """
        Parse and execute a command.
        
        Args:
            input_line: Raw input from user
            
        Returns:
            Tuple of (Command, result)
        """
        command = self.parser.parse(input_line)
        
        if command.has_error:
            return command, command.error_message
        
        result = self.parser.execute(command)
        return command, result
