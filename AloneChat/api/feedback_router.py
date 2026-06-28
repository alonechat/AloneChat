"""
Feedback routes extracted from app.py.

Endpoints: POST /api/feedback, GET /api/health.

Auth is handled by the middleware layer (request.state.user is set by
AuthMiddleware). This router only reads the already-resolved user and
delegates persistence / health logic accordingly.
"""

import json
import logging
import os
import time
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from AloneChat.di import container
from AloneChat import __version__

logger = logging.getLogger(__name__)

FEEDBACK_FILE = "feedback.json"

feedback_router = APIRouter(prefix="/api", tags=["feedback"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_user(request: Request) -> str:
    """Extract authenticated user from request state (set by AuthMiddleware)."""
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------

class FeedbackRequest(BaseModel):
    content: str


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@feedback_router.post("/feedback")
async def submit_feedback(feedback: FeedbackRequest, request: Request):
    """Submit user feedback (persisted to local JSON file)."""
    username = _get_user(request)

    feedback_data = {
        "id": str(time.time()),
        "user": username,
        "content": feedback.content,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "pending",
    }

    feedbacks: list = []
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                feedbacks = data.get("feedbacks", [])
        except Exception:
            pass

    feedbacks.append(feedback_data)

    try:
        with open(FEEDBACK_FILE, "w", encoding="utf-8") as f:
            json.dump({"feedbacks": feedbacks}, f, ensure_ascii=False, indent=2)
        return {"success": True, "message": "Feedback submitted"}
    except Exception as e:
        logger.error("Failed to save feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save feedback")


@feedback_router.get("/health")
async def health_check():
    """Health check — verifies the DI container and core services are reachable."""
    try:
        # Touch a lazy-loaded property to confirm wiring is intact
        _ = container.db
        return {
            "status": "healthy",
            "version": __version__,
        }
    except Exception as e:
        logger.error("Health check failed: %s", e)
        raise HTTPException(status_code=503, detail="Service unavailable")
