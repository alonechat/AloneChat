"""Client utilities — constants and exceptions."""

from AloneChat.client.utils.constants import (
    DEFAULT_HOST,
    DEFAULT_PORT,
    DEFAULT_API_PORT,
    MAX_RECONNECT_ATTEMPTS,
    RECONNECT_DELAY_SECONDS,
    MAX_MESSAGE_HISTORY,
    INPUT_PROMPT,
    REFRESH_RATE_HZ,
    SYSTEM_SENDER,
    ERROR_SENDER,
    API_TIMEOUT_SECONDS,
    MESSAGE_RECEIVE_TIMEOUT,
)
from AloneChat.client.utils.exceptions import (
    ClientError,
)

__all__ = [
    "DEFAULT_HOST",
    "DEFAULT_PORT",
    "DEFAULT_API_PORT",
    "MAX_RECONNECT_ATTEMPTS",
    "RECONNECT_DELAY_SECONDS",
    "MAX_MESSAGE_HISTORY",
    "INPUT_PROMPT",
    "REFRESH_RATE_HZ",
    "SYSTEM_SENDER",
    "ERROR_SENDER",
    "API_TIMEOUT_SECONDS",
    "MESSAGE_RECEIVE_TIMEOUT",
    "ClientError",
]
