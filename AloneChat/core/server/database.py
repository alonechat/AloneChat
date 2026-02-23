"""
Database service for AloneChat server.

Provides ClickHouse-based data persistence with optimized batch operations.
Supports multi-thread and multi-process parallelization.
"""

import asyncio
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from queue import Empty, Queue
from typing import Any, Dict, List, Optional

from AloneChat.config import config

logger = logging.getLogger(__name__)


class ConnectionPool:
    """Thread-safe database connection pool with health checking."""
    
    def __init__(self, max_size: int = 10, overflow: int = 10, timeout: float = 30.0):
        self._max_size = max_size
        self._overflow = overflow
        self._timeout = timeout
        self._pool: Queue = Queue(maxsize=max_size + overflow)
        self._created = 0
        self._lock = threading.Lock()
        self._connection_args = None
        self._health_check_interval = 60.0
        self._last_health_check = time.time()
    
    def initialize(self, host: str, port: int, user: str, password: str, database: str) -> None:
        self._connection_args = {
            'host': host,
            'port': port,
            'user': user,
            'password': password,
            'database': database,
        }
        for _ in range(self._max_size):
            conn = self._create_connection()
            if conn:
                self._pool.put(conn)
    
    def _create_connection(self):
        try:
            from clickhouse_driver import Client
            return Client(**self._connection_args)
        except Exception as e:
            logger.warning("Failed to create connection: %s", e)
            return None
    
    def _is_connection_healthy(self, conn) -> bool:
        try:
            conn.execute("SELECT 1")
            return True
        except Exception:
            return False
    
    def get(self, timeout: Optional[float] = None):
        timeout = timeout or self._timeout
        try:
            conn = self._pool.get(timeout=timeout)
            
            if time.time() - self._last_health_check > self._health_check_interval:
                if not self._is_connection_healthy(conn):
                    try:
                        conn.disconnect()
                    except Exception:
                        pass
                    conn = self._create_connection()
                    if conn is None:
                        raise RuntimeError("Failed to create healthy connection")
                self._last_health_check = time.time()
            
            return conn
        except Empty:
            with self._lock:
                if self._created < self._max_size + self._overflow:
                    conn = self._create_connection()
                    if conn:
                        self._created += 1
                        return conn
            raise RuntimeError("Connection pool exhausted")
    
    def put(self, conn) -> None:
        try:
            self._pool.put_nowait(conn)
        except Exception:
            try:
                conn.disconnect()
            except Exception:
                pass
    
    def close_all(self) -> None:
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                conn.disconnect()
            except Exception:
                pass
    
    @property
    def size(self) -> int:
        return self._pool.qsize()


_connection_pool: Optional[ConnectionPool] = None
_pool_lock = threading.Lock()
_executor = ThreadPoolExecutor(
    max_workers=config.DB_WORKERS,
    thread_name_prefix="db_"
)


def get_connection_pool() -> ConnectionPool:
    global _connection_pool
    
    with _pool_lock:
        if _connection_pool is None:
            _connection_pool = ConnectionPool(
                max_size=config.DB_POOL_SIZE,
                overflow=config.DB_POOL_OVERFLOW,
                timeout=config.DB_POOL_TIMEOUT
            )
            _connection_pool.initialize(
                host=config.CLICKHOUSE_HOST,
                port=config.CLICKHOUSE_PORT,
                user=config.CLICKHOUSE_USER,
                password=config.CLICKHOUSE_PASSWORD,
                database=config.CLICKHOUSE_DATABASE,
            )
            
            try:
                client = _connection_pool.get(timeout=5.0)
                if client:
                    _ensure_database_and_tables(client, config.CLICKHOUSE_DATABASE)
                    _connection_pool.put(client)
                    logger.info("Database schema ensured: %s", config.CLICKHOUSE_DATABASE)
            except Exception as e:
                logger.warning("Failed to ensure database schema: %s", e)
            
            logger.info("Connection pool initialized: size=%d, overflow=%d",
                       config.DB_POOL_SIZE, config.DB_POOL_OVERFLOW)
        return _connection_pool


def get_client():
    pool = get_connection_pool()
    try:
        return pool.get(timeout=5.0)
    except Exception as e:
        logger.error("Failed to get connection from pool: %s", e)
        return None


