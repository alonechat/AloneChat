"""
Database service for AloneChat server.

Provides ClickHouse-based data persistence with optimized batch operations.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_client = None
_store = None


def get_client():
    global _client
    if _client is not None:
        return _client
    
    try:
        from clickhouse_driver import Client
        from AloneChat.config import config
        
        _client = Client(
            host=config.CLICKHOUSE_HOST,
            port=config.CLICKHOUSE_PORT,
            user=config.CLICKHOUSE_USER,
            password=config.CLICKHOUSE_PASSWORD,
            database=config.CLICKHOUSE_DATABASE,
        )
        
        _ensure_tables(_client)
        logger.info("ClickHouse connected: %s:%s/%s", 
                   config.CLICKHOUSE_HOST, config.CLICKHOUSE_PORT, config.CLICKHOUSE_DATABASE)
        return _client
        
    except ImportError:
        logger.warning("clickhouse-driver not installed")
        return None
    except Exception as e:
        logger.error("ClickHouse connection failed: %s", e)
        return None


def _ensure_tables(client):
    from AloneChat.config import config
    
    try:
        client.execute(f"CREATE DATABASE IF NOT EXISTS {config.CLICKHOUSE_DATABASE}")
    except Exception:
        pass
    
    client.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id String,
            password_hash String,
            display_name String DEFAULT '',
            status Enum8('online' = 1, 'away' = 2, 'busy' = 3, 'offline' = 4) DEFAULT 'offline',
            is_online UInt8 DEFAULT 0,
            last_seen DateTime DEFAULT now(),
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY user_id
    """)
    
    client.execute("""
        CREATE TABLE IF NOT EXISTS user_activity (
            user_id String,
            activity_type String,
            activity_data String DEFAULT '',
            timestamp DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        ORDER BY (user_id, timestamp)
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

    # Friend system
    client.execute("""
        CREATE TABLE IF NOT EXISTS friend_requests (
            request_id String,
            from_user String,
            to_user String,
            status Enum8('pending' = 1, 'accepted' = 2, 'rejected' = 3, 'cancelled' = 4) DEFAULT 'pending',
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (to_user, from_user, request_id)
    """)

    client.execute("""
        CREATE TABLE IF NOT EXISTS friends (
            user_id String,
            friend_user_id String,
            created_at DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        ORDER BY (user_id, friend_user_id)
    """)


@dataclass
class UserData:
    user_id: str
    password_hash: str
    display_name: str = ""
    status: str = "offline"
    is_online: bool = False
    last_seen: Optional[datetime] = None
    created_at: Optional[datetime] = None


class Database:
    """High-performance database service."""
    
    def __init__(self, client=None):
        self._client = client or get_client()
        self._enabled = self._client is not None
    
    @property
    def is_enabled(self) -> bool:
        return self._enabled
    
    def create_user(self, user_id: str, password_hash: str, display_name: str = "") -> bool:
        if not self._enabled:
            return False
        
        try:
            now = datetime.now()
            self._client.execute(
                "INSERT INTO users (user_id, password_hash, display_name, status, is_online, created_at, updated_at) VALUES",
                [{'user_id': user_id, 'password_hash': password_hash, 
                  'display_name': display_name or user_id, 'status': 'offline',
                  'is_online': 0, 'created_at': now, 'updated_at': now}]
            )
            return True
        except Exception as e:
            logger.error("create_user failed: %s", e)
            return False
    
    def get_user(self, user_id: str) -> Optional[UserData]:
        if not self._enabled:
            return None
        
        try:
            result = self._client.execute(
                "SELECT "
                "  user_id, "
                "  argMax(password_hash, updated_at) as password_hash, "
                "  argMax(display_name, updated_at) as display_name, "
                "  argMax(status, updated_at) as status, "
                "  argMax(is_online, updated_at) as is_online, "
                "  argMax(last_seen, updated_at) as last_seen, "
                "  argMax(created_at, updated_at) as created_at "
                "FROM users "
                "WHERE user_id = %(uid)s "
                "GROUP BY user_id",
                {'uid': user_id}
            )
            if result:
                row = result[0]
                return UserData(
                    user_id=row[0], password_hash=row[1], display_name=row[2],
                    status=row[3], is_online=bool(row[4]), 
                    last_seen=row[5], created_at=row[6]
                )
            return None
        except Exception as e:
            logger.error("get_user failed: %s", e)
            return None
    
    def user_exists(self, user_id: str) -> bool:
        if not self._enabled:
            return False
        
        try:
            result = self._client.execute(
                "SELECT count() FROM users WHERE user_id = %(uid)s LIMIT 1",
                {'uid': user_id}
            )
            return result[0][0] > 0
        except Exception as e:
            logger.error("user_exists failed: %s", e)
            return False
    
    def update_status(self, user_id: str, status: str, is_online: bool) -> bool:
        if not self._enabled:
            return False
        
        try:
            now = datetime.now()
            self._client.execute(
                "INSERT INTO users (user_id, password_hash, display_name, status, is_online, last_seen, updated_at) "
                "SELECT "
                "  user_id, "
                "  argMax(password_hash, updated_at), "
                "  argMax(display_name, updated_at), "
                "  %(status)s, "
                "  %(online)s, "
                "  %(now)s, "
                "  %(now)s "
                "FROM users "
                "WHERE user_id = %(uid)s "
                "GROUP BY user_id",
                {'status': status, 'online': 1 if is_online else 0, 'now': now, 'uid': user_id}
            )
            return True
        except Exception as e:
            logger.error("update_status failed: %s", e)
            return False
    
    def batch_update_status(self, updates: List[Dict[str, Any]]) -> int:
        if not self._enabled or not updates:
            return 0
        
        try:
            now = datetime.now()
            user_ids = [u['user_id'] for u in updates]
            placeholders = ', '.join([f"'{uid}'" for uid in user_ids])
            
            result = self._client.execute(
                f"SELECT user_id, "
                f"  argMax(password_hash, updated_at) as password_hash, "
                f"  argMax(display_name, updated_at) as display_name "
                f"FROM users "
                f"WHERE user_id IN ({placeholders}) "
                f"GROUP BY user_id"
            )
            
            user_data_map = {r[0]: {'password_hash': r[1], 'display_name': r[2]} for r in result}
            
            batch_data = []
            for update in updates:
                user_id = update['user_id']
                data = user_data_map.get(user_id, {})
                batch_data.append({
                    'user_id': user_id,
                    'password_hash': data.get('password_hash', ''),
                    'display_name': data.get('display_name', user_id),
                    'status': update['status'],
                    'is_online': 1 if update['is_online'] else 0,
                    'last_seen': now,
                    'updated_at': now
                })
            
            if batch_data:
                self._client.execute(
                    "INSERT INTO users (user_id, password_hash, display_name, status, is_online, last_seen, updated_at) VALUES",
                    batch_data
                )
                return len(batch_data)
            return 0
        except Exception as e:
            logger.error("batch_update_status failed: %s", e)
            return 0
    
    def get_all_users(self) -> List[UserData]:
        if not self._enabled:
            return []
        
        try:
            result = self._client.execute(
                "SELECT "
                "  user_id, "
                "  argMax(password_hash, updated_at) as password_hash, "
                "  argMax(display_name, updated_at) as display_name, "
                "  argMax(status, updated_at) as status, "
                "  argMax(is_online, updated_at) as is_online, "
                "  argMax(last_seen, updated_at) as last_seen, "
                "  argMax(created_at, updated_at) as created_at "
                "FROM users "
                "GROUP BY user_id"
            )
            return [
                UserData(user_id=r[0], password_hash=r[1], display_name=r[2],
                        status=r[3], is_online=bool(r[4]), last_seen=r[5], created_at=r[6])
                for r in result
            ]
        except Exception as e:
            logger.error("get_all_users failed: %s", e)
            return []
    
    def get_online_users(self) -> List[str]:
        if not self._enabled:
            return []
        
        try:
            result = self._client.execute(
                "SELECT user_id "
                "FROM users "
                "GROUP BY user_id "
                "HAVING argMax(is_online, updated_at) = 1"
            )
            return [r[0] for r in result]
        except Exception as e:
            logger.error("get_online_users failed: %s", e)
            return []
    
    def set_all_offline(self) -> int:
        """Set ALL users to offline status in a single query."""
        if not self._enabled:
            return 0
        
        try:
            now = datetime.now()
            result = self._client.execute(
                "INSERT INTO users (user_id, password_hash, display_name, status, is_online, last_seen, updated_at) "
                "SELECT "
                "  user_id, "
                "  argMax(password_hash, updated_at), "
                "  argMax(display_name, updated_at), "
                "  'offline', "
                "  0, "
                "  %(now)s, "
                "  %(now)s "
                "FROM users "
                "GROUP BY user_id",
                {'now': now}
            )
            count_result = self._client.execute(
                "SELECT count(DISTINCT user_id) FROM users"
            )
            count = count_result[0][0] if count_result else 0
            logger.info("Set all %d users to offline status", count)
            return count
        except Exception as e:
            logger.error("set_all_offline failed: %s", e)
            return 0
    
    def save_private_message(self, msg_id: str, sender: str, recipient: str, content: str, delivered: bool = False) -> bool:
        if not self._enabled:
            return False
        
        try:
            self._client.execute(
                "INSERT INTO private_messages (id, sender, recipient, content, timestamp, delivered) VALUES",
                [{'id': msg_id, 'sender': sender, 'recipient': recipient,
                  'content': content, 'timestamp': datetime.now(), 'delivered': 1 if delivered else 0}]
            )
            return True
        except Exception as e:
            logger.error("save_private_message failed: %s", e)
            return False
    
    def get_private_messages(self, user1: str, user2: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        
        try:
            result = self._client.execute(
                "SELECT sender, content, timestamp FROM private_messages "
                "WHERE (sender = %(u1)s AND recipient = %(u2)s) OR (sender = %(u2)s AND recipient = %(u1)s) "
                "ORDER BY timestamp DESC LIMIT %(limit)s",
                {'u1': user1, 'u2': user2, 'limit': limit}
            )
            return [{'sender': r[0], 'content': r[1], 'timestamp': r[2]} for r in reversed(result)]
        except Exception as e:
            logger.error("get_private_messages failed: %s", e)
            return []

    # -----------------
    # Friend system API
    # -----------------
    def are_friends(self, user_id: str, other_user_id: str) -> bool:
        if not self._enabled:
            return False
        try:
            r = self._client.execute(
                "SELECT count() FROM friends WHERE user_id = %(u)s AND friend_user_id = %(f)s LIMIT 1",
                {'u': user_id, 'f': other_user_id}
            )
            return bool(r and r[0][0] > 0)
        except Exception as e:
            logger.error("are_friends failed: %s", e)
            return False

    def list_friends(self, user_id: str) -> List[str]:
        if not self._enabled:
            return []
        try:
            r = self._client.execute(
                "SELECT friend_user_id FROM friends WHERE user_id = %(u)s ORDER BY friend_user_id",
                {'u': user_id}
            )
            return [x[0] for x in r]
        except Exception as e:
            logger.error("list_friends failed: %s", e)
            return []

    def create_friend_request(self, from_user: str, to_user: str, request_id: str) -> bool:
        if not self._enabled:
            return False
        try:
            now = datetime.now()
            self._client.execute(
                "INSERT INTO friend_requests (request_id, from_user, to_user, status, created_at, updated_at) VALUES",
                [{'request_id': request_id, 'from_user': from_user, 'to_user': to_user,
                  'status': 'pending', 'created_at': now, 'updated_at': now}]
            )
            return True
        except Exception as e:
            logger.error("create_friend_request failed: %s", e)
            return False

    def upsert_friend_request_status(self, request_id: str, status: str) -> bool:
        if not self._enabled:
            return False
        try:
            now = datetime.now()
            self._client.execute(
                "INSERT INTO friend_requests (request_id, from_user, to_user, status, created_at, updated_at) "
                "SELECT request_id, from_user, to_user, %(status)s, created_at, %(now)s "
                "FROM friend_requests WHERE request_id = %(rid)s LIMIT 1",
                {'rid': request_id, 'status': status, 'now': now}
            )
            return True
        except Exception as e:
            logger.error("upsert_friend_request_status failed: %s", e)
            return False

    def get_latest_friend_request(self, from_user: str, to_user: str) -> Optional[Dict[str, Any]]:
        if not self._enabled:
            return None
        try:
            r = self._client.execute(
                "SELECT request_id, "
                "  argMax(status, updated_at) as status, "
                "  argMax(created_at, updated_at) as created_at, "
                "  max(updated_at) as updated_at "
                "FROM friend_requests "
                "WHERE from_user = %(f)s AND to_user = %(t)s "
                "GROUP BY request_id "
                "ORDER BY updated_at DESC LIMIT 1",
                {'f': from_user, 't': to_user}
            )
            if not r:
                return None
            row = r[0]
            return {'request_id': row[0], 'status': row[1], 'created_at': row[2], 'updated_at': row[3]}
        except Exception as e:
            logger.error("get_latest_friend_request failed: %s", e)
            return None

    def list_friend_requests(self, user_id: str, direction: str = 'incoming', limit: int = 100) -> List[Dict[str, Any]]:
        """direction: incoming (to_user=user) or outgoing (from_user=user)."""
        if not self._enabled:
            return []
        try:
            if direction == 'outgoing':
                where = "from_user = %(u)s"
            else:
                where = "to_user = %(u)s"

            r = self._client.execute(
                "SELECT request_id, "
                "  argMax(from_user, updated_at) as from_user, "
                "  argMax(to_user, updated_at) as to_user, "
                "  argMax(status, updated_at) as status, "
                "  argMax(created_at, updated_at) as created_at, "
                "  max(updated_at) as updated_at "
                "FROM friend_requests "
                f"WHERE {where} "
                "GROUP BY request_id "
                "ORDER BY updated_at DESC LIMIT %(limit)s",
                {'u': user_id, 'limit': limit}
            )
            out = []
            for row in r:
                out.append({
                    'request_id': row[0],
                    'from_user': row[1],
                    'to_user': row[2],
                    'status': row[3],
                    'created_at': row[4],
                    'updated_at': row[5],
                })
            return out
        except Exception as e:
            logger.error("list_friend_requests failed: %s", e)
            return []

    def add_friend_pair(self, user_a: str, user_b: str) -> bool:
        if not self._enabled:
            return False
        try:
            now = datetime.now()
            # Insert two directions; ignore duplicates by checking first
            pairs = [(user_a, user_b), (user_b, user_a)]
            rows = []
            for u, f in pairs:
                if not self.are_friends(u, f):
                    rows.append({'user_id': u, 'friend_user_id': f, 'created_at': now})
            if rows:
                self._client.execute(
                    "INSERT INTO friends (user_id, friend_user_id, created_at) VALUES",
                    rows
                )
            return True
        except Exception as e:
            logger.error("add_friend_pair failed: %s", e)
            return False


def get_database() -> Database:
    global _store
    if _store is None:
        _store = Database()
    return _store
