"""
Feedback routes for AloneChat API.
"""

import datetime
import json
import logging
import os
import time
from typing import List

from fastapi import APIRouter, HTTPException, Request

from AloneChat.api.models import FeedbackRequest


logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["feedback"])

FEEDBACK_FILE = "feedback.json"


def _get_user(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    return user


def _load_feedback() -> List[dict]:
    feedbacks = []
    if os.path.exists(FEEDBACK_FILE):
        try:
            with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
                feedbacks = data.get('feedbacks', [])
        except Exception:
            pass
    return feedbacks


def _save_feedback(feedbacks: List[dict]) -> None:
    with open(FEEDBACK_FILE, 'w', encoding='utf-8') as f:
        json.dump({'feedbacks': feedbacks}, f, ensure_ascii=False, indent=2)


@router.post("/feedback/submit")
async def submit_feedback(feedback: FeedbackRequest, request: Request):
    username = _get_user(request)

    feedback_data = {
        "id": str(time.time()),
        "user": username,
        "content": feedback.content,
        "timestamp": datetime.datetime.now().isoformat(),
        "status": "pending"
    }

    feedbacks = _load_feedback()
    feedbacks.append(feedback_data)

    try:
        _save_feedback(feedbacks)
        return {"success": True, "message": "Feedback submitted"}
    except Exception as e:
        logger.error("Failed to save feedback: %s", e)
        raise HTTPException(status_code=500, detail="Failed to save feedback")


@router.get("/feedback/my-feedback")
async def get_my_feedback(request: Request):
    username = _get_user(request)

    if not os.path.exists(FEEDBACK_FILE):
        return {"success": True, "feedbacks": []}

    try:
        with open(FEEDBACK_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            feedbacks = [fb for fb in data.get('feedbacks', []) if fb.get("user") == username]
            feedbacks.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
            return {"success": True, "feedbacks": feedbacks}
    except Exception:
        return {"success": True, "feedbacks": []}
