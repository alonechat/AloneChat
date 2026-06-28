"""
Constants and configuration values for the curses client.
"""

# Default connection settings
DEFAULT_HOST = "localhost"
DEFAULT_PORT = 8765
DEFAULT_API_PORT = 8766  # API server typically runs on port + 1

# Reconnection settings
MAX_RECONNECT_ATTEMPTS = 5
RECONNECT_DELAY_SECONDS = 3

# UI settings
MAX_MESSAGE_HISTORY = 1000
INPUT_PROMPT = "> "
REFRESH_RATE_HZ = 100  # Input polling rate (100Hz = 10ms)

# Message display
SYSTEM_SENDER = "System"
ERROR_SENDER = "! Error"

# Timeout settings
API_TIMEOUT_SECONDS = 30
MESSAGE_RECEIVE_TIMEOUT = 5