def release_client(client) -> None:
    pool = get_connection_pool()
    pool.put(client)


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
        CREATE MATERIALIZED VIEW IF NOT EXISTS {database_name}.users_latest
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY user_id
        AS SELECT
            user_id,
            anyLast(password_hash) as password_hash,
            anyLast(display_name) as display_name,
            anyLast(status) as status,
            anyLast(is_online) as is_online,
            anyLast(last_seen) as last_seen,
            anyLast(created_at) as created_at,
            anyLast(updated_at) as updated_at
        FROM {database_name}.users
        GROUP BY user_id
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
        CREATE MATERIALIZED VIEW IF NOT EXISTS {database_name}.friendships_latest
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (user_id, friend_id)
        AS SELECT
            user_id,
            friend_id,
            anyLast(remark) as remark,
            anyLast(created_at) as created_at,
            anyLast(updated_at) as updated_at
        FROM {database_name}.friendships
        GROUP BY user_id, friend_id
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
    
    client.execute(f"""
        CREATE MATERIALIZED VIEW IF NOT EXISTS {database_name}.friend_requests_latest
        ENGINE = ReplacingMergeTree(updated_at)
        ORDER BY (id)
        AS SELECT
            id,
            anyLast(from_user) as from_user,
            anyLast(to_user) as to_user,
            anyLast(message) as message,
            anyLast(status) as status,
            anyLast(created_at) as created_at,
            anyLast(updated_at) as updated_at
        FROM {database_name}.friend_requests
        GROUP BY id
    """)


