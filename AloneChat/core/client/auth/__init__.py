"""
Authentication module for curses client.
Handles login, registration, and session management.
"""

from .auth_flow import AuthFlow, AuthResult

__all__ = ['AuthFlow', 'AuthResult']
