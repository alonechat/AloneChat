"""Lightweight social graph persistence for AloneChat.

This module stores:
- friendships (accepted)
- friend requests (pending/accepted/rejected)

Persistence format: JSON files in project root (next to user_credentials.json),
so it works without databases and supports Windows/Linux/macOS.

Note: This is a stepping stone. You can later replace this with a DB-backed repo layer.
"""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, asdict
from typing import Dict, List, Optional, Tuple

from AloneChat.api.routes_base import load_user_credentials

DEFAULT_DIR = os.getcwd()
FRIENDS_FILE = os.path.join(DEFAULT_DIR, "friendships.json")
REQUESTS_FILE = os.path.join(DEFAULT_DIR, "friend_requests.json")


def _read_json(path: str, default):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def _write_json(path: str, obj) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def _now() -> float:
    return time.time()


@dataclass
class FriendRequest:
    from_user: str
    to_user: str
    message: str = ""
    status: str = "pending"  # pending|accepted|rejected|canceled
    created_at: float = 0.0
    acted_at: float = 0.0

    def to_dict(self) -> Dict:
        d = asdict(self)
        return d


class SocialStore:
    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = base_dir or DEFAULT_DIR
        self.friends_path = os.path.join(self.base_dir, os.path.basename(FRIENDS_FILE))
        self.requests_path = os.path.join(self.base_dir, os.path.basename(REQUESTS_FILE))

    # ---- friendships ----
    def _load_friends(self) -> Dict[str, List[str]]:
        return _read_json(self.friends_path, {})

    def _save_friends(self, data: Dict[str, List[str]]) -> None:
        _write_json(self.friends_path, data)

    def are_friends(self, a: str, b: str) -> bool:
        data = self._load_friends()
        return b in set(data.get(a, []))

    def add_friendship(self, a: str, b: str) -> None:
        data = self._load_friends()
        data.setdefault(a, [])
        data.setdefault(b, [])
        if b not in data[a]:
            data[a].append(b)
        if a not in data[b]:
            data[b].append(a)
        data[a] = sorted(set(data[a]))
        data[b] = sorted(set(data[b]))
        self._save_friends(data)

    def list_friends(self, user: str) -> List[str]:
        data = self._load_friends()
        return sorted(set(data.get(user, [])))

    # ---- requests ----
    def _load_requests(self) -> List[Dict]:
        return _read_json(self.requests_path, [])

    def _save_requests(self, data: List[Dict]) -> None:
        _write_json(self.requests_path, data)

    def _find_request(self, data: List[Dict], from_user: str, to_user: str, status: Optional[str] = None) -> Optional[Dict]:
        for r in data:
            if r.get("from_user") == from_user and r.get("to_user") == to_user:
                if status is None or r.get("status") == status:
                    return r
        return None

    def send_request(self, from_user: str, to_user: str, message: str = "") -> Tuple[bool, str]:
        if from_user == to_user:
            return False, "Cannot add yourself."
        users = load_user_credentials()
        if to_user not in users:
            return False, "User does not exist."
        if self.are_friends(from_user, to_user):
            return False, "Already friends."

        data = self._load_requests()
        # existing pending either direction
        if self._find_request(data, from_user, to_user, "pending"):
            return False, "Request already sent."
        if self._find_request(data, to_user, from_user, "pending"):
            return False, "You have a pending request from this user."

        fr = FriendRequest(
            from_user=from_user,
            to_user=to_user,
            message=message or "",
            status="pending",
            created_at=_now(),
            acted_at=0.0,
        )
        data.append(fr.to_dict())
        self._save_requests(data)
        return True, "Request sent."

    def incoming_requests(self, user: str) -> List[Dict]:
        data = self._load_requests()
        return sorted(
            [r for r in data if r.get("to_user") == user and r.get("status") == "pending"],
            key=lambda r: r.get("created_at", 0),
            reverse=True
        )

    def sent_requests(self, user: str) -> List[Dict]:
        data = self._load_requests()
        return sorted(
            [r for r in data if r.get("from_user") == user],
            key=lambda r: r.get("created_at", 0),
            reverse=True
        )

    def respond(self, to_user: str, from_user: str, accept: bool) -> Tuple[bool, str]:
        data = self._load_requests()
        r = self._find_request(data, from_user, to_user, "pending")
        if not r:
            return False, "No pending request."
        r["status"] = "accepted" if accept else "rejected"
        r["acted_at"] = _now()
        self._save_requests(data)
        if accept:
            self.add_friendship(from_user, to_user)
        return True, "Accepted." if accept else "Rejected."

    def relation_status(self, me: str, other: str) -> str:
        if me == other:
            return "self"
        if self.are_friends(me, other):
            return "friend"
        data = self._load_requests()
        if self._find_request(data, me, other, "pending"):
            return "requested_by_me"
        if self._find_request(data, other, me, "pending"):
            return "requested_to_me"
        return "none"