def initialize_database() -> bool:
    """Initialize database schema. Call once at startup."""
    try:
        from clickhouse_driver import Client
        client = Client(
            host=config.CLICKHOUSE_HOST,
            port=config.CLICKHOUSE_PORT,
            user=config.CLICKHOUSE_USER,
            password=config.CLICKHOUSE_PASSWORD,
        )
        _ensure_database_and_tables(client, config.CLICKHOUSE_DATABASE)
        client.disconnect()
        logger.info("Database schema initialized: %s", config.CLICKHOUSE_DATABASE)
        return True
    except Exception as e:
        logger.error("Failed to initialize database: %s", e)
        return False


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
    """High-performance database service with connection pooling."""
    
    def __init__(self, use_pool: bool = True):
        self._use_pool = use_pool
        self._enabled = True
        self._local_client = threading.local()
    
    def _get_client(self):
        if self._use_pool:
            return get_client()
        if not hasattr(self._local_client, 'client') or self._local_client.client is None:
            self._local_client.client = get_client()
        return self._local_client.client
    
    def _release_client(self, client) -> None:
        if self._use_pool and client:
            release_client(client)
    
    def _safe_execute(self, query, params=None):
        client = None
        try:
            client = self._get_client()
            if client is None:
                raise Exception("Database not available")
            
            if params:
                return client.execute(query, params)
            return client.execute(query)
        except Exception as e:
            logger.warning("Query failed: %s", e)
            raise
        finally:
            self._release_client(client)
    
    async def _async_execute(self, query, params=None):
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
            self._safe_execute(
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
            result = self._safe_execute(
                "SELECT user_id, password_hash, display_name, status, is_online, last_seen, created_at "
                "FROM users_latest "
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
        if not self._enabled:
            return None
        
        try:
            result = await self._async_execute(
                "SELECT user_id, password_hash, display_name, status, is_online, last_seen, created_at "
                "FROM users_latest "
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
            result = self._safe_execute(
                "SELECT 1 FROM users WHERE user_id = %(uid)s LIMIT 1",
                {'uid': user_id}
            )
            return len(result) > 0
        except Exception as e:
            logger.error("user_exists failed: %s", e)
            return False
    
    async def async_user_exists(self, user_id: str) -> bool:
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
            self._safe_execute(
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
            
            result = self._safe_execute(
                "SELECT user_id, "
                "  argMax(password_hash, updated_at) as password_hash, "
                "  argMax(display_name, updated_at) as display_name "
                "FROM users "
                "WHERE user_id IN %(uids)s "
                "GROUP BY user_id",
                {'uids': [u['user_id'] for u in updates]}
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
                self._safe_execute(
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
            result = self._safe_execute(
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
            result = self._safe_execute(
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
        if not self._enabled:
            return 0
        
        try:
            now = datetime.now()
            self._safe_execute(
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
            count_result = self._safe_execute(
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
            self._safe_execute(
                "INSERT INTO private_messages (id, sender, recipient, content, timestamp, delivered) VALUES",
                [{'id': msg_id, 'sender': sender, 'recipient': recipient,
                  'content': content, 'timestamp': datetime.now(), 'delivered': 1 if delivered else 0}]
            )
            return True
        except Exception as e:
            logger.error("save_private_message failed: %s", e)
            return False
    
    def batch_save_private_messages(self, messages: List[Dict[str, Any]]) -> int:
        """Batch insert private messages for better performance."""
        if not self._enabled or not messages:
            return 0
        
        try:
            batch_data = []
            for msg in messages:
                batch_data.append({
                    'id': msg['msg_id'],
                    'sender': msg['sender'],
                    'recipient': msg['recipient'],
                    'content': msg['content'],
                    'timestamp': msg.get('timestamp', datetime.now()),
                    'delivered': 1 if msg.get('delivered', False) else 0
                })
            
            self._safe_execute(
                "INSERT INTO private_messages (id, sender, recipient, content, timestamp, delivered) VALUES",
                batch_data
            )
            return len(batch_data)
        except Exception as e:
            logger.error("batch_save_private_messages failed: %s", e)
            return 0
    
    def get_private_messages(self, user1: str, user2: str, limit: int = 50) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        
        try:
            result = self._safe_execute(
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
            self._safe_execute(
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
            self._safe_execute(
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
            result = self._safe_execute(
                "SELECT friend_id, remark, created_at "
                "FROM friendships_latest "
                "WHERE user_id = %(uid)s AND remark != '__deleted__' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'friend_id': r[0], 'remark': r[1], 'created_at': r[2]} for r in result]
        except Exception as e:
            logger.error("get_friends failed: %s", e)
            return []
    
    async def async_get_friends(self, user_id: str) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
                "SELECT friend_id, remark, created_at "
                "FROM friendships_latest "
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
            result = self._safe_execute(
                "SELECT remark FROM friendships_latest "
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
        if not self._enabled:
            return False
        
        try:
            result = await self._async_execute(
                "SELECT remark FROM friendships_latest "
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
            self._safe_execute(
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
            self._safe_execute(
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
            result = self._safe_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests_latest "
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
        if not self._enabled:
            return None
        
        try:
            result = await self._async_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests_latest "
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
            result = self._safe_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests_latest "
                "WHERE to_user = %(uid)s AND status = 'pending' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'id': r[0], 'from_user': r[1], 'to_user': r[2], 'message': r[3], 'status': r[4], 'created_at': r[5]} for r in result]
        except Exception as e:
            logger.error("get_pending_friend_requests failed: %s", e)
            return []
    
    async def async_get_pending_friend_requests(self, user_id: str) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests_latest "
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
            result = self._safe_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests_latest "
                "WHERE from_user = %(uid)s AND status = 'pending' "
                "ORDER BY created_at DESC",
                {'uid': user_id}
            )
            return [{'id': r[0], 'from_user': r[1], 'to_user': r[2], 'message': r[3], 'status': r[4], 'created_at': r[5]} for r in result]
        except Exception as e:
            logger.error("get_sent_friend_requests failed: %s", e)
            return []
    
    async def async_get_sent_friend_requests(self, user_id: str) -> List[Dict[str, Any]]:
        if not self._enabled:
            return []
        
        try:
            result = await self._async_execute(
                "SELECT id, from_user, to_user, message, status, created_at "
                "FROM friend_requests_latest "
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
            
            self._safe_execute(
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
            result = self._safe_execute(
                "SELECT 1 FROM friend_requests_latest "
                "WHERE from_user = %(f)s AND to_user = %(t)s AND status = 'pending' "
                "LIMIT 1",
                {'f': from_user, 't': to_user}
            )
            return len(result) > 0
        except Exception as e:
            logger.error("has_pending_request failed: %s", e)
            return False
    
    async def async_has_pending_request(self, from_user: str, to_user: str) -> bool:
        if not self._enabled:
            return False
        
        try:
            result = await self._async_execute(
                "SELECT 1 FROM friend_requests_latest "
                "WHERE from_user = %(f)s AND to_user = %(t)s AND status = 'pending' "
                "LIMIT 1",
                {'f': from_user, 't': to_user}
            )
            return len(result) > 0
        except Exception as e:
            logger.error("async_has_pending_request failed: %s", e)
            return False


_store: Optional[Database] = None


def get_database() -> Database:
    global _store
    if _store is None:
        _store = Database()
    return _store


def shutdown_database() -> None:
    global _store, _connection_pool
    if _connection_pool:
        _connection_pool.close_all()
        _connection_pool = None
    _store = None
    logger.info("Database shutdown complete")
