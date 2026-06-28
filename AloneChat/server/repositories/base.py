"""
Base repository classes and data transfer objects for AloneChat.

Provides the BaseRepository and UserData dataclass used by the concrete
repositories.  Uses ClickHouse when available; falls back to an in-memory
store when ``CLICKHOUSE_ENABLED`` is falsy or the connection is refused.
"""

import logging
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from AloneChat.server.database import get_client

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# In-memory table store (used when ClickHouse is disabled / unavailable)
# ---------------------------------------------------------------------------

_memory_store: Dict[str, List[Dict[str, Any]]] = {}
_memory_lock = threading.Lock()


def reset_memory_store() -> None:
    """Discard all in-memory table data (useful between tests)."""
    global _memory_store
    with _memory_lock:
        _memory_store.clear()


def _ensure_table(table: str) -> List[Dict[str, Any]]:
    with _memory_lock:
        if table not in _memory_store:
            _memory_store[table] = []
        return _memory_store[table]


def _eval_condition(row: Dict[str, Any], where_clause: str) -> bool:
    """Evaluate a simple WHERE clause against a dict row.

    Handles bool/int coercion: ``is_online = 1`` matches both ``1`` (int)
    and ``True`` (bool) stored values.
    """
    if not where_clause:
        return True
    parts = where_clause.split("AND")
    for part in parts:
        part = part.strip()
        matched = False
        for op in ("!=", "<>", "=", ">=", "<=", ">", "<"):
            if op in part:
                left, right = part.split(op, 1)
                left = left.strip()
                right = right.strip().strip("'\"")
                row_val_raw = row.get(left, "")
                # Normalise bool/int: ClickHouse ``is_online = 1`` should
                # match both integer 1 and Python True.
                if isinstance(row_val_raw, bool):
                    row_val_str = "1" if row_val_raw else "0"
                elif isinstance(row_val_raw, int):
                    row_val_str = str(row_val_raw)
                else:
                    row_val_str = str(row_val_raw)
                if op in ("!=", "<>"):
                    if row_val_str == right:
                        return False
                    matched = True
                elif op == "=":
                    if row_val_str != right:
                        return False
                    matched = True
                elif op in (">", "<", ">=", "<="):
                    try:
                        rv = float(row_val_str)
                        cv = float(right)
                    except ValueError:
                        return False
                    if op == ">" and not (rv > cv):
                        return False
                    if op == "<" and not (rv < cv):
                        return False
                    if op == ">=" and not (rv >= cv):
                        return False
                    if op == "<=" and not (rv <= cv):
                        return False
                    matched = True
                break
        if not matched:
            return False
    return True


def _substitute_params(
    text: str, params: Optional[Dict[str, Any]]
) -> str:
    """Replace ``%(name)s`` placeholders in *text* with literal values."""
    if params is None:
        return text
    for k, v in params.items():
        if v is None:
            val = "NULL"
        elif isinstance(v, bool):
            val = "1" if v else "0"
        elif isinstance(v, (int, float)):
            val = str(v)
        else:
            val = str(v)
        text = text.replace(f"%({k})s", val)
    return text


