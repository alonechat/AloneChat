"""
Persistence service for saving/loading state and logs.
"""
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional


class PersistenceService:
    """Handles persistence of logs and application state."""
    
    def __init__(self, log_dir: Optional[str] = None):
        self._log_dir = log_dir or os.path.join(os.getcwd(), "logs")
        os.makedirs(self._log_dir, exist_ok=True)
        self._state_path = os.path.join(self._log_dir, "gui_state.json")
    
    @property
    def log_dir(self) -> str:
        """Get log directory path."""
        return self._log_dir
    
    def load_state(self) -> Dict[str, Any]:
        """Load application state from disk."""
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    
    def save_state(self, state: Dict[str, Any]) -> bool:
        """Save application state to disk."""
        try:
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False
    
    def log_chat(self, username: str, sender: str, content: str) -> bool:
        """Append chat log to a daily file."""
        try:
            day = datetime.now().strftime("%Y%m%d")
            user = username or "unknown"
            path = os.path.join(self._log_dir, f"chat_{user}_{day}.txt")
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {sender}: {content}\n"
            with open(path, "a", encoding="utf-8") as f:
                f.write(line)
            return True
        except Exception:
            return False
    
    def export_conversation_md(self, username: str, cid: str, 
                               name: str, items: list) -> Optional[str]:
        """Export conversation to Markdown file."""
        try:
            day = datetime.now().strftime("%Y%m%d")
            path = os.path.join(self._log_dir, f"conv_{username}_{cid}_{day}.md")
            lines = [f"# Conversation: {name}", ""]
            for item in items:
                ts = item.get("ts") or ""
                sender = item.get("sender") or ""
                content = item.get("content") or ""
                if item.get("is_system"):
                    lines.append(f"> [{ts}] **System**: {content}")
                else:
                    lines.append(f"- [{ts}] {sender}: {content}")
            with open(path, "w", encoding="utf-8") as f:
                f.write("\n".join(lines) + "\n")
            return path
        except Exception:
            return None
    
    def export_conversation_json(self, username: str, cid: str, 
                                 items: list) -> Optional[str]:
        """Export conversation to JSON file."""
        try:
            day = datetime.now().strftime("%Y%m%d")
            path = os.path.join(self._log_dir, f"conv_{username}_{cid}_{day}.json")
            with open(path, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            return path
        except Exception:
            return None
