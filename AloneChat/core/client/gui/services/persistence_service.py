"""
Persistence service for saving/loading state and logs.
Uses async file I/O to avoid blocking the event loop.
"""
import asyncio
import json
import os
from datetime import datetime
from typing import Dict, Any, Optional, List

import aiofiles
import aiofiles.os


class PersistenceService:
    """Handles persistence of logs and application state with async I/O."""

    def __init__(self, log_dir: Optional[str] = None):
        self._log_dir = log_dir or os.path.join(os.getcwd(), "logs")
        self._state_path = os.path.join(self._log_dir, "gui_state.json")
        self._write_lock = asyncio.Lock()
        self._log_buffer: Dict[str, List[str]] = {}
        self._buffer_size = 100
        self._initialized = False

    async def _ensure_dir(self) -> None:
        """Ensure log directory exists (async)."""
        if not self._initialized:
            await aiofiles.os.makedirs(self._log_dir, exist_ok=True)
            self._initialized = True

    @property
    def log_dir(self) -> str:
        """Get log directory path."""
        return self._log_dir

    async def load_state(self) -> Dict[str, Any]:
        """Load application state from disk (async)."""
        await self._ensure_dir()
        try:
            async with aiofiles.open(self._state_path, "r", encoding="utf-8") as f:
                content = await f.read()
                return json.loads(content)
        except Exception:
            return {}

    async def save_state(self, state: Dict[str, Any]) -> bool:
        """Save application state to disk (async)."""
        await self._ensure_dir()
        try:
            async with self._write_lock:
                async with aiofiles.open(self._state_path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(state, ensure_ascii=False, indent=2))
            return True
        except Exception:
            return False

    async def log_chat(self, username: str, sender: str, content: str) -> bool:
        """Append chat log to a daily file (async with buffering)."""
        try:
            day = datetime.now().strftime("%Y%m%d")
            user = username or "unknown"
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {sender}: {content}\n"

            buffer_key = f"{user}_{day}"
            if buffer_key not in self._log_buffer:
                self._log_buffer[buffer_key] = []

            self._log_buffer[buffer_key].append(line)

            if len(self._log_buffer[buffer_key]) >= self._buffer_size:
                await self._flush_buffer(buffer_key, user, day)

            return True
        except Exception:
            return False

    async def _flush_buffer(self, buffer_key: str, user: str, day: str) -> None:
        """Flush log buffer to file."""
        if buffer_key not in self._log_buffer or not self._log_buffer[buffer_key]:
            return

        await self._ensure_dir()
        path = os.path.join(self._log_dir, f"chat_{user}_{day}.txt")

        try:
            async with self._write_lock:
                async with aiofiles.open(path, "a", encoding="utf-8") as f:
                    await f.writelines(self._log_buffer[buffer_key])
            self._log_buffer[buffer_key] = []
        except Exception:
            pass

    async def flush_all_buffers(self) -> None:
        """Flush all log buffers to files."""
        for buffer_key in list(self._log_buffer.keys()):
            parts = buffer_key.rsplit("_", 1)
            if len(parts) == 2:
                user, day = parts
                await self._flush_buffer(buffer_key, user, day)

    async def log_chat_immediate(self, username: str, sender: str, content: str) -> bool:
        """Append chat log immediately without buffering (async)."""
        try:
            await self._ensure_dir()
            day = datetime.now().strftime("%Y%m%d")
            user = username or "unknown"
            path = os.path.join(self._log_dir, f"chat_{user}_{day}.txt")
            ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {sender}: {content}\n"

            async with self._write_lock:
                async with aiofiles.open(path, "a", encoding="utf-8") as f:
                    await f.write(line)
            return True
        except Exception:
            return False

    async def export_conversation_md(self, username: str, cid: str,
                                      name: str, items: list) -> Optional[str]:
        """Export conversation to Markdown file (async)."""
        try:
            await self._ensure_dir()
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

            async with self._write_lock:
                async with aiofiles.open(path, "w", encoding="utf-8") as f:
                    await f.write("\n".join(lines) + "\n")
            return path
        except Exception:
            return None

    async def export_conversation_json(self, username: str, cid: str,
                                        items: list) -> Optional[str]:
        """Export conversation to JSON file (async)."""
        try:
            await self._ensure_dir()
            day = datetime.now().strftime("%Y%m%d")
            path = os.path.join(self._log_dir, f"conv_{username}_{cid}_{day}.json")

            async with self._write_lock:
                async with aiofiles.open(path, "w", encoding="utf-8") as f:
                    await f.write(json.dumps(items, ensure_ascii=False, indent=2))
            return path
        except Exception:
            return None

    def load_state_sync(self) -> Dict[str, Any]:
        """Synchronous fallback for loading state."""
        try:
            with open(self._state_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def save_state_sync(self, state: Dict[str, Any]) -> bool:
        """Synchronous fallback for saving state."""
        try:
            os.makedirs(self._log_dir, exist_ok=True)
            with open(self._state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def flush_buffers_sync(self) -> None:
        """Synchronously flush all log buffers to files."""
        for buffer_key, lines in list(self._log_buffer.items()):
            if not lines:
                continue
            parts = buffer_key.rsplit("_", 1)
            if len(parts) == 2:
                user, day = parts
                path = os.path.join(self._log_dir, f"chat_{user}_{day}.txt")
                try:
                    os.makedirs(self._log_dir, exist_ok=True)
                    with open(path, "a", encoding="utf-8") as f:
                        f.writelines(lines)
                    self._log_buffer[buffer_key] = []
                except Exception:
                    pass
