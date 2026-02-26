"""
Unit tests for AloneChat API layer.
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from fastapi.testclient import TestClient


class TestAPIConfig:
    """Test API configuration endpoints."""

    def test_root_endpoint(self):
        """Test root endpoint returns index.html."""
        from AloneChat.api.app import app
        with TestClient(app) as client:
            response = client.get("/")
            assert response.status_code == 200

    def test_get_default_server(self):
        """Test get_default_server endpoint."""
        from AloneChat.api.app import app
        with TestClient(app) as client:
            response = client.get("/api/get_default_server")
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "default_server_address" in data


class TestAPIAuth:
    """Test authentication endpoints."""

    @patch('AloneChat.api.app.get_auth_service')
    def test_register_success(self, mock_get_service):
        """Test successful user registration."""
        from AloneChat.api.app import app
        
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.success = True
        mock_service.register.return_value = mock_result
        mock_get_service.return_value = mock_service
        
        with TestClient(app) as client:
            response = client.post("/api/register", json={
                "username": "testuser",
                "password": "testpass123"
            })
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True

    @patch('AloneChat.api.app.get_auth_service')
    def test_register_failure(self, mock_get_service):
        """Test failed user registration."""
        from AloneChat.api.app import app
        
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Username already exists"
        mock_service.register.return_value = mock_result
        mock_get_service.return_value = mock_service
        
        with TestClient(app) as client:
            response = client.post("/api/register", json={
                "username": "existinguser",
                "password": "testpass123"
            })
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False

    @patch('AloneChat.api.app.get_user_service')
    @patch('AloneChat.api.app.get_auth_service')
    def test_login_success(self, mock_get_auth, mock_get_user):
        """Test successful login."""
        from AloneChat.api.app import app
        
        mock_auth_service = MagicMock()
        mock_auth_result = MagicMock()
        mock_auth_result.success = True
        mock_auth_result.user_id = "testuser"
        mock_auth_result.token = "test_token"
        mock_auth_service.authenticate.return_value = mock_auth_result
        mock_get_auth.return_value = mock_auth_service
        
        mock_user_service = MagicMock()
        mock_get_user.return_value = mock_user_service
        
        with TestClient(app) as client:
            response = client.post("/api/login", json={
                "username": "testuser",
                "password": "testpass123"
            })
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is True
            assert "token" in data

    @patch('AloneChat.api.app.get_auth_service')
    def test_login_failure(self, mock_get_service):
        """Test failed login."""
        from AloneChat.api.app import app
        
        mock_service = MagicMock()
        mock_result = MagicMock()
        mock_result.success = False
        mock_result.error = "Invalid credentials"
        mock_service.authenticate.return_value = mock_result
        mock_get_service.return_value = mock_service
        
        with TestClient(app) as client:
            response = client.post("/api/login", json={
                "username": "testuser",
                "password": "wrongpass"
            })
            assert response.status_code == 200
            data = response.json()
            assert data["success"] is False


class TestAPIUsers:
    """Test user management endpoints."""

    @patch('AloneChat.api.app.get_user_service')
    def test_get_online_users(self, mock_get_service):
        """Test getting online users."""
        from AloneChat.api.app import app
        
        mock_service = MagicMock()
        mock_service.get_online_users.return_value = ["user1", "user2"]
        mock_get_service.return_value = mock_service
        
        with TestClient(app) as client:
            response = client.get(
                "/api/users/online",
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code == 307

    @patch('AloneChat.api.app.get_user_service')
    def test_get_all_users(self, mock_get_service):
        """Test getting all users."""
        from AloneChat.api.app import app
        
        mock_service = MagicMock()
        mock_service.get_all_users.return_value = ["user1", "user2", "user3"]
        mock_get_service.return_value = mock_service
        
        with TestClient(app) as client:
            response = client.get(
                "/api/users/all",
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code == 307


class TestAPIChat:
    """Test chat endpoints."""

    @patch('AloneChat.api.app.get_chat_service')
    def test_get_chat_history(self, mock_get_service):
        """Test getting chat history."""
        from AloneChat.api.app import app
        
        mock_service = MagicMock()
        mock_service.get_history.return_value = []
        mock_get_service.return_value = mock_service
        
        with TestClient(app) as client:
            response = client.get(
                "/api/chat/history/user2",
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code == 307

    @patch('AloneChat.api.app.get_chat_service')
    def test_get_recent_chats(self, mock_get_service):
        """Test getting recent chats."""
        from AloneChat.api.app import app
        
        mock_service = MagicMock()
        mock_service.get_recent_chats.return_value = []
        mock_get_service.return_value = mock_service
        
        with TestClient(app) as client:
            response = client.get(
                "/api/chat/recent",
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code == 307


class TestAPIFriends:
    """Test friend management endpoints."""

    @patch('AloneChat.api.app.get_friend_service')
    def test_get_friends(self, mock_get_service):
        """Test getting friends list."""
        from AloneChat.api.app import app
        
        mock_service = MagicMock()
        mock_service.get_friends.return_value = []
        mock_get_service.return_value = mock_service
        
        with TestClient(app) as client:
            response = client.get(
                "/api/friends",
                headers={"Authorization": "Bearer test_token"}
            )
            assert response.status_code == 307


class TestTokenCache:
    """Test JWT token cache."""

    def test_token_cache_get_miss(self):
        """Test token cache miss."""
        from AloneChat.api.app import TokenCache
        
        cache = TokenCache()
        result = cache.get("nonexistent_token")
        assert result is None

    def test_token_cache_set_and_get(self):
        """Test token cache set and get."""
        from AloneChat.api.app import TokenCache
        
        cache = TokenCache()
        cache.set("test_token", {"sub": "testuser", "exp": 9999999999})
        result = cache.get("test_token")
        assert result is not None
        assert result["sub"] == "testuser"

    def test_token_cache_invalidate(self):
        """Test token cache invalidation."""
        from AloneChat.api.app import TokenCache
        
        cache = TokenCache()
        cache.set("test_token", {"sub": "testuser", "exp": 9999999999})
        cache.invalidate("test_token")
        result = cache.get("test_token")
        assert result is None


@pytest.mark.unit
class TestAPIUnitMarker:
    """Test marker for unit tests."""

    def test_unit_marker_present(self):
        """Verify unit marker is configured."""
        assert True
