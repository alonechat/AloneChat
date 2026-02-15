"""
Async service for handling API calls and event loop.
"""
import asyncio
import threading
from typing import Optional


class AsyncService:
    """Manages async event loop in a background thread."""
    
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._ready = threading.Event()
    
    def start(self) -> None:
        """Start the async event loop in a background thread."""
        if self._running:
            return
        
        self._ready.clear()
        
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._ready.set()
            self._loop.run_forever()
        
        self._thread = threading.Thread(target=run_loop, daemon=False)
        self._thread.start()
        self._running = True
        
        self._ready.wait()
    
    def stop(self, timeout: float = 2.0) -> None:
        """Stop the async event loop gracefully."""
        if not self._running:
            return
        
        try:
            if self._loop:
                fut = asyncio.run_coroutine_threadsafe(self._shutdown_loop(), self._loop)
                try:
                    fut.result(timeout=timeout)
                except Exception:
                    try:
                        self._loop.call_soon_threadsafe(self._loop.stop)
                    except Exception:
                        pass
        except Exception:
            pass
        
        try:
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)
        except Exception:
            pass
        
        self._running = False
        self._loop = None
        self._thread = None
        self._ready.clear()
    
    async def _shutdown_loop(self) -> None:
        """Cancel all tasks and stop the loop."""
        try:
            current = asyncio.current_task()
            tasks = [t for t in asyncio.all_tasks() if t is not current]
            for t in tasks:
                t.cancel()
            if tasks:
                await asyncio.gather(*tasks, return_exceptions=True)
        finally:
            if self._loop:
                self._loop.stop()
    
    def run_async(self, coro) -> Optional[asyncio.Future]:
        """Run a coroutine in the event loop."""
        if not self._loop or not self._running:
            return None
        return asyncio.run_coroutine_threadsafe(coro, self._loop)
    
    def is_running(self) -> bool:
        """Check if the async service is running."""
        return self._running and self._loop is not None
