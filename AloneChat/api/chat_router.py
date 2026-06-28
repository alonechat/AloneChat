"""
Chat routes extracted from app.py.

Endpoints:
    POST /api/chat/send       — send a private message
    GET  /api/chat/history    — chat history with another user
    POST /api/chat/recv       — poll pending message queue (replaces /api/chat/pending)
    POST /api/chat/recv/clear — clear pending message queue
    GET  /api/chat/sessions   — list recent chat sessions
"""

import asyncio
import json
import logging

from fastapi import APIRouter, HTTPException, Query, Request
from pydantic import BaseModel, Field

from AloneChat.message.protocol import Message, MessageType
from AloneChat.di import container

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------

chat_router = APIRouter(prefix="/api/chat", tags=["chat"])

# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------


def _get_user(request: Request) -> str:
    """Extract the authenticated username from the request state.

    Relies on the AuthMiddleware (installed on the FastAPI app) to validate
    the JWT and set ``request.state.user`` before this handler runs.
    """
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------


class SendMessageRequest(BaseModel):
    recipient: str = Field(..., min_length=1, description="Target username")
    content: str = Field(..., min_length=1, description="Message body")


# ---------------------------------------------------------------------------
# POST /api/chat/send
# ---------------------------------------------------------------------------


@chat_router.post("/send")
async def send_message(req: SendMessageRequest, request: Request):
    """Send a private message to another user."""
    sender = _get_user(request)

    content = req.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    if sender == req.recipient:
        raise HTTPException(status_code=400, detail="Cannot message yourself")

    # Deliver + persist via message service (live WS or queue fallback + DB).
    # Chat history is maintained by ChatService via get_history (reads from DB).
    await container.message_service.send_message(
        sender=sender,
        recipient=req.recipient,
        content=content,
        msg_type=MessageType.TEXT,
    )

    await container.chat_service.record_message(sender, req.recipient, content)

    return {"success": True, "message": "Message sent"}


# ---------------------------------------------------------------------------
# GET /api/chat/history
# ---------------------------------------------------------------------------


@chat_router.get("/history")
async def get_history(
    request: Request,
    other_user: str = Query(..., min_length=1, description="The other participant's username"),
    limit: int = Query(50, ge=1, le=200, description="Max messages to return"),
):
    """Return the message history between the current user and *other_user*."""
    current_user = _get_user(request)

    history = await container.chat_service.get_history(current_user, other_user, limit)
    return {"success": True, "messages": history, "count": len(history)}


# ---------------------------------------------------------------------------
# POST /api/chat/recv  (replaces old /api/chat/pending)
# ---------------------------------------------------------------------------


@chat_router.post("/recv")
async def recv_messages(request: Request):
    """Poll the pending message queue for the current user.

    Uses POST for idempotency (no side-effects on repeat calls).  Each call
    drains the queue — messages are delivered exactly once.  Returns an empty
    list when no messages are pending.
    """
    current_user = _get_user(request)

    pending = container.message_service.get_pending(current_user)
    messages = []
    for raw in pending:
        try:
            msg = Message.deserialize(raw)
            messages.append({
                "sender": msg.sender,
                "content": msg.content,
                "type": msg.type.value,
            })
        except Exception:
            logger.warning("Failed to deserialize pending message for %s", current_user)

    return {"success": True, "messages": messages, "count": len(messages)}


# ---------------------------------------------------------------------------
# POST /api/chat/recv/clear
# ---------------------------------------------------------------------------


@chat_router.post("/recv/clear")
async def clear_recv_messages(request: Request):
    """Discard all pending messages for the current user."""
    current_user = _get_user(request)

    count = container.message_service.clear_pending(current_user)
    return {"success": True, "cleared_count": count}


# ---------------------------------------------------------------------------
# GET /api/chat/sessions
# ---------------------------------------------------------------------------


@chat_router.get("/sessions")
async def get_sessions(
    request: Request,
    limit: int = Query(10, ge=1, le=100, description="Max sessions to return"),
):
    """Return the most recent chat sessions for the current user."""
    current_user = _get_user(request)

    sessions = await container.chat_service.get_recent_chats(current_user, limit)
    return {"success": True, "sessions": sessions, "count": len(sessions)}
