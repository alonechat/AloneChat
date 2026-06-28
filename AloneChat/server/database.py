"""
Database connection management for AloneChat server.

Thread-safe ClickHouse connection factory with automatic reconnect, plus
synchronous and asynchronous query execution helpers.  No repository or
business-logic methods — purely connection management.
"""

import asyncio
import logging
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, Optional

from AloneChat.config import config

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Module-level globals
# ---------------------------------------------------------------------------

_client: Optional[Any] = None
_client_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="db_")

_IDENTIFIER_RE = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_]*$")


# ---------------------------------------------------------------------------
# Table migration
# ---------------------------------------------------------------------------


def _ensure_tables(client) -> None:
    """Create application tables if they don't already exist.

    Uses ClickHouse ReplacingMergeTree for mutable entities and MergeTree
    for append-only data.
    """
    client.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id String,
            password_hash String,
            display_name String DEFAULT '',
            status String DEFAULT 'offline',
            is_online UInt8 DEFAULT 0,
            last_seen DateTime DEFAULT now(),
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY user_id
    """)

    client.execute("""
        CREATE TABLE IF NOT EXISTS private_messages (
            id String,
            sender String,
            recipient String,
            content String,
            timestamp DateTime DEFAULT now(),
            delivered UInt8 DEFAULT 0
        ) ENGINE = MergeTree()
        ORDER BY (sender, recipient, timestamp)
    """)

    client.execute("""
        CREATE TABLE IF NOT EXISTS friendships (
            user_id String,
            friend_id String,
            remark String DEFAULT '',
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (user_id, friend_id)
    """)

    client.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            id String,
            from_user String,
            to_user String,
            message String DEFAULT '',
            status String DEFAULT 'pending',
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (to_user, from_user, created_at)
    """)


# ---------------------------------------------------------------------------
# Connection factory
# ---------------------------------------------------------------------------


def get_client():
    """Return a healthy ClickHouse client, creating or reconnecting as needed.

    The returned client is connected to *config.CLICKHOUSE_DATABASE*.  If the
    database does not exist it is created automatically (tables are handled
    elsewhere, e.g. via migrations).

    Returns ``None`` when ClickHouse is disabled via ``CLICKHOUSE_ENABLED``,
    ``clickhouse-driver`` is not installed, or the connection fails.
    """
    global _client

    if not config.CLICKHOUSE_ENABLED:
        return None

    with _client_lock:
        if _client is not None:
            try:
                _client.execute("SELECT 1")
                return _client
            except Exception:
                logger.warning("ClickHouse connection lost, reconnecting")
                _client = None

        try:
            from clickhouse_driver import Client

            db_name = config.CLICKHOUSE_DATABASE
            if not _IDENTIFIER_RE.match(db_name):
                raise ValueError(f"Unsafe database name: {db_name!r}")

            # Ensure the database exists (DDL identifiers cannot be
            # parameterised in ClickHouse; validated above).
            temp = Client(
                host=config.CLICKHOUSE_HOST,
                port=config.CLICKHOUSE_PORT,
                user=config.CLICKHOUSE_USER,
                password=config.CLICKHOUSE_PASSWORD,
            )
            try:
                temp.execute(
                    f"CREATE DATABASE IF NOT EXISTS {db_name}",
                )
            finally:
                temp.disconnect()

            _client = Client(
                host=config.CLICKHOUSE_HOST,
                port=config.CLICKHOUSE_PORT,
                user=config.CLICKHOUSE_USER,
                password=config.CLICKHOUSE_PASSWORD,
                database=db_name,
            )

            # Ensure tables exist (DDL — identifiers validated above).
            _ensure_tables(_client)
            logger.info(
                "ClickHouse connected: %s:%s/%s",
                config.CLICKHOUSE_HOST,
                config.CLICKHOUSE_PORT,
                db_name,
            )
            return _client

        except ImportError:
            logger.warning("clickhouse-driver is not installed")
            return None
        except Exception:
            logger.exception("ClickHouse connection failed")
            return None


# ---------------------------------------------------------------------------
# Query execution helpers
# ---------------------------------------------------------------------------


def _safe_execute(query: str, params: Any = None) -> Any:
    """Execute a parameterised ClickHouse query with automatic reconnection.

    Use ``%(name)s`` placeholders for parameters.  Raises
    :exc:`ConnectionError` when the database is unavailable even after a
    reconnection attempt.
    """
    global _client

    client = get_client()
    if client is None:
        raise ConnectionError("ClickHouse database is not available")

    try:
        if params is not None:
            return client.execute(query, params)
        return client.execute(query)
    except Exception:
        logger.warning("Query failed, attempting reconnect: %.120s", query)
        with _client_lock:
            _client = None
        client = get_client()
        if client is None:
            raise ConnectionError("ClickHouse reconnection failed")
        if params is not None:
            return client.execute(query, params)
        return client.execute(query)


async def _async_execute(query: str, params: Optional[Dict[str, Any]] = None) -> Any:
    """Execute a ClickHouse query asynchronously via a thread-pool.

    Offloads the blocking :func:`_safe_execute` call to the shared
    ``ThreadPoolExecutor`` so the asyncio event loop is not blocked.
    """
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(_executor, _safe_execute, query, params)


# ---------------------------------------------------------------------------
# Singleton handle
# ---------------------------------------------------------------------------

_store: Optional["Database"] = None


class Database:
    """Lightweight handle for database access.

    Repositories receive or look up this handle instead of calling
    ``_safe_execute`` / ``_async_execute`` directly.
    """

    __slots__ = ("_client",)

    def __init__(self, client=None) -> None:
        self._client = client

    @property
    def is_enabled(self) -> bool:
        """``True`` when a working ClickHouse connection is available."""
        c = self._client or get_client()
        return c is not None

    def execute(self, query: str, params: Any = None) -> Any:
        """Execute a parameterised query synchronously (with reconnect)."""
        return _safe_execute(query, params)

    async def async_execute(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute a parameterised query asynchronously (with reconnect)."""
        return await _async_execute(query, params)


def get_database() -> Database:
    """Return the singleton :class:`Database` handle, lazily created."""
    global _store
    if _store is None:
        _store = Database()
    return _store
