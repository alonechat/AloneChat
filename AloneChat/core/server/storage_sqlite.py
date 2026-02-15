"""SQLite persistence layer for AloneChat.

This project started with a simple JSON-based user store. To support
"WeChat-like" features (friends, friend approval, conversations and message
history), we provide a lightweight SQLite-backed storage implementation.

Design goals:
  - Zero extra dependencies (uses stdlib sqlite3)
  - Safe for multi-request use (single process): guarded by a lock
  - Keep APIs small and explicit

The DB file location is controlled by Config.SQLITE_DB_FILE.
"""

from __future__ import annotations

import sqlite3
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


SCHEMA_SQL = """
PRAGMA journal_mode=WAL;
PRAGMA foreign_keys=ON;

CREATE TABLE IF NOT EXISTS users (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT UNIQUE NOT NULL,
  password_hash TEXT NOT NULL,
  created_at REAL NOT NULL,
  is_online INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS friend_requests (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  from_user TEXT NOT NULL,
  to_user TEXT NOT NULL,
  message TEXT DEFAULT '',
  status TEXT NOT NULL, -- pending / accepted / rejected
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE(from_user, to_user, status)
);

CREATE TABLE IF NOT EXISTS friendships (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_a TEXT NOT NULL,
  user_b TEXT NOT NULL,
  created_at REAL NOT NULL,
  UNIQUE(user_a, user_b)
);

CREATE TABLE IF NOT EXISTS conversations (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  user_a TEXT NOT NULL,
  user_b TEXT NOT NULL,
  created_at REAL NOT NULL,
  updated_at REAL NOT NULL,
  UNIQUE(user_a, user_b)
);

-- Per-user conversation settings (pin/mute).
CREATE TABLE IF NOT EXISTS conversation_settings (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  username TEXT NOT NULL,
  conversation_id INTEGER NOT NULL,
  pinned INTEGER NOT NULL DEFAULT 0,
  muted INTEGER NOT NULL DEFAULT 0,
  updated_at REAL NOT NULL,
  UNIQUE(username, conversation_id),
  FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS messages (
  id INTEGER PRIMARY KEY AUTOINCREMENT,
  conversation_id INTEGER NOT NULL,
  sender TEXT NOT NULL,
  content TEXT NOT NULL,
  created_at REAL NOT NULL,
  FOREIGN KEY(conversation_id) REFERENCES conversations(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_messages_conv_time ON messages(conversation_id, created_at);

CREATE INDEX IF NOT EXISTS idx_conv_settings_user ON conversation_settings(username, pinned, muted);
"""


def _pair(a: str, b: str) -> Tuple[str, str]:
    """Canonical ordered pair for symmetric relationships."""
    return (a, b) if a <= b else (b, a)


@dataclass(frozen=True)
class FriendRequestRow:
    id: int
    from_user: str
    to_user: str
    message: str
    status: str
    created_at: float
    updated_at: float


