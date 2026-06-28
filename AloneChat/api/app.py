"""
AloneChat API - HTTP/WebSocket application.

This module creates the FastAPI application, configures middleware, mounts
all routers, and registers the WebSocket endpoint. All business logic is
delegated to service classes accessed through the DI container.
"""

import logging
from contextlib import asynccontextmanager

import asyncio
import json
import logging

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import StreamingResponse

from AloneChat import __version__
from AloneChat.api.middleware import AuthMiddleware, _get_token_user
from AloneChat.api.auth_router import auth_router
from AloneChat.api.chat_router import chat_router
from AloneChat.api.friend_router import friend_router
from AloneChat.api.user_router import user_router
from AloneChat.api.feedback_router import feedback_router
from AloneChat.api.ws_handler import router as ws_router
from AloneChat.di import container
from AloneChat.message.protocol import Message, MessageType

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle.

    On startup the DI container wires all services lazily. Touching
    ``container.db`` ensures the database connection is ready before the
    first request arrives.

    On shutdown the container flushes status buffers, closes connections,
    and drops all cached instances.
    """
    logger.info("AloneChat API v%s starting up", __version__)
    # Ensure services are wired before the first request.
    _ = container.db
    yield
    logger.info("AloneChat API shutting down")
    container.shutdown()


app = FastAPI(
    title="AloneChat API",
    version=__version__,
    description="AloneChat API Server",
    lifespan=lifespan,
)

# ---------------------------------------------------------------------------
# Middleware (order matters: CORS → GZip → Auth)
# ---------------------------------------------------------------------------

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.add_middleware(GZipMiddleware, minimum_size=1000)

app.add_middleware(AuthMiddleware)

# ---------------------------------------------------------------------------
# SSE endpoint (top-level for backward compatibility)
# ---------------------------------------------------------------------------


@app.get("/events")
async def message_events(request: Request):
    """Server-Sent Events stream for real-time message delivery."""
    username = _get_token_user(request)
    if not username:
        from fastapi import HTTPException
        raise HTTPException(status_code=401, detail="Not authenticated")

    queue = container.message_service.get_queue(username)

    # Drain any undelivered messages from DB on connect (handles
    # messages sent while user was offline, and recovers after restart).
    undelivered = container.message_repo.get_undelivered_messages(username)
    if undelivered:
        logger.info("[SSE] Replaying %d offline messages for %s", len(undelivered), username)
        for row in undelivered:
            msg = Message(
                type=MessageType.TEXT,
                sender=row["sender"],
                content=row["content"],
                target=username,
            )
            queue.put_nowait(msg.serialize())
        container.message_repo.mark_delivered(username)

    async def event_generator():
        yield ": connected\n\n"
        try:
            while True:
                if await request.is_disconnected():
                    break
                msg_data = await queue.get(timeout=30.0)
                if msg_data:
                    try:
                        msg = Message.deserialize(msg_data)
                        data = json.dumps({
                            "sender": msg.sender,
                            "content": msg.content,
                            "type": msg.type.value,
                        })
                        yield f"data: {data}\n\n"
                    except Exception:
                        yield ": heartbeat\n\n"
                else:
                    yield ": heartbeat\n\n"
        except asyncio.CancelledError:
            pass

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
    )

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(friend_router)
app.include_router(user_router)
app.include_router(feedback_router)
app.include_router(ws_router)
