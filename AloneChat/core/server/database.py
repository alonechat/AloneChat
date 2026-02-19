"""
Database service for AloneChat server.

Provides ClickHouse-based data persistence with optimized batch operations.
"""

import asyncio
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_client = None
_store = None
_client_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="db_")


def get_client():
    global _client
    
    with _client_lock:
        if _client is not None:
            try:
                _client.execute("SELECT 1")
                return _client
            except Exception as e:
                logger.warning("ClickHouse connection lost, reconnecting: %s", e)
                _client = None
        
        try:
            from clickhouse_driver import Client
            from AloneChat.config import config
            
            temp_client = Client(
                host=config.CLICKHOUSE_HOST,
                port=config.CLICKHOUSE_PORT,
                user=config.CLICKHOUSE_USER,
                password=config.CLICKHOUSE_PASSWORD,
            )
            
            _ensure_database_and_tables(temp_client, config.CLICKHOUSE_DATABASE)
            temp_client.disconnect()
            
            _client = Client(
                host=config.CLICKHOUSE_HOST,
                port=config.CLICKHOUSE_PORT,
                user=config.CLICKHOUSE_USER,
                password=config.CLICKHOUSE_PASSWORD,
                database=config.CLICKHOUSE_DATABASE,
            )
            
            logger.info("ClickHouse connected: %s:%s/%s", 
                       config.CLICKHOUSE_HOST, config.CLICKHOUSE_PORT, config.CLICKHOUSE_DATABASE)
            return _client
            
        except ImportError:
            logger.warning("clickhouse-driver not installed")
            return None
        except Exception as e:
            logger.error("ClickHouse connection failed: %s", e)
            return None


