"""
Unit tests for the refactored server components.

Tests cover:
- Authentication service
- User service
- Message service
- Chat service
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from AloneChat.core.message.protocol import Message, MessageType
from AloneChat.core.server import (
    AuthService, AuthResult, RegisterResult,
    UserService, UserInfo, Status,
    MessageService, MessageQueue, DeliveryResult,
    ChatService, ChatSession, PendingMessage,
)


class TestMessageQueue:
    """Tests for the MessageQueue class."""
    
    def setup_method(self):
        self.queue = MessageQueue(max_size=10)
    
    @pytest.mark.asyncio
    async def test_put_and_get(self):
        """Test basic put and get operations."""
        await self.queue.put("test message")
        result = await self.queue.get(timeout=1.0)
        assert result == "test message"
    
    @pytest.mark.asyncio
    async def test_get_nowait(self):
        """Test non-blocking get."""
        await self.queue.put("test")
        result = self.queue.get_nowait()
        assert result == "test"
        
        result = self.queue.get_nowait()
        assert result is None
    
    @pytest.mark.asyncio
    async def test_overflow(self):
        """Test queue overflow handling."""
        small_queue = MessageQueue(max_size=2)
        
        await small_queue.put("msg1")
        await small_queue.put("msg2")
        await small_queue.put("msg3")
        
        assert small_queue.size() == 2
    
    @pytest.mark.asyncio
    async def test_get_batch(self):
        """Test batch retrieval."""
        for i in range(5):
            await self.queue.put(f"msg{i}")
        
        messages = self.queue.get_batch(max_count=3)
        assert len(messages) == 3


class TestMessageService:
    """Tests for the MessageService class."""
    
    def setup_method(self):
        self.service = MessageService()
    
    def test_get_queue(self):
        """Test queue creation."""
        queue = self.service.get_queue("user1")
        assert queue is not None
        assert isinstance(queue, MessageQueue)
    
    def test_has_connection(self):
        """Test connection check."""
        assert self.service.has_connection("user1") is False
        
        self.service.register_connection("user1", lambda x: None)
        assert self.service.has_connection("user1") is True
    
    def test_register_unregister_connection(self):
        """Test connection management."""
        self.service.register_connection("user1", lambda x: None)
        assert self.service.has_connection("user1")
        
        self.service.unregister_connection("user1")
        assert not self.service.has_connection("user1")
    
    @pytest.mark.asyncio
    async def test_send_to_user_with_connection(self):
        """Test sending to connected user."""
        messages = []
        
        async def send_func(msg):
            messages.append(msg)
        
        self.service.register_connection("user1", send_func)
        
        message = Message(MessageType.TEXT, "sender", "content")
        result = await self.service.send_to_user("user1", message)
        
        assert result.success
        assert len(messages) == 1
    
    @pytest.mark.asyncio
    async def test_send_to_user_without_connection(self):
        """Test sending to offline user queues the message."""
        message = Message(MessageType.TEXT, "sender", "content")
        result = await self.service.send_to_user("user1", message)
        
        assert result.success
        
        queue = self.service.get_queue("user1")
        queued = queue.get_nowait()
        assert queued is not None
    
    @pytest.mark.asyncio
    async def test_broadcast(self):
        """Test broadcasting messages."""
        messages1 = []
        messages2 = []
        
        async def send1(msg):
            messages1.append(msg)
        
        async def send2(msg):
            messages2.append(msg)
        
        self.service.register_connection("user1", send1)
        self.service.register_connection("user2", send2)
        
        message = Message(MessageType.TEXT, "sender", "broadcast")
        results = await self.service.broadcast(message, exclude={"sender"})
        
        assert len(results) == 2
        assert len(messages1) == 1
        assert len(messages2) == 1


class TestChatService:
    """Tests for the ChatService class."""
    
    def setup_method(self):
        self.service = ChatService()
    
    def test_make_session_id(self):
        """Test session ID generation."""
        id1 = ChatService.make_session_id("alice", "bob")
        id2 = ChatService.make_session_id("bob", "alice")
        
        assert id1 == id2
        assert id1 == "alice:bob"
    
    def test_get_or_create_session(self):
        """Test session creation."""
        session = self.service.get_or_create_session("alice", "bob")
        
        assert session is not None
        assert session.user1 == "alice"
        assert session.user2 == "bob"
    
    def test_record_message(self):
        """Test message recording."""
        session = self.service.record_message("alice", "bob", "Hello!", delivered=True)
        
        assert session.message_count == 1
        
        history = self.service.get_history("alice", "bob")
        assert len(history) == 1
        assert history[0]['sender'] == "alice"
        assert history[0]['content'] == "Hello!"
    
    def test_pending_messages(self):
        """Test pending message handling."""
        self.service.record_message("alice", "bob", "Hello!", delivered=False)
        
        pending = self.service.get_pending("bob")
        assert len(pending) == 1
        assert pending[0].sender == "alice"
        
        count = self.service.clear_pending("bob")
        assert count == 1
        
        pending = self.service.get_pending("bob")
        assert len(pending) == 0
    
    def test_get_user_sessions(self):
        """Test getting user sessions."""
        self.service.get_or_create_session("alice", "bob")
        self.service.get_or_create_session("alice", "charlie")
        
        sessions = self.service.get_user_sessions("alice")
        assert len(sessions) == 2
    
    def test_get_recent_chats(self):
        """Test getting recent chats."""
        self.service.record_message("alice", "bob", "Hi")
        self.service.record_message("alice", "charlie", "Hello")
        
        recent = self.service.get_recent_chats("alice", limit=1)
        assert len(recent) == 1


class TestUserInfo:
    """Tests for the UserInfo dataclass."""
    
    def test_create_user_info(self):
        """Test creating user info."""
        info = UserInfo(
            user_id="test_user",
            status=Status.ONLINE,
            display_name="Test User"
        )
        
        assert info.user_id == "test_user"
        assert info.status == Status.ONLINE
    
    def test_to_dict(self):
        """Test conversion to dictionary."""
        info = UserInfo(
            user_id="test_user",
            status=Status.ONLINE,
            display_name="Test User"
        )
        
        d = info.to_dict()
        
        assert d['user_id'] == "test_user"
        assert d['status'] == "online"
        assert d['is_online'] is True


class TestAuthResult:
    """Tests for AuthResult dataclass."""
    
    def test_success_result(self):
        """Test successful auth result."""
        result = AuthResult(
            success=True,
            user_id="test_user",
            token="test_token"
        )
        
        assert result.success
        assert result.user_id == "test_user"
        assert result.token == "test_token"
        assert result.error is None
    
    def test_failure_result(self):
        """Test failed auth result."""
        result = AuthResult(
            success=False,
            error="Invalid credentials"
        )
        
        assert not result.success
        assert result.error == "Invalid credentials"


class TestRegisterResult:
    """Tests for RegisterResult dataclass."""
    
    def test_success_result(self):
        """Test successful registration result."""
        result = RegisterResult(
            success=True,
            user_id="new_user"
        )
        
        assert result.success
        assert result.user_id == "new_user"
    
    def test_failure_result(self):
        """Test failed registration result."""
        result = RegisterResult(
            success=False,
            error="Username already exists"
        )
        
        assert not result.success
        assert result.error == "Username already exists"


class TestDeliveryResult:
    """Tests for DeliveryResult dataclass."""
    
    def test_success_result(self):
        """Test successful delivery result."""
        result = DeliveryResult(
            success=True,
            user_id="test_user"
        )
        
        assert result.success
        assert result.user_id == "test_user"
        assert result.error is None
    
    def test_failure_result(self):
        """Test failed delivery result."""
        result = DeliveryResult(
            success=False,
            user_id="test_user",
            error="Connection closed"
        )
        
        assert not result.success
        assert result.error == "Connection closed"


class TestStatus:
    """Tests for Status enum."""
    
    def test_status_values(self):
        """Test status enum values."""
        assert Status.ONLINE.value == 1
        assert Status.AWAY.value == 2
        assert Status.BUSY.value == 3
        assert Status.OFFLINE.value == 4


class TestChatSession:
    """Tests for ChatSession dataclass."""
    
    def test_session_id(self):
        """Test session ID generation."""
        session = ChatSession(user1="alice", user2="bob")
        
        assert session.session_id == "alice:bob"
    
    def test_get_partner(self):
        """Test getting partner from session."""
        session = ChatSession(user1="alice", user2="bob")
        
        assert session.get_partner("alice") == "bob"
        assert session.get_partner("bob") == "alice"
        assert session.get_partner("charlie") is None


class TestPendingMessage:
    """Tests for PendingMessage dataclass."""
    
    def test_create_pending_message(self):
        """Test creating pending message."""
        msg = PendingMessage(
            message="Hello",
            sender="alice",
            recipient="bob"
        )
        
        assert msg.message == "Hello"
        assert msg.sender == "alice"
        assert msg.recipient == "bob"
        assert not msg.delivered


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