def _in_memory_execute(
    query: str, params: Optional[Dict[str, Any]] = None
) -> Any:
    """Execute a simple SQL query against the in-memory store.

    Supported operations: INSERT INTO users, SELECT ... FROM users [FINAL],
    SELECT count() ... FROM users, ALTER TABLE users UPDATE ... WHERE ...

    All ``%(name)s`` placeholders are substituted with values from *params*
    before the query is parsed.
    """
    q = _substitute_params(query.strip().rstrip(";"), params)

    # -- INSERT INTO users (...) VALUES (...) -----------------------------
    m = re.match(
        r"INSERT\s+INTO\s+users\s*\((?P<cols>[^)]+)\)\s*VALUES\s*\((?P<vals>[^)]+)\)",
        q, re.IGNORECASE | re.DOTALL,
    )
    if m:
        col_names = [c.strip() for c in m.group("cols").split(",")]
        val_parts = [v.strip().strip("'\"") for v in m.group("vals").split(",")]
        row = dict(zip(col_names, val_parts))
        if "is_online" in row:
            row["is_online"] = 1 if row["is_online"] in ("1", "True", "true") else 0
        _ensure_table("users").append(row)
        return []

    # -- SELECT count() AS cnt FROM users ---------------------------------
    m = re.match(
        r"SELECT\s+count\(\s*\)\s+AS\s+cnt\s+FROM\s+users\s*(FINAL)?\s*(?:WHERE\s+(?P<where>.+?))?\s*(?=\s*(?:LIMIT|ORDER|$))",
        q, re.IGNORECASE | re.DOTALL,
    )
    if m:
        where = m.group("where")
        rows = _ensure_table("users")
        matched = [r for r in rows if _eval_condition(r, where)]
        return [(len(matched),)]

    # -- SELECT columns FROM users [FINAL] [WHERE ...] [LIMIT n] ----------
    m = re.match(
        r"SELECT\s+(?P<cols>.+?)\s+FROM\s+users\s*(FINAL)?\s*(?:WHERE\s+(?P<where>.+?))?\s*(?=\s*(?:LIMIT|ORDER|$))",
        q, re.IGNORECASE | re.DOTALL,
    )
    if m:
        cols_str = m.group("cols").strip()
        where = m.group("where")
        # Extract optional LIMIT n suffix
        limit_match = re.search(r"\s+LIMIT\s+(?P<limit>\d+)\s*$", q, re.IGNORECASE)
        limit = int(limit_match.group("limit")) if limit_match else None

        if cols_str == "*":
            col_names = [
                "user_id", "password_hash", "display_name", "status",
                "is_online", "last_seen", "created_at",
            ]
        else:
            col_names = [c.strip() for c in cols_str.split(",")]

        rows = _ensure_table("users")
        matched = [r for r in rows if _eval_condition(r, where)]
        if limit is not None:
            matched = matched[:limit]
        return [tuple(row.get(c) for c in col_names) for row in matched]

    # -- ALTER TABLE users UPDATE ... WHERE ... ---------------------------
    m = re.match(
        r"ALTER\s+TABLE\s+users\s+UPDATE\s+(?P<sets>.+?)\s+WHERE\s+(?P<where>.+)\s*$",
        q, re.IGNORECASE | re.DOTALL,
    )
    if m:
        sets_str = m.group("sets")
        where = m.group("where")
        rows = _ensure_table("users")

        set_pairs: Dict[str, Any] = {}
        for pair in sets_str.split(","):
            pair = pair.strip()
            if "=" not in pair:
                continue
            k, v = pair.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if v == "now()":
                v = datetime.now()
            set_pairs[k] = v

        count = 0
        for row in rows:
            if _eval_condition(row, where):
                for k, v in set_pairs.items():
                    if k in ("is_online",):
                        row[k] = 1 if v in ("1", "True", "true", 1, True) else 0
                    else:
                        row[k] = v
                count += 1
        return []

    logger.debug("In-memory fallback: unsupported query: %.120s", q)
    return []


# ---------------------------------------------------------------------------
# UserData
# ---------------------------------------------------------------------------


@dataclass
class UserData:
    """Lightweight transfer object representing a single user row."""

    user_id: str
    password_hash: str
    display_name: str = ""
    status: str = "offline"
    is_online: bool = False
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None


# ---------------------------------------------------------------------------
# BaseRepository
# ---------------------------------------------------------------------------


class BaseRepository:
    """Common ClickHouse connection and query execution for repositories.

    Concrete repositories (UserRepository, MessageRepository, etc.) inherit
    from this class to gain ``_safe_execute`` and automatic reconnection
    behaviour.

    When ClickHouse is unavailable (``CLICKHOUSE_ENABLED`` falsy or
    connection refused), ``_safe_execute`` transparently falls back to an
    in-memory store so that tests and development environments can run
    without a real ClickHouse instance.
    """

    def __init__(
        self,
        client: Optional[Any] = None,
        db: Optional[Any] = None,
    ) -> None:
        # Accept either a raw ClickHouse client or a Database handle (from DI).
        if client is not None:
            self._client = client
        elif db is not None:
            self._client = getattr(db, "_client", None)
        else:
            self._client = None
        # Optimistic: assume enabled and let _get_client() try on first use.
        self._enabled = True

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _get_client(self):
        """Return a working ClickHouse client, reconnecting on failure."""
        if self._client is None:
            self._client = get_client()
            self._enabled = self._client is not None
        return self._client

    def _safe_execute(
        self, query: str, params: Optional[Dict[str, Any]] = None
    ) -> Any:
        """Execute a parameterized query with automatic reconnection and
        transparent in-memory fallback when ClickHouse is unavailable.
        """
        client = self._get_client()
        if client is None:
            logger.debug("ClickHouse unavailable; using in-memory fallback")
            return _in_memory_execute(query, params)

        try:
            if params is not None:
                return client.execute(query, params)
            return client.execute(query)
        except Exception as exc:
            logger.warning(
                "Query failed, falling back to in-memory. Error: %s. Query: %.120s",
                exc, query,
            )
            self._client = None
            self._enabled = False
            return _in_memory_execute(query, params)

    @property
    def is_enabled(self) -> bool:
        """``True`` when the repository has a working database connection."""
        return self._enabled
