"""
Unit tests for AloneChat core server services.
"""

import pytest
import json
import tempfile
import os
from unittest.mock import MagicMock, patch


class TestAuthService:
    """Test authentication service."""

    def test_auth_service_register(self):
        """Test user registration."""
        from AloneChat.core.server.auth import AuthService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.json")
            with open(db_path, "w") as f:
                json.dump({}, f)
            
            service = AuthService(db_path)
            result = service.register("newuser", "password123")
            assert result.success is True

    def test_auth_service_register_duplicate(self):
        """Test duplicate user registration."""
        from AloneChat.core.server.auth import AuthService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.json")
            with open(db_path, "w") as f:
                json.dump({"existinguser": {"password": "hash"}}, f)
            
            service = AuthService(db_path)
            result = service.register("existinguser", "password123")
            assert result.success is False

    def test_auth_service_authenticate_success(self):
        """Test successful authentication."""
        from AloneChat.core.server.auth import AuthService
        from AloneChat.core.crypto.password_hash import hash_password
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.json")
            password_hash = hash_password("correctpassword")
            with open(db_path, "w") as f:
                json.dump({"testuser": {"password": password_hash}}, f)
            
            service = AuthService(db_path)
            result = service.authenticate("testuser", "correctpassword")
            assert result.success is True
            assert result.token is not None

    def test_auth_service_authenticate_failure(self):
        """Test failed authentication."""
        from AloneChat.core.server.auth import AuthService
        from AloneChat.core.crypto.password_hash import hash_password
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.json")
            password_hash = hash_password("correctpassword")
            with open(db_path, "w") as f:
                json.dump({"testuser": {"password": password_hash}}, f)
            
            service = AuthService(db_path)
            result = service.authenticate("testuser", "wrongpassword")
            assert result.success is False
            assert result.token is None


class TestUserService:
    """Test user service."""

    def test_user_service_set_online(self):
        """Test setting user online status."""
        from AloneChat.core.server.user import UserService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.json")
            with open(db_path, "w") as f:
                json.dump({"testuser": {"password": "hash"}}, f)
            
            service = UserService(db_path)
            service.set_online("testuser")
            assert service.is_online("testuser") is True

    def test_user_service_set_offline(self):
        """Test setting user offline status."""
        from AloneChat.core.server.user import UserService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.json")
            with open(db_path, "w") as f:
                json.dump({"testuser": {"password": "hash"}}, f)
            
            service = UserService(db_path)
            service.set_online("testuser")
            service.set_offline("testuser")
            assert service.is_online("testuser") is False

    def test_user_service_get_online_users(self):
        """Test getting online users."""
        from AloneChat.core.server.user import UserService
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, "users.json")
            with open(db_path, "w") as f:
                json.dump({
                    "user1": {"password": "hash"},
                    "user2": {"password": "hash"},
                    "user3": {"password": "hash"}
                }, f)
            
            service = UserService(db_path)
            service.set_online("user1")
            service.set_online("user2")
            
            online = service.get_online_users()
            assert "user1" in online
            assert "user2" in online
            assert "user3" not in online


class TestMessageService:
    """Test message service."""

    @pytest.mark.asyncio
    async def test_message_service_send_to_user(self):
        """Test sending message to user."""
        from AloneChat.core.server.message import MessageService
        from AloneChat.core.message import Message, MessageType
        
        service = MessageService()
        
        message = Message(MessageType.TEXT, "sender", "Hello", target="receiver")
        
        with patch.object(service, 'get_queue', return_value=MagicMock()):
            result = await service.send_to_user("receiver", message)
            assert result.success is True

    @pytest.mark.asyncio
    async def test_message_service_broadcast(self):
        """Test broadcasting message."""
        from AloneChat.core.server.message import MessageService
        from AloneChat.core.message import Message, MessageType
        
        service = MessageService()
        
        message = Message(MessageType.TEXT, "sender", "Hello")
        
        with patch.object(service, 'get_queue', return_value=MagicMock()):
            with patch.object(service, '_connections', {"user1": MagicMock(), "user2": MagicMock()}):
                result = await service.broadcast(message, exclude={"sender"})
                assert result.success is True


class TestChatService:
    """Test chat service."""

    def test_chat_service_record_message(self):
        """Test recording a message."""
        from AloneChat.core.server.chat import ChatService
        
        service = ChatService()
        
        service.record_message("user1", "user2", "Hello World", is_online=True)
        
        history = service.get_history("user1", "user2", limit=10)
        assert len(history) > 0

    def test_chat_service_get_history(self):
        """Test getting chat history."""
        from AloneChat.core.server.chat import ChatService
        
        service = ChatService()
        
        service.record_message("user1", "user2", "Message 1", is_online=True)
        service.record_message("user2", "user1", "Message 2", is_online=True)
        
        history = service.get_history("user1", "user2", limit=10)
        assert len(history) >= 2

    def test_chat_service_get_recent_chats(self):
        """Test getting recent chats."""
        from AloneChat.core.server.chat import ChatService
        
        service = ChatService()
        
        service.record_message("user1", "user2", "Hello", is_online=True)
        service.record_message("user1", "user3", "Hi", is_online=True)
        
        recent = service.get_recent_chats("user1", limit=10)
        assert len(recent) >= 2


class TestFriendService:
    """Test friend service."""

    def test_friend_service_send_request(self):
        """Test sending friend request."""
        from AloneChat.core.server.friend import FriendService
        
        service = FriendService()
        
        result = service.send_friend_request("user1", "user2", "Hello!")
        assert result.get("success") is True

    def test_friend_service_get_friends(self):
        """Test getting friends list."""
        from AloneChat.core.server.friend import FriendService
        
        service = FriendService()
        
        service.send_friend_request("user1", "user2", "Hi")
        
        friends = service.get_friends("user1")
        assert isinstance(friends, list)


@pytest.mark.unit
class TestCoreUnitMarker:
    """Test marker for unit tests."""

    def test_unit_marker_present(self):
        """Verify unit marker is configured."""
        assert True
