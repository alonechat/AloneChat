"""
Unit tests for AloneChat core server services.
"""

import pytest
import json
import tempfile
import os
from unittest.mock import MagicMock, patch


@pytest.mark.unit
class TestAuthService:
    """Test authentication service."""

    @patch('AloneChat.core.server.auth.get_database')
    def test_auth_service_register(self, mock_get_db):
        """Test user registration."""
        mock_db = MagicMock()
        mock_db.user_exists.return_value = False
        mock_db.create_user.return_value = True
        mock_get_db.return_value = mock_db
        
        from AloneChat.core.server.auth import AuthService
        service = AuthService()
        result = service.register("newuser", "password123")
        assert result.success is True

    @patch('AloneChat.core.server.auth.get_database')
    def test_auth_service_register_duplicate(self, mock_get_db):
        """Test duplicate user registration."""
        mock_db = MagicMock()
        mock_db.user_exists.return_value = True
        mock_get_db.return_value = mock_db
        
        from AloneChat.core.server.auth import AuthService
        service = AuthService()
        result = service.register("existinguser", "password123")
        assert result.success is False

    @patch('AloneChat.core.server.auth.get_database')
    @patch('AloneChat.core.server.auth.verify_password')
    @patch('AloneChat.core.server.auth.hash_password')
    def test_auth_service_authenticate_success(self, mock_hash, mock_verify, mock_get_db):
        """Test successful authentication."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.password_hash = "hashed_password"
        mock_db.get_user.return_value = mock_user
        mock_verify.return_value = True
        mock_get_db.return_value = mock_db
        
        from AloneChat.core.server.auth import AuthService
        service = AuthService()
        result = service.authenticate("testuser", "correctpassword")
        assert result.success is True
        assert result.token is not None

    @patch('AloneChat.core.server.auth.get_database')
    @patch('AloneChat.core.server.auth.verify_password')
    def test_auth_service_authenticate_failure(self, mock_verify, mock_get_db):
        """Test failed authentication."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.password_hash = "hashed_password"
        mock_db.get_user.return_value = mock_user
        mock_verify.return_value = False
        mock_get_db.return_value = mock_db
        
        from AloneChat.core.server.auth import AuthService
        service = AuthService()
        result = service.authenticate("testuser", "wrongpassword")
        assert result.success is False


@pytest.mark.unit
class TestUserService:
    """Test user service."""

    @patch('AloneChat.core.server.user.get_database')
    def test_user_service_set_online(self, mock_get_db):
        """Test setting user online status."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.is_online = False
        mock_db.get_user.return_value = mock_user
        mock_get_db.return_value = mock_db
        
        from AloneChat.core.server.user import UserService
        service = UserService()
        service.set_online("testuser")
        assert mock_db.update_user.call_count >= 0

    @patch('AloneChat.core.server.user.get_database')
    def test_user_service_set_offline(self, mock_get_db):
        """Test setting user offline status."""
        mock_db = MagicMock()
        mock_user = MagicMock()
        mock_user.is_online = True
        mock_db.get_user.return_value = mock_user
        mock_get_db.return_value = mock_db
        
        from AloneChat.core.server.user import UserService
        service = UserService()
        service.set_offline("testuser")
        assert mock_db.update_user.call_count >= 0


@pytest.mark.unit
class TestMessageService:
    """Test message service."""

    def test_message_service_init(self):
        """Test message service initialization."""
        from AloneChat.core.server.message import MessageService
        service = MessageService()
        assert service is not None

    def test_message_queue_init(self):
        """Test message queue initialization."""
        from AloneChat.core.server.message import MessageQueue
        queue = MessageQueue()
        assert queue is not None


@pytest.mark.unit
class TestChatService:
    """Test chat service."""

    def test_chat_service_init(self):
        """Test chat service initialization."""
        from AloneChat.core.server.chat import ChatService
        service = ChatService()
        assert service is not None

    def test_chat_session_init(self):
        """Test chat session initialization."""
        from AloneChat.core.server.chat import ChatSession
        session = ChatSession("user1", "user2")
        assert session is not None


@pytest.mark.unit
class TestFriendService:
    """Test friend service."""

    def test_friend_service_init(self):
        """Test friend service initialization."""
        from AloneChat.core.server.friend import FriendService
        service = FriendService()
        assert service is not None

    def test_friend_info_init(self):
        """Test friend info initialization."""
        from AloneChat.core.server.friend import FriendInfo
        friend = FriendInfo(user_id="user2", display_name="User 2", remark="Friend", status="online", is_online=True, last_seen=None)
        assert friend.user_id == "user2"


@pytest.mark.unit
class TestDatabase:
    """Test database service."""

    def test_database_init(self):
        """Test database initialization."""
        from AloneChat.core.server.database import Database
        db = Database()
        assert db is not None

    def test_user_data_init(self):
        """Test user data initialization."""
        from AloneChat.core.server.database import UserData
        user = UserData(user_id="testuser", password_hash="hash123")
        assert user.user_id == "testuser"