def _ensure_database_and_tables(client, database_name):
    client.execute(f"CREATE DATABASE IF NOT EXISTS {database_name}")
    
    client.execute(f"""
        CREATE TABLE IF NOT EXISTS {database_name}.users (
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
    
    client.execute(f"""
        CREATE TABLE IF NOT EXISTS {database_name}.user_activity (
            user_id String,
            activity_type String,
            activity_data String DEFAULT '',
            timestamp DateTime DEFAULT now()
        ) ENGINE = MergeTree()
        ORDER BY (user_id, timestamp)
    """)
    
    client.execute(f"""
        CREATE TABLE IF NOT EXISTS {database_name}.private_messages (
            id String,
            sender String,
            recipient String,
            content String,
            timestamp DateTime DEFAULT now(),
            delivered UInt8 DEFAULT 0
        ) ENGINE = MergeTree()
        ORDER BY (sender, recipient, timestamp)
    """)
    
    client.execute(f"""
        CREATE TABLE IF NOT EXISTS {database_name}.friendships (
            user_id String,
            friend_id String,
            remark String DEFAULT '',
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (user_id, friend_id)
    """)
    
    client.execute(f"""
        CREATE TABLE IF NOT EXISTS {database_name}.friend_requests (
            id String,
            from_user String,
            to_user String,
            message String DEFAULT '',
            status Enum8('pending' = 1, 'accepted' = 2, 'rejected' = 3) DEFAULT 'pending',
            created_at DateTime DEFAULT now(),
            updated_at DateTime DEFAULT now()
        ) ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (to_user, from_user, created_at)
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
    
    def _get_client(self):
        """Get a working client connection."""
        if self._client is None:
            self._client = get_client()
            self._enabled = self._client is not None
        return self._client
    
    def _safe_execute(self, query, params=None):
        """Execute query with connection retry."""
        client = self._get_client()
        if client is None:
            raise Exception("Database not available")
        
        try:
            if params:
                return client.execute(query, params)
            return client.execute(query)
        except Exception as e:
            logger.warning("Query failed, attempting reconnect: %s", e)
            self._client = None
            client = self._get_client()
            if client is None:
                raise Exception("Database reconnection failed")
            
            if params:
                return client.execute(query, params)
            return client.execute(query)
    
    async def _async_execute(self, query, params=None):
        """Execute query asynchronously using thread pool."""
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, self._safe_execute, query, params)
    
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
                "SELECT user_id, password_hash, display_name, status, is_online, last_seen, created_at "
                "FROM users FINAL "
                "WHERE user_id = %(uid)s "
                "LIMIT 1",
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
    
    async def async_get_user(self, user_id: str) -> Optional[UserData]:
        """Async version of get_user with optimized query."""
        if not self._enabled:
            return None
        
        try:
            result = await self._async_execute(
                "SELECT user_id, password_hash, display_name, status, is_online, last_seen, created_at "
                "FROM users FINAL "
                "WHERE user_id = %(uid)s "
                "LIMIT 1",
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
            logger.error("async_get_user failed: %s", e)
            return None
    
    def user_exists(self, user_id: str) -> bool:
        if not self._enabled:
            return False
        
        try:
            result = self._client.execute(
                "SELECT 1 FROM users WHERE user_id = %(uid)s LIMIT 1",
                {'uid': user_id}
            )
            return len(result) > 0
        except Exception as e:
            logger.error("user_exists failed: %s", e)
            return False
    
    async def async_user_exists(self, user_id: str) -> bool:
        """Async version of user_exists."""
        if not self._enabled:
            return False
        
        try:
            result = await self._async_execute(
                "SELECT 1 FROM users WHERE user_id = %(uid)s LIMIT 1",
                {'uid': user_id}
            )
            return len(result) > 0
        except Exception as e:
            logger.error("async_user_exists failed: %s", e)
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
    
    async def async_get_all_users(self) -> List[UserData]:
        """Async version of get_all_users.
        
        Uses argMax with GROUP BY since no filter is applied (0% selectivity).
        FINAL would merge the entire table which is expensive.
        """
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
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
            logger.error("async_get_all_users failed: %s", e)
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
    
    async def async_get_online_users(self) -> List[str]:
        """Async version of get_online_users.
        
        Uses argMax with GROUP BY since online users are typically ≤50% of total.
        This avoids the overhead of merging the entire table with FINAL.
        """
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
                "SELECT user_id "
                "FROM users "
                "GROUP BY user_id "
                "HAVING argMax(is_online, updated_at) = 1"
            )
            return [r[0] for r in result]
        except Exception as e:
            logger.error("async_get_online_users failed: %s", e)
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
    
    async def async_get_private_messages(self, user1: str, user2: str, limit: int = 50) -> List[Dict[str, Any]]:
        """Async version of get_private_messages."""
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
                "SELECT sender, content, timestamp FROM private_messages "
                "WHERE (sender = %(u1)s AND recipient = %(u2)s) OR (sender = %(u2)s AND recipient = %(u1)s) "
                "ORDER BY timestamp DESC LIMIT %(limit)s",
                {'u1': user1, 'u2': user2, 'limit': limit}
            )
            return [{'sender': r[0], 'content': r[1], 'timestamp': r[2]} for r in reversed(result)]
        except Exception as e:
            logger.error("async_get_private_messages failed: %s", e)
            return []
    
    def add_friend(self, user_id: str, friend_id: str, remark: str = "") -> bool:
        if not self._enabled:
            return False
        
        try:
            now = datetime.now()
            self._client.execute(
                "INSERT INTO friendships (user_id, friend_id, remark, created_at, updated_at) VALUES",
                [
                    {'user_id': user_id, 'friend_id': friend_id, 'remark': remark, 'created_at': now, 'updated_at': now},
                    {'user_id': friend_id, 'friend_id': user_id, 'remark': '', 'created_at': now, 'updated_at': now}
                ]
            )
            return True
        except Exception as e:
            logger.error("add_friend failed: %s", e)
            return False
    
    def remove_friend(self, user_id: str, friend_id: str) -> bool:
        if not self._enabled:
            return False
        
        try:
            now = datetime.now()
            self._client.execute(
                "INSERT INTO friendships (user_id, friend_id, remark, created_at, updated_at) VALUES",
                [
                    {'user_id': user_id, 'friend_id': friend_id, 'remark': '__deleted__', 'created_at': now, 'updated_at': now},
                    {'user_id': friend_id, 'friend_id': user_id, 'remark': '__deleted__', 'created_at': now, 'updated_at': now}
                ]
            )
            return True
        except Exception as e:
            logger.error("remove_friend failed: %s", e)
            return False
    
    def get_friends(self, user_id: str) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        
        try:
            result = self._client.execute(
                "SELECT friend_id, remark, created_at "
                "FROM friendships FINAL "
                "WHERE user_id = %(uid)s AND remark != '__deleted__' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'friend_id': r[0], 'remark': r[1], 'created_at': r[2]} for r in result]
        except Exception as e:
            logger.error("get_friends failed: %s", e)
            return []
    
    async def async_get_friends(self, user_id: str) -> List[Dict[str, Any]]:
        """Async version of get_friends."""
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
                "SELECT friend_id, remark, created_at "
                "FROM friendships FINAL "
                "WHERE user_id = %(uid)s AND remark != '__deleted__' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'friend_id': r[0], 'remark': r[1], 'created_at': r[2]} for r in result]
        except Exception as e:
            logger.error("async_get_friends failed: %s", e)
            return []
    
    def is_friend(self, user_id: str, friend_id: str) -> bool:
        if not self._enabled:
            return False
        
        try:
            result = self._client.execute(
                "SELECT remark FROM friendships FINAL "
                "WHERE user_id = %(uid)s AND friend_id = %(fid)s "
                "LIMIT 1",
                {'uid': user_id, 'fid': friend_id}
            )
            if result and result[0][0] != '__deleted__':
                return True
            return False
        except Exception as e:
            logger.error("is_friend failed: %s", e)
            return False
    
    async def async_is_friend(self, user_id: str, friend_id: str) -> bool:
        """Async version of is_friend."""
        if not self._enabled:
            return False
        
        try:
            result = await self._async_execute(
                "SELECT remark FROM friendships FINAL "
                "WHERE user_id = %(uid)s AND friend_id = %(fid)s "
                "LIMIT 1",
                {'uid': user_id, 'fid': friend_id}
            )
            if result and result[0][0] != '__deleted__':
                return True
            return False
        except Exception as e:
            logger.error("async_is_friend failed: %s", e)
            return False
    
    def set_friend_remark(self, user_id: str, friend_id: str, remark: str) -> bool:
        if not self._enabled:
            return False
        
        try:
            now = datetime.now()
            self._client.execute(
                "INSERT INTO friendships (user_id, friend_id, remark, created_at, updated_at) VALUES",
                [{'user_id': user_id, 'friend_id': friend_id, 'remark': remark, 'created_at': now, 'updated_at': now}]
            )
            return True
        except Exception as e:
            logger.error("set_friend_remark failed: %s", e)
            return False
    
    def create_friend_request(self, request_id: str, from_user: str, to_user: str, message: str = "") -> bool:
        if not self._enabled:
            return False
        
        try:
            now = datetime.now()
            self._client.execute(
                "INSERT INTO friend_requests (id, from_user, to_user, message, status, created_at, updated_at) VALUES",
                [{'id': request_id, 'from_user': from_user, 'to_user': to_user, 
                  'message': message, 'status': 'pending', 'created_at': now, 'updated_at': now}]
            )
            return True
        except Exception as e:
            logger.error("create_friend_request failed: %s", e)
            return False
    
    def get_friend_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        if not self._enabled:
            return None
        
        try:
            result = self._client.execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE id = %(rid)s "
                "LIMIT 1",
                {'rid': request_id}
            )
            if result:
                r = result[0]
                return {'id': r[0], 'from_user': r[1], 'to_user': r[2], 'message': r[3], 'status': r[4], 'created_at': r[5]}
            return None
        except Exception as e:
            logger.error("get_friend_request failed: %s", e)
            return None
    
    async def async_get_friend_request(self, request_id: str) -> Optional[Dict[str, Any]]:
        """Async version of get_friend_request."""
        if not self._enabled:
            return None
        
        try:
            result = await self._async_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE id = %(rid)s "
                "LIMIT 1",
                {'rid': request_id}
            )
            if result:
                r = result[0]
                return {'id': r[0], 'from_user': r[1], 'to_user': r[2], 'message': r[3], 'status': r[4], 'created_at': r[5]}
            return None
        except Exception as e:
            logger.error("async_get_friend_request failed: %s", e)
            return None
    
    def get_pending_friend_requests(self, user_id: str) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        
        try:
            result = self._client.execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE to_user = %(uid)s AND status = 'pending' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'id': r[0], 'from_user': r[1], 'to_user': r[2], 'message': r[3], 'status': r[4], 'created_at': r[5]} for r in result]
        except Exception as e:
            logger.error("get_pending_friend_requests failed: %s", e)
            return []
    
    async def async_get_pending_friend_requests(self, user_id: str) -> List[Dict[str, Any]]:
        """Async version of get_pending_friend_requests."""
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE to_user = %(uid)s AND status = 'pending' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'id': r[0], 'from_user': r[1], 'to_user': r[2], 'message': r[3], 'status': r[4], 'created_at': r[5]} for r in result]
        except Exception as e:
            logger.error("async_get_pending_friend_requests failed: %s", e)
            return []
    
    def get_sent_friend_requests(self, user_id: str) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        
        try:
            result = self._client.execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE from_user = %(uid)s AND status = 'pending' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'id': r[0], 'from_user': r[1], 'to_user': r[2], 'message': r[3], 'status': r[4], 'created_at': r[5]} for r in result]
        except Exception as e:
            logger.error("get_sent_friend_requests failed: %s", e)
            return []
    
    async def async_get_sent_friend_requests(self, user_id: str) -> List[Dict[str, Any]]:
        """Async version of get_sent_friend_requests."""
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests FINAL "
                "WHERE from_user = %(uid)s AND status = 'pending' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'id': r[0], 'from_user': r[1], 'to_user': r[2], 'message': r[3], 'status': r[4], 'created_at': r[5]} for r in result]
        except Exception as e:
            logger.error("async_get_sent_friend_requests failed: %s", e)
            return []
    
    def update_friend_request_status(self, request_id: str, status: str) -> bool:
        if not self._enabled:
            return False
        
        try:
            now = datetime.now()
            existing = self.get_friend_request(request_id)
            if not existing:
                return False
            
            self._client.execute(
                "INSERT INTO friend_requests (id, from_user, to_user, message, status, created_at, updated_at) VALUES",
                [{'id': request_id, 'from_user': existing['from_user'], 'to_user': existing['to_user'],
                  'message': existing['message'], 'status': status, 'created_at': existing['created_at'], 'updated_at': now}]
            )
            return True
        except Exception as e:
            logger.error("update_friend_request_status failed: %s", e)
            return False
    
    def has_pending_request(self, from_user: str, to_user: str) -> bool:
        if not self._enabled:
            return False
        
        try:
            result = self._client.execute(
                "SELECT 1 FROM friend_requests FINAL "
                "WHERE from_user = %(f)s AND to_user = %(t)s AND status = 'pending' "
                "LIMIT 1",
                {'f': from_user, 't': to_user}
            )
            return len(result) > 0
        except Exception as e:
            logger.error("has_pending_request failed: %s", e)
            return False
    
    async def async_has_pending_request(self, from_user: str, to_user: str) -> bool:
        """Async version of has_pending_request."""
        if not self._enabled:
            return False
        
        try:
            result = await self._async_execute(
                "SELECT 1 FROM friend_requests FINAL "
                "WHERE from_user = %(f)s AND to_user = %(t)s AND status = 'pending' "
                "LIMIT 1",
                {'f': from_user, 't': to_user}
            )
            return len(result) > 0
        except Exception as e:
            logger.error("async_has_pending_request failed: %s", e)
            return False


def get_database() -> Database:
    global _store
    if _store is None:
        _store = Database()
    return _store
