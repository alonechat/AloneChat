"""
Async service for managing event loop in GUI applications.

Provides a background event loop for running async operations
without blocking the main GUI thread.
"""

import asyncio
import atexit
import logging
import threading
import weakref
from concurrent.futures import Future
from typing import Any, Callable, Coroutine, Optional, Set

logger = logging.getLogger(__name__)


class AsyncService:
    """
    Manages an async event loop in a background thread.
    
    Features:
        - Thread-safe async execution
        - Graceful shutdown handling
        - Task tracking and cancellation
        - Callback scheduling on main thread
    """
    
    _instances: Set['AsyncService'] = weakref.WeakSet()
    
    def __init__(self):
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._ready = threading.Event()
        self._tasks: Set[asyncio.Task] = set()
        self._lock = threading.Lock()
        
        AsyncService._instances.add(self)
    
    def start(self) -> None:
        """Start the async event loop in a background thread."""
        with self._lock:
            if self._running:
                return
            
            self._ready.clear()
            
            def run_loop():
                self._loop = asyncio.new_event_loop()
                asyncio.set_event_loop(self._loop)
                self._ready.set()
                
                try:
                    self._loop.run_forever()
                finally:
                    self._loop.run_until_complete(self._loop.shutdown_asyncgens())
                    self._loop.close()
            
            self._thread = threading.Thread(
                target=run_loop,
                name="AsyncServiceThread",
                daemon=True
            )
            self._thread.start()
            self._running = True
            
            self._ready.wait(timeout=5.0)
            
            if not self._ready.is_set():
                raise RuntimeError("Failed to start async event loop")
            
            logger.debug("AsyncService started")
    
    def stop(self, timeout: float = 5.0) -> None:
        """Stop the async event loop gracefully."""
        with self._lock:
            if not self._running:
                return
            
            self._running = False
            
            if self._loop and self._loop.is_running():
                future = asyncio.run_coroutine_threadsafe(
                    self._shutdown(),
                    self._loop
                )
                try:
                    future.result(timeout=timeout)
                except Exception as e:
                    logger.warning("Error during async shutdown: %s", e)
                    if self._loop.is_running():
                        self._loop.call_soon_threadsafe(self._loop.stop)
            
            if self._thread and self._thread.is_alive():
                self._thread.join(timeout=timeout)
            
            self._loop = None
            self._thread = None
            self._tasks.clear()
            
            logger.debug("AsyncService stopped")
    
    async def _shutdown(self) -> None:
        """Cancel all tasks and cleanup."""
        current = asyncio.current_task()
        tasks = [t for t in asyncio.all_tasks() if t is not current]
        
        for task in tasks:
            task.cancel()
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        
        self._tasks.clear()
        
        if self._loop:
            self._loop.stop()
    
    def run_async(
        self, 
        coro: Coroutine,
        callback: Optional[Callable[[Any], None]] = None,
        error_callback: Optional[Callable[[Exception], None]] = None
    ) -> Optional[Future]:
        """
        Run a coroutine in the event loop.
        
        Args:
            coro: Coroutine to run
            callback: Optional success callback (called with result)
            error_callback: Optional error callback (called with exception)
            
        Returns:
            concurrent.futures.Future or None if not running
        """
        if not self._loop or not self._running:
            logger.warning("AsyncService not running, cannot execute coroutine")
            return None
        
        async def wrapped():
            try:
                result = await coro
                if callback:
                    callback(result)
                return result
            except Exception as e:
                logger.error("Async task error: %s", e)
                if error_callback:
                    error_callback(e)
                raise
        
        future = asyncio.run_coroutine_threadsafe(wrapped(), self._loop)
        return future
    
    def run_async_soon(
        self,
        callback: Callable[[], Coroutine],
        delay: float = 0
    ) -> None:
        """
        Schedule a coroutine callback to run soon.
        
        Args:
            callback: Async function to call
            delay: Optional delay in seconds
        """
        if not self._loop or not self._running:
            return
        
        async def delayed():
            if delay > 0:
                await asyncio.sleep(delay)
            await callback()
        
        self._loop.call_soon_threadsafe(
            lambda: asyncio.create_task(delayed())
        )
    
    def schedule_on_main(
        self,
        callback: Callable[[], None],
        delay_ms: int = 0
    ) -> None:
        """
        Schedule a callback to run on main thread.
        
        This is a placeholder - actual main thread scheduling
        should be done via tkinter's after() method.
        
        Args:
            callback: Function to call on main thread
            delay_ms: Delay in milliseconds
        """
        callback()
    
    def create_task(
        self,
        coro: Coroutine,
        name: Optional[str] = None
    ) -> Optional[asyncio.Task]:
        """
        Create and track an async task.
        
        Args:
            coro: Coroutine to run as task
            name: Optional task name for debugging
            
        Returns:
            asyncio.Task or None if not running
        """
        if not self._loop or not self._running:
            return None
        
        def task_done(task: asyncio.Task):
            self._tasks.discard(task)
            if not task.cancelled():
                try:
                    exc = task.exception()
                    if exc:
                        logger.error("Task %s failed: %s", name or task, exc)
                except asyncio.CancelledError:
                    pass
        
        future = asyncio.run_coroutine_threadsafe(
            self._create_task_internal(coro, name, task_done),
            self._loop
        )
        
        try:
            return future.result(timeout=1.0)
        except Exception:
            return None
    
    async def _create_task_internal(
        self,
        coro: Coroutine,
        name: Optional[str],
        callback: Callable[[asyncio.Task], None]
    ) -> asyncio.Task:
        """Internal method to create task in loop context."""
        task = asyncio.create_task(coro)
        if name:
            task.set_name(name)
        self._tasks.add(task)
        task.add_done_callback(callback)
        return task
    
    def cancel_all_tasks(self) -> None:
        """Cancel all tracked tasks."""
        if not self._loop:
            return
        
        for task in list(self._tasks):
            task.cancel()
    
    def is_running(self) -> bool:
        """Check if the async service is running."""
        return self._running and self._loop is not None and self._loop.is_running()
    
    @property
    def loop(self) -> Optional[asyncio.AbstractEventLoop]:
        """Get the event loop."""
        return self._loop
    
    @classmethod
    def shutdown_all(cls) -> None:
        """Shutdown all AsyncService instances."""
        for instance in list(cls._instances):
            instance.stop()


@atexit.register
def _cleanup():
    """Cleanup on exit."""
    AsyncService.shutdown_all()


__all__ = ['AsyncService']
