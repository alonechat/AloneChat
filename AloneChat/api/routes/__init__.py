"""
API routes for AloneChat.
"""

from AloneChat.api.routes import auth, user, chat, friend, message, feedback


def register_routes(app):
    """Register all API routes to the FastAPI app."""
    app.include_router(auth.router)
    app.include_router(user.router)
    app.include_router(chat.router)
    app.include_router(friend.router)
    app.include_router(message.router)
    app.include_router(feedback.router)


__all__ = [
    "register_routes",
    "auth",
    "user",
    "chat",
    "friend",
    "message",
    "feedback",
]
