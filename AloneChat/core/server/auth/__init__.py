"""
Authentication module for the server.

Provides JWT-based authentication with clear separation of concerns.
Supports token extraction from query parameters and cookies.
"""

import logging
from typing import Optional, Dict, Any
from urllib.parse import parse_qs

import jwt

from AloneChat.config import config
from AloneChat.core.server.interfaces import Authenticator, AuthResult

logger = logging.getLogger(__name__)


class JWTAuthenticator:
    """
    JWT-based authenticator implementation.
    
    Handles token validation using JWT and extracts tokens from
    various transport contexts (WebSocket connections).
    """
    
    def __init__(
        self,
        secret: str = None,
        algorithm: str = None,
        token_extractor = None
    ):
        """
        Initialize JWT authenticator.
        
        Args:
            secret: JWT secret key (defaults to config.JWT_SECRET)
            algorithm: JWT algorithm (defaults to config.JWT_ALGORITHM)
            token_extractor: Optional custom token extractor
        """
        self._secret = secret or config.JWT_SECRET
        self._algorithm = algorithm or config.JWT_ALGORITHM
        self._token_extractor = token_extractor or DefaultTokenExtractor()
    
    async def authenticate(self, token: str) -> AuthResult:
        """
        Validate a JWT token.
        
        Args:
            token: JWT token string
            
        Returns:
            AuthResult with authentication status and username
        """
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm]
            )
            username = payload.get("sub")
            
            if not username:
                return AuthResult(
                    success=False,
                    error_message="No username in token payload",
                    error_code="INVALID_PAYLOAD"
                )
            
            return AuthResult(success=True, username=username)
            
        except jwt.ExpiredSignatureError:
            logger.warning("Authentication failed: Token expired")
            return AuthResult(
                success=False,
                error_message="Token has expired",
                error_code="TOKEN_EXPIRED"
            )
        except jwt.InvalidTokenError as e:
            logger.warning("Authentication failed: Invalid token - %s", e)
            return AuthResult(
                success=False,
                error_message=f"Invalid token: {e}",
                error_code="INVALID_TOKEN"
            )
        except Exception as e:
            logger.exception("Unexpected error during authentication")
            return AuthResult(
                success=False,
                error_message=f"Authentication error: {e}",
                error_code="AUTH_ERROR"
            )
    
    def extract_token(self, transport_context: Any) -> Optional[str]:
        """
        Extract token from transport context.
        
        Args:
            transport_context: WebSocket or similar connection object
            
        Returns:
            Extracted token or None
        """
        return self._token_extractor.extract(transport_context)


class DefaultTokenExtractor:
    """
    Default token extractor that handles common transport formats.
    
    Supports extraction from:
    - URL query parameters (?token=xxx)
    - Cookie headers (authToken=xxx)
    """
    
    def extract(self, websocket: Any) -> Optional[str]:
        """
        Extract token from WebSocket connection.
        
        Args:
            websocket: WebSocket connection object
            
        Returns:
            Extracted token or None
        """
        # Try query parameter first
        token = self._extract_from_query(websocket)
        if token:
            return token
        
        # Try cookie
        token = self._extract_from_cookie(websocket)
        if token:
            return token
        
        return None
    
    def _extract_from_query(self, websocket: Any) -> Optional[str]:
        """Extract token from URL query parameters."""
        try:
            path = self._get_path(websocket)
            if path and "?" in path:
                _, query = path.split("?", 1)
                params = parse_qs(query)
                tokens = params.get("token", [])
                if tokens:
                    return tokens[0]
        except Exception as e:
            logger.debug("Failed to extract token from query: %s", e)
        return None
    
    def _extract_from_cookie(self, websocket: Any) -> Optional[str]:
        """Extract token from Cookie header."""
        try:
            headers = self._get_headers(websocket)
            cookie_header = headers.get("Cookie", "")
            
            for cookie in cookie_header.split(";"):
                if "authToken=" in cookie:
                    return cookie.split("=", 1)[1].strip()
        except Exception as e:
            logger.debug("Failed to extract token from cookie: %s", e)
        return None
    
    def _get_path(self, websocket: Any) -> Optional[str]:
        """Extract path from WebSocket object."""
        # Try different ways to get path across websockets versions
        request = getattr(websocket, "request", None)
        if request:
            path = getattr(request, "path", None)
            if path:
                return path
        
        return getattr(websocket, "path", None)
    
    def _get_headers(self, websocket: Any) -> Dict[str, str]:
        """Extract headers from WebSocket object."""
        try:
            request = getattr(websocket, "request", None)
            if request and hasattr(request, "headers"):
                return dict(request.headers)
        except Exception:
            pass
        
        # Fallback: try to get headers directly
        try:
            return getattr(websocket, "request", {}).get("headers", {})
        except Exception:
            return {}


class AuthenticationMiddleware:
    """
    Middleware that wraps authentication logic.
    
    Provides a clean interface for authenticating connections
    and handling authentication failures.
    """
    
    def __init__(self, authenticator: Authenticator):
        """
        Initialize middleware.
        
        Args:
            authenticator: Authenticator implementation
        """
        self._authenticator = authenticator
    
    async def authenticate_connection(self, transport_context: Any) -> AuthResult:
        """
        Authenticate a connection.
        
        Args:
            transport_context: Transport-specific context
            
        Returns:
            AuthResult with authentication status
        """
        token = self._authenticator.extract_token(transport_context)
        
        if not token:
            return AuthResult(
                success=False,
                error_message="No authentication token provided",
                error_code="NO_TOKEN"
            )
        
        return await self._authenticator.authenticate(token)