class SQLiteStore:
    """A tiny SQLite-backed store."""

    def __init__(self, db_path: str):
        self.db_path = str(Path(db_path))
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        with self._lock:
            self._conn.executescript(SCHEMA_SQL)
            self._conn.commit()

    # ------------------- conversation settings -------------------
    def _get_conversation_id_locked(self, user1: str, user2: str) -> Optional[int]:
        a, b = _pair(user1, user2)
        cur = self._conn.execute(
            "SELECT id FROM conversations WHERE user_a=? AND user_b=?",
            (a, b),
        )
        row = cur.fetchone()
        return None if row is None else int(row["id"])

    def _ensure_settings_locked(self, username: str, conversation_id: int) -> None:
        now = time.time()
        self._conn.execute(
            """
            INSERT OR IGNORE INTO conversation_settings(username, conversation_id, pinned, muted, updated_at)
            VALUES(?,?,0,0,?)
            """,
            (username, int(conversation_id), now),
        )

    def set_conversation_pinned(self, username: str, other: str, pinned: bool) -> Tuple[bool, str]:
        if other.lower() == "global":
            return False, "Cannot pin global"
        if not self.are_friends(username, other):
            return False, "Not friends"
        now = time.time()
        with self._lock:
            cid = self._get_conversation_id_locked(username, other)
            if cid is None:
                cid = self._ensure_conversation_locked(username, other)
            self._ensure_settings_locked(username, cid)
            self._conn.execute(
                "UPDATE conversation_settings SET pinned=?, updated_at=? WHERE username=? AND conversation_id=?",
                (1 if pinned else 0, now, username, int(cid)),
            )
            self._conn.commit()
        return True, "Pinned" if pinned else "Unpinned"

    def set_conversation_muted(self, username: str, other: str, muted: bool) -> Tuple[bool, str]:
        if other.lower() == "global":
            return False, "Cannot mute global"
        if not self.are_friends(username, other):
            return False, "Not friends"
        now = time.time()
        with self._lock:
            cid = self._get_conversation_id_locked(username, other)
            if cid is None:
                cid = self._ensure_conversation_locked(username, other)
            self._ensure_settings_locked(username, cid)
            self._conn.execute(
                "UPDATE conversation_settings SET muted=?, updated_at=? WHERE username=? AND conversation_id=?",
                (1 if muted else 0, now, username, int(cid)),
            )
            self._conn.commit()
        return True, "Muted" if muted else "Unmuted"

    # --------------------------- users ---------------------------
    def user_exists(self, username: str) -> bool:
        with self._lock:
            cur = self._conn.execute("SELECT 1 FROM users WHERE username=?", (username,))
            return cur.fetchone() is not None

    def create_user(self, username: str, password_hash: str) -> bool:
        now = time.time()
        with self._lock:
            try:
                self._conn.execute(
                    "INSERT INTO users(username, password_hash, created_at, is_online) VALUES(?,?,?,0)",
                    (username, password_hash, now),
                )
                self._conn.commit()
                return True
            except sqlite3.IntegrityError:
                return False

    def get_password_hash(self, username: str) -> Optional[str]:
        with self._lock:
            cur = self._conn.execute("SELECT password_hash FROM users WHERE username=?", (username,))
            row = cur.fetchone()
            return None if row is None else str(row["password_hash"])

    def set_user_online(self, username: str, is_online: bool) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE users SET is_online=? WHERE username=?",
                (1 if is_online else 0, username),
            )
            self._conn.commit()

    def list_users(self, q: str = "", limit: int = 50) -> List[Dict[str, Any]]:
        q = (q or "").strip()
        like = f"%{q}%" if q else "%"
        with self._lock:
            cur = self._conn.execute(
                "SELECT username, is_online, created_at FROM users WHERE username LIKE ? ORDER BY username LIMIT ?",
                (like, int(limit)),
            )
            return [
                {
                    "username": r["username"],
                    "is_online": bool(r["is_online"]),
                    "created_at": float(r["created_at"]),
                }
                for r in cur.fetchall()
            ]

    # --------------------- friendships / requests ---------------------
    def are_friends(self, user1: str, user2: str) -> bool:
        a, b = _pair(user1, user2)
        with self._lock:
            cur = self._conn.execute(
                "SELECT 1 FROM friendships WHERE user_a=? AND user_b=?",
                (a, b),
            )
            return cur.fetchone() is not None

    def list_friends(self, username: str) -> List[str]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT CASE WHEN user_a=? THEN user_b ELSE user_a END AS friend
                FROM friendships
                WHERE user_a=? OR user_b=?
                ORDER BY friend
                """,
                (username, username, username),
            )
            return [str(r["friend"]) for r in cur.fetchall()]

    def create_friend_request(self, from_user: str, to_user: str, message: str = "") -> Tuple[bool, str]:
        if from_user == to_user:
            return False, "Cannot add yourself"
        if not self.user_exists(to_user):
            return False, "Target user does not exist"
        if self.are_friends(from_user, to_user):
            return False, "Already friends"

        now = time.time()
        with self._lock:
            # If there is an opposite pending request, accept it automatically.
            cur = self._conn.execute(
                """
                SELECT id FROM friend_requests
                WHERE from_user=? AND to_user=? AND status='pending'
                """,
                (to_user, from_user),
            )
            row = cur.fetchone()
            if row is not None:
                req_id = int(row["id"])
                self._accept_request_locked(req_id)
                self._conn.commit()
                return True, "Friend request matched and accepted"

            try:
                self._conn.execute(
                    """
                    INSERT INTO friend_requests(from_user, to_user, message, status, created_at, updated_at)
                    VALUES(?,?,?,'pending',?,?)
                    """,
                    (from_user, to_user, message or "", now, now),
                )
                self._conn.commit()
                return True, "Friend request sent"
            except sqlite3.IntegrityError:
                return False, "Friend request already pending"

    def _accept_request_locked(self, request_id: int) -> Tuple[bool, str]:
        now = time.time()
        cur = self._conn.execute(
            "SELECT * FROM friend_requests WHERE id=?",
            (int(request_id),),
        )
        row = cur.fetchone()
        if row is None:
            return False, "Request not found"
        if row["status"] != "pending":
            return False, f"Request already {row['status']}"
        from_user = str(row["from_user"])
        to_user = str(row["to_user"])
        a, b = _pair(from_user, to_user)

        self._conn.execute(
            "UPDATE friend_requests SET status='accepted', updated_at=? WHERE id=?",
            (now, int(request_id)),
        )
        # Create friendship
        try:
            self._conn.execute(
                "INSERT OR IGNORE INTO friendships(user_a, user_b, created_at) VALUES(?,?,?)",
                (a, b, now),
            )
        except sqlite3.IntegrityError:
            pass

        # Ensure a conversation exists for DMs
        self._ensure_conversation_locked(from_user, to_user)

        return True, "Accepted"

    def accept_friend_request(self, request_id: int, acting_user: str) -> Tuple[bool, str]:
        with self._lock:
            # Must be recipient
            cur = self._conn.execute("SELECT to_user FROM friend_requests WHERE id=?", (int(request_id),))
            row = cur.fetchone()
            if row is None:
                return False, "Request not found"
            if str(row["to_user"]) != acting_user:
                return False, "Not allowed"
            ok, msg = self._accept_request_locked(int(request_id))
            self._conn.commit()
            return ok, msg

    def reject_friend_request(self, request_id: int, acting_user: str) -> Tuple[bool, str]:
        now = time.time()
        with self._lock:
            cur = self._conn.execute("SELECT to_user, status FROM friend_requests WHERE id=?", (int(request_id),))
            row = cur.fetchone()
            if row is None:
                return False, "Request not found"
            if str(row["to_user"]) != acting_user:
                return False, "Not allowed"
            if str(row["status"]) != "pending":
                return False, f"Request already {row['status']}"
            self._conn.execute(
                "UPDATE friend_requests SET status='rejected', updated_at=? WHERE id=?",
                (now, int(request_id)),
            )
            self._conn.commit()
            return True, "Rejected"

    def list_incoming_requests(self, username: str) -> List[FriendRequestRow]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM friend_requests
                WHERE to_user=? AND status='pending'
                ORDER BY created_at DESC
                """,
                (username,),
            )
            return [FriendRequestRow(**dict(r)) for r in cur.fetchall()]

    def list_outgoing_requests(self, username: str) -> List[FriendRequestRow]:
        with self._lock:
            cur = self._conn.execute(
                """
                SELECT * FROM friend_requests
                WHERE from_user=?
                ORDER BY created_at DESC
                """,
                (username,),
            )
            return [FriendRequestRow(**dict(r)) for r in cur.fetchall()]

    def get_friend_request(self, request_id: int) -> Optional[FriendRequestRow]:
        """Get a friend request row by id."""
        with self._lock:
            cur = self._conn.execute(
                "SELECT * FROM friend_requests WHERE id=?",
                (int(request_id),),
            )
            row = cur.fetchone()
            if row is None:
                return None
            try:
                return FriendRequestRow(**dict(row))
            except Exception:
                return None

    # ------------------- conversations / messages -------------------
    def _ensure_conversation_locked(self, user1: str, user2: str) -> int:
        a, b = _pair(user1, user2)
        now = time.time()
        cur = self._conn.execute(
            "SELECT id FROM conversations WHERE user_a=? AND user_b=?",
            (a, b),
        )
        row = cur.fetchone()
        if row is not None:
            return int(row["id"])

        self._conn.execute(
            "INSERT INTO conversations(user_a, user_b, created_at, updated_at) VALUES(?,?,?,?)",
            (a, b, now, now),
        )
        return int(self._conn.execute("SELECT last_insert_rowid() AS id").fetchone()["id"])

    def ensure_conversation(self, user1: str, user2: str) -> int:
        with self._lock:
            cid = self._ensure_conversation_locked(user1, user2)
            self._conn.commit()
            return cid

    def add_message(self, sender: str, target: str, content: str) -> int:
        """Store a DM message. Requires friendship."""
        if not self.are_friends(sender, target):
            raise PermissionError("Users are not friends")
        now = time.time()
        with self._lock:
            conv_id = self._ensure_conversation_locked(sender, target)
            self._conn.execute(
                "INSERT INTO messages(conversation_id, sender, content, created_at) VALUES(?,?,?,?)",
                (conv_id, sender, content, now),
            )
            self._conn.execute(
                "UPDATE conversations SET updated_at=? WHERE id=?",
                (now, conv_id),
            )
            self._conn.commit()
            return conv_id

    def list_conversations(self, username: str, limit: int = 50) -> List[Dict[str, Any]]:
        with self._lock:
            # Also include the last message preview for better client UX.
            cur = self._conn.execute(
                """
                SELECT c.id, c.user_a, c.user_b, c.updated_at,
                       m.sender AS last_sender,
                       m.content AS last_content,
                       m.created_at AS last_created_at,
                       COALESCE(cs.pinned, 0) AS pinned,
                       COALESCE(cs.muted, 0) AS muted
                FROM conversations c
                LEFT JOIN conversation_settings cs
                  ON cs.conversation_id = c.id AND cs.username = ?
                LEFT JOIN messages m
                  ON m.id = (
                    SELECT id
                    FROM messages
                    WHERE conversation_id = c.id
                    ORDER BY created_at DESC
                    LIMIT 1
                  )
                WHERE c.user_a=? OR c.user_b=?
                ORDER BY pinned DESC, c.updated_at DESC
                LIMIT ?
                """,
                (username, username, username, int(limit)),
            )
            out: List[Dict[str, Any]] = []
            for r in cur.fetchall():
                other = r["user_b"] if r["user_a"] == username else r["user_a"]
                out.append(
                    {
                        "conversation_id": int(r["id"]),
                        "with": str(other),
                        "updated_at": float(r["updated_at"]),
                        "last_sender": (str(r["last_sender"]) if r["last_sender"] is not None else ""),
                        "last_message": (str(r["last_content"]) if r["last_content"] is not None else ""),
                        "last_created_at": (float(r["last_created_at"]) if r["last_created_at"] is not None else None),
                        "pinned": bool(r["pinned"]),
                        "muted": bool(r["muted"]),
                    }
                )
            return out

    def get_history(self, user1: str, user2: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.are_friends(user1, user2):
            return []
        a, b = _pair(user1, user2)
        with self._lock:
            cur = self._conn.execute(
                "SELECT id FROM conversations WHERE user_a=? AND user_b=?",
                (a, b),
            )
            row = cur.fetchone()
            if row is None:
                return []
            conv_id = int(row["id"])
            cur2 = self._conn.execute(
                """
                SELECT sender, content, created_at
                FROM messages
                WHERE conversation_id=?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (conv_id, int(limit)),
            )
            rows = cur2.fetchall()
            # Return chronological order
            rows.reverse()
            return [
                {
                    "sender": str(r["sender"]),
                    "content": str(r["content"]),
                    "created_at": float(r["created_at"]),
                }
                for r in rows
            ]
