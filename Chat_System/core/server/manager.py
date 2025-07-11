from dataclasses import dataclass
from typing import Dict
import time

@dataclass
class UserSession:
    user_id: str
    last_active: float

class SessionManager:
    def __init__(self):
        self.sessions: Dict[str, UserSession] = {}

    def add_session(self, user_id: str):
        self.sessions[user_id] = UserSession(
            user_id=user_id,
            last_active=time.time()
        )

    def remove_session(self, user_id: str):
        self.sessions.pop(user_id, None)

    def check_inactive(self, timeout: int = 300):
        current = time.time()
        inactive = [
            uid for uid, session in self.sessions.items()
            if current - session.last_active > timeout
        ]
        for uid in inactive:
            self.remove_session(uid)
        return inactive