"""
Authentication flow handler for curses client.
Manages login and registration workflows.
"""

from dataclasses import dataclass
from enum import Enum, auto
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from AloneChat.api.client import AloneChatAPIClient
    from AloneChat.core.client.ui.renderer import CursesRenderer


class AuthResult(Enum):
    """Result of an authentication operation."""
    SUCCESS = auto()
    CANCELLED = auto()
    INVALID_CREDENTIALS = auto()
    USERNAME_EXISTS = auto()
    PASSWORD_MISMATCH = auto()
    NETWORK_ERROR = auto()
    UNKNOWN_ERROR = auto()


@dataclass
class AuthSession:
    """Represents an authenticated session."""
    username: str
    token: str

    def is_valid(self) -> bool:
        """Check if session has valid credentials."""
        return bool(self.username and self.token)


class AuthFlow:
    """
    Handles authentication flows (login and registration).
    Provides interactive prompts for user credentials.
    """

    def __init__(self, renderer: 'CursesRenderer', api_client: 'AloneChatAPIClient'):
        """
        Initialize authentication flow.

        Args:
            renderer: UI renderer for displaying prompts
            api_client: API client for authentication requests
        """
        self._renderer = renderer
        self._api_client = api_client
        self._session: Optional[AuthSession] = None

    @property
    def session(self) -> Optional[AuthSession]:
        """Get current authentication session."""
        return self._session

    @property
    def is_authenticated(self) -> bool:
        """Check if user is authenticated."""
        return self._session is not None and self._session.is_valid()

    async def show_auth_menu(self) -> Optional[AuthSession]:
        """
        Display authentication menu and handle user choice.

        Returns:
            AuthSession if authenticated, None otherwise
        """
        while not self.is_authenticated:
            choice = self._show_menu_prompt()

            match choice:
                case "1":
                    result = await self._handle_login()
                    if result == AuthResult.SUCCESS:
                        return self._session

                case "2":
                    result = await self._handle_registration()
                    if result == AuthResult.SUCCESS:
                        self._renderer.show_success("Registration successful! Please login.", 2.0)

                case "q" | "Q":
                    return None

                case _:
                    self._renderer.show_error("Invalid option. Please choose 1, 2, or Q.", 1.5)

        return self._session

    def _show_menu_prompt(self) -> str:
        """
        Display the authentication menu and get user choice.

        Returns:
            User's choice as string
        """
        lines = [
            "=" * 40,
            "         Welcome to AloneChat",
            "=" * 40,
            "",
            "Please select an option:",
            "",
            "  1. Login",
            "  2. Register",
            "",
            "  Q. Quit",
            "",
            "Enter your choice: "
        ]

        self._renderer.draw_prompt(lines)
        return self._renderer.get_input_at_position(len(lines) - 1, 19).strip()

    async def _handle_login(self) -> AuthResult:
        """
        Handle the login flow.

        Returns:
            AuthResult indicating the outcome
        """
        self._renderer.clear()

        # Get username
        self._renderer.draw_prompt(["Username: "])
        username = self._renderer.get_input_at_position(0, 10).strip()

        if not username:
            return AuthResult.CANCELLED

        # Get password
        self._renderer.draw_prompt(["Username: " + username, "Password: "])
        password = self._renderer.get_input_at_position(1, 10, mask=True)

        if not password:
            return AuthResult.CANCELLED

        # Attempt login
        try:
            response = await self._api_client.login(username, password)

            if response.get("success"):
                token = response.get("token")
                if token:
                    self._session = AuthSession(username=username, token=token)
                    self._renderer.show_success("Login successful!", 1.0)
                    return AuthResult.SUCCESS
                else:
                    self._renderer.show_error("Login failed: No token received", 2.0)
                    return AuthResult.UNKNOWN_ERROR
            else:
                message = response.get("message", "Invalid credentials")
                self._renderer.show_error(f"Login failed: {message}", 2.0)
                return AuthResult.INVALID_CREDENTIALS

        except Exception as e:
            self._renderer.show_error(f"Network error: {str(e)}", 2.0)
            return AuthResult.NETWORK_ERROR

    async def _handle_registration(self) -> AuthResult:
        """
        Handle the registration flow.

        Returns:
            AuthResult indicating the outcome
        """
        self._renderer.clear()

        # Get username
        self._renderer.draw_prompt(["Username: "])
        username = self._renderer.get_input_at_position(0, 10).strip()

        if not username:
            return AuthResult.CANCELLED

        # Get password
        self._renderer.draw_prompt(["Username: " + username, "Password: "])
        password = self._renderer.get_input_at_position(1, 10, mask=True)

        if not password:
            return AuthResult.CANCELLED

        # Confirm password
        self._renderer.draw_prompt([
            "Username: " + username,
            "Password: " + "*" * len(password),
            "Confirm password: "
        ])
        confirm_password = self._renderer.get_input_at_position(2, 18, mask=True)

        if password != confirm_password:
            self._renderer.show_error("Passwords do not match!", 2.0)
            return AuthResult.PASSWORD_MISMATCH

        # Attempt registration
        try:
            response = await self._api_client.register(username, password)

            if response.get("success"):
                return AuthResult.SUCCESS
            else:
                message = response.get("message", "Registration failed")
                self._renderer.show_error(f"Registration failed: {message}", 2.0)
                if "exists" in message.lower():
                    return AuthResult.USERNAME_EXISTS
                return AuthResult.UNKNOWN_ERROR

        except Exception as e:
            self._renderer.show_error(f"Network error: {str(e)}", 2.0)
            return AuthResult.NETWORK_ERROR

    async def logout(self) -> bool:
        """
        Logout the current user.

        Returns:
            True if logout was successful, False otherwise
        """
        if not self.is_authenticated:
            return True

        try:
            response = await self._api_client.logout()
            success = response.get("success", False)

            if success:
                self._session = None

            return success

        except Exception:
            return False

    def clear_session(self) -> None:
        """Clear the current session without API call."""
        self._session = None
