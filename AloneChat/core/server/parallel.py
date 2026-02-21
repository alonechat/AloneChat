"""
Parallel processing module for AloneChat server.

Provides multi-process + multi-thread parallelization for high-performance computing.

Architecture (Allocate Pooling):
    - AllocatedWorker: Pre-allocated worker with dedicated task queue
    - AllocatedThreadPool: Thread pool with allocated workers
    - AllocatedProcessPool: Process pool with allocated workers
    - TaskDispatcher: Intelligent task routing based on task type
    - SharedState: Process-safe shared state using multiprocessing.Manager

Allocate Pooling vs Traditional Pooling:
    - Traditional: Workers share a single queue, high lock contention
    - Allocate: Each worker has dedicated queue, reduced lock contention
    - Better cache locality and task isolation
"""

import asyncio
import logging
import multiprocessing as mp
import threading
import time
import uuid
from concurrent.futures import Future
from dataclasses import dataclass, field
from enum import Enum, auto
from queue import Empty, Queue
from typing import Any, Callable, Dict, Generic, List, Optional, Tuple, TypeVar, Union

from AloneChat.config import Config

logger = logging.getLogger(__name__)

T = TypeVar('T')
R = TypeVar('R')


class TaskType(Enum):
    CPU_BOUND = auto()
    IO_BOUND = auto()
    DATABASE = auto()
    NETWORK = auto()
    MESSAGE = auto()
    BROADCAST = auto()
    THREAD = auto()


@dataclass
class TaskResult(Generic[T]):
    success: bool = False
    data: Optional[T] = None
    error: Optional[str] = None
    execution_time: float = 0.0
    worker_id: str = ""


@dataclass
class ParallelConfig:
    process_workers: int = field(default_factory=lambda: Config.PROCESS_WORKERS)
    thread_workers: int = field(default_factory=lambda: Config.THREAD_WORKERS)
    io_workers: int = field(default_factory=lambda: Config.IO_WORKERS)
    db_workers: int = field(default_factory=lambda: Config.DB_WORKERS)
    max_tasks_per_child: int = field(default_factory=lambda: Config.MAX_TASKS_PER_CHILD)
    task_timeout: float = field(default_factory=lambda: Config.TASK_TIMEOUT)
    queue_size: int = field(default_factory=lambda: Config.PARALLEL_QUEUE_SIZE)
    
    @classmethod
    def from_config(cls) -> 'ParallelConfig':
        return cls(
            process_workers=Config.PROCESS_WORKERS,
            thread_workers=Config.THREAD_WORKERS,
            io_workers=Config.IO_WORKERS,
            db_workers=Config.DB_WORKERS,
            max_tasks_per_child=Config.MAX_TASKS_PER_CHILD,
            task_timeout=Config.TASK_TIMEOUT,
            queue_size=Config.PARALLEL_QUEUE_SIZE,
        )


class SharedState:
    """Process-safe shared state using multiprocessing.Manager.
    
    Optimized with atomic counters to reduce lock contention.
    """
    
    _COUNTER_SLOTS = 64
    
    def __init__(self, manager: Optional[mp.Manager] = None):
        self._manager = manager or mp.Manager()
        self._dict = self._manager.dict()
        self._list = self._manager.list()
        self._lock = self._manager.Lock()
        self._event = self._manager.Event()
        self._queues: Dict[str, mp.Queue] = {}
        
        self._counters: Dict[str, mp.Value] = {}
        self._counter_lock = threading.Lock()
    
    def get(self, key: str, default: Any = None) -> Any:
        return self._dict.get(key, default)
    
    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._dict[key] = value
    
    def delete(self, key: str) -> bool:
        with self._lock:
            if key in self._dict:
                del self._dict[key]
                return True
            return False
    
    def increment(self, key: str, delta: int = 1) -> int:
        if key not in self._counters:
            with self._counter_lock:
                if key not in self._counters:
                    self._counters[key] = mp.Value('q', 0)
        
        with self._counters[key].get_lock():
            self._counters[key].value += delta
            return self._counters[key].value
    
    def get_counter(self, key: str) -> int:
        if key in self._counters:
            with self._counters[key].get_lock():
                return self._counters[key].value
        return 0
    
    def get_queue(self, name: str) -> mp.Queue:
        if name not in self._queues:
            self._queues[name] = self._manager.Queue()
        return self._queues[name]
    
    def set_event(self) -> None:
        self._event.set()
    
    def clear_event(self) -> None:
        self._event.clear()
    
    def is_event_set(self) -> bool:
        return self._event.is_set()
    
    def wait_event(self, timeout: Optional[float] = None) -> bool:
        return self._event.wait(timeout)
    
    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return dict(self._dict)
    
    def shutdown(self) -> None:
        try:
            self._manager.shutdown()
        except Exception:
            pass


@dataclass
class TaskWrapper:
    """Wrapper for task execution with Future support."""
    task_id: str
    func: Callable
    args: Tuple
    kwargs: Dict
    future: Future
    submit_time: float = field(default_factory=time.time)


class AllocatedThreadWorker:
    """Pre-allocated thread worker with dedicated task queue.
    
    Each worker has its own queue, eliminating lock contention between workers.
    Tasks are distributed by a load balancer in the pool.
    
    Optimized: Uses blocking get() instead of polling to reduce CPU usage.
    """
    
    _STOP_SENTINEL = object()
    
    def __init__(self, worker_id: int, queue_size: int = 1000, name: str = ""):
        self._worker_id = worker_id
        self._name = name or f"worker_{worker_id}"
        self._queue: Queue[Optional[TaskWrapper]] = Queue(maxsize=queue_size)
        self._thread: Optional[threading.Thread] = None
        self._running = False
        self._task_count = 0
        self._total_time = 0.0
        self._lock = threading.Lock()
    
    def start(self) -> None:
        if self._running:
            return
        
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name=self._name)
        self._thread.start()
    
    def _run(self) -> None:
        while self._running:
            try:
                task = self._queue.get()
                
                if task is None or task is self._STOP_SENTINEL:
                    break
                
                self._execute_task(task)
            except Exception as e:
                logger.debug("Worker %s error: %s", self._name, e)
        
        logger.debug("AllocatedThreadWorker %s stopped", self._name)
    
    def _execute_task(self, task: TaskWrapper) -> None:
        start_time = time.time()
        try:
            result = task.func(*task.args, **task.kwargs)
            task.future.set_result(result)
            
            with self._lock:
                self._task_count += 1
                self._total_time += time.time() - start_time
        except Exception as e:
            task.future.set_exception(e)
            logger.debug("Task %s failed in worker %s: %s", task.task_id, self._name, e)
    
    def submit(self, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        future: Future[R] = Future()
        task = TaskWrapper(
            task_id=str(uuid.uuid4())[:8],
            func=func,
            args=args,
            kwargs=kwargs,
            future=future
        )
        
        try:
            self._queue.put_nowait(task)
        except Exception as e:
            future.set_exception(e)
        
        return future
    
    def stop(self) -> None:
        self._running = False
        try:
            self._queue.put_nowait(self._STOP_SENTINEL)
        except Exception:
            pass
    
    def queue_size(self) -> int:
        return self._queue.qsize()
    
    def get_stats(self) -> Dict[str, Any]:
        with self._lock:
            return {
                'worker_id': self._worker_id,
                'name': self._name,
                'task_count': self._task_count,
                'total_time': self._total_time,
                'avg_time': self._total_time / max(1, self._task_count),
                'queue_size': self._queue.qsize(),
            }


class LoadBalanceStrategy(Enum):
    ROUND_ROBIN = auto()
    LEAST_LOADED = auto()


class AllocatedThreadPool:
    """Thread pool using Allocate Pooling pattern.
    
    Workers are pre-allocated with dedicated queues.
    Tasks are distributed using round-robin or least-loaded strategy.
    
    Optimized: Supports configurable load balancing strategy.
    """
    
    def __init__(self, num_workers: int, queue_size: int = 1000, name_prefix: str = "worker",
                 strategy: LoadBalanceStrategy = LoadBalanceStrategy.LEAST_LOADED):
        self._num_workers = num_workers
        self._queue_size = queue_size
        self._name_prefix = name_prefix
        self._strategy = strategy
        self._workers: List[AllocatedThreadWorker] = []
        self._current_index = 0
        self._index_lock = threading.Lock()
        self._running = False
        self._stats_lock = threading.Lock()
        self._total_submitted = 0
    
    def start(self) -> None:
        if self._running:
            return
        
        for i in range(self._num_workers):
            worker = AllocatedThreadWorker(
                worker_id=i,
                queue_size=self._queue_size,
                name=f"{self._name_prefix}_{i}"
            )
            worker.start()
            self._workers.append(worker)
        
        self._running = True
        logger.info(
            "AllocatedThreadPool started: workers=%d, queue_size=%d, prefix=%s, strategy=%s",
            self._num_workers, self._queue_size, self._name_prefix, self._strategy.name
        )
    
    def submit(self, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        if not self._running:
            raise RuntimeError("Pool not started")
        
        worker = self._select_worker()
        future = worker.submit(func, *args, **kwargs)
        
        with self._stats_lock:
            self._total_submitted += 1
        
        return future
    
    def _select_worker(self) -> AllocatedThreadWorker:
        if self._strategy == LoadBalanceStrategy.LEAST_LOADED:
            return self._select_least_loaded()
        return self._select_round_robin()
    
    def _select_round_robin(self) -> AllocatedThreadWorker:
        with self._index_lock:
            worker = self._workers[self._current_index]
            self._current_index = (self._current_index + 1) % self._num_workers
        return worker
    
    def _select_least_loaded(self) -> AllocatedThreadWorker:
        min_size = float('inf')
        selected = self._workers[0]
        
        for worker in self._workers:
            size = worker.queue_size()
            if size < min_size:
                min_size = size
                selected = worker
        
        return selected
    
    def stop(self) -> None:
        if not self._running:
            return
        
        self._running = False
        
        for worker in self._workers:
            worker.stop()
        
        self._workers.clear()
        logger.info("AllocatedThreadPool stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        worker_stats = [w.get_stats() for w in self._workers]
        with self._stats_lock:
            return {
                'num_workers': self._num_workers,
                'total_submitted': self._total_submitted,
                'workers': worker_stats,
            }


def _process_worker_main(worker_id: int, task_queue: mp.Queue, result_queue: mp.Queue, 
                          shutdown_event: mp.Event, name: str):
    """Main function for process workers."""
    logger.debug("ProcessWorker %s started", name)
    
    while not shutdown_event.is_set():
        try:
            task = task_queue.get(timeout=0.5)
            if task is None:
                continue
            
            task_id, func, args, kwargs = task
            start_time = time.time()
            
            try:
                result = func(*args, **kwargs)
                execution_time = time.time() - start_time
                result_queue.put({
                    'task_id': task_id,
                    'success': True,
                    'result': result,
                    'execution_time': execution_time,
                    'worker_id': worker_id
                })
            except Exception as e:
                result_queue.put({
                    'task_id': task_id,
                    'success': False,
                    'error': str(e),
                    'worker_id': worker_id
                })
        except Empty:
            continue
        except Exception as e:
            logger.debug("ProcessWorker %s error: %s", name, e)
    
    logger.debug("ProcessWorker %s stopped", name)


class AllocatedProcessWorker:
    """Pre-allocated process worker with dedicated task queue."""
    
    def __init__(self, worker_id: int, task_queue: mp.Queue, result_queue: mp.Queue,
                 shutdown_event: mp.Event, name: str = "",
                 pending_futures: Optional[Dict[str, Future]] = None,
                 futures_lock: Optional[threading.Lock] = None):
        self._worker_id = worker_id
        self._name = name or f"process_{worker_id}"
        self._task_queue = task_queue
        self._result_queue = result_queue
        self._shutdown_event = shutdown_event
        self._process: Optional[mp.Process] = None
        self._local_futures: Dict[str, Future] = {}
        self._lock = threading.Lock()
        self._task_count = 0
        self._pending_futures = pending_futures
        self._futures_lock = futures_lock
    
    def start(self) -> None:
        self._process = mp.Process(
            target=_process_worker_main,
            args=(self._worker_id, self._task_queue, self._result_queue, 
                  self._shutdown_event, self._name),
            name=self._name,
            daemon=True
        )
        self._process.start()
    
    def submit(self, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        future: Future[R] = Future()
        task_id = str(uuid.uuid4())[:8]
        
        if self._pending_futures is not None and self._futures_lock is not None:
            with self._futures_lock:
                self._pending_futures[task_id] = future
        else:
            with self._lock:
                self._local_futures[task_id] = future
        
        with self._lock:
            self._task_count += 1
        
        try:
            self._task_queue.put((task_id, func, args, kwargs))
        except Exception as e:
            if self._pending_futures is not None and self._futures_lock is not None:
                with self._futures_lock:
                    self._pending_futures.pop(task_id, None)
            else:
                with self._lock:
                    self._local_futures.pop(task_id, None)
            future.set_exception(e)
        
        return future
    
    def stop(self) -> None:
        pass
    
    def queue_size(self) -> int:
        return self._task_queue.qsize()


class AllocatedProcessPool:
    """Process pool using Allocate Pooling pattern.
    
    Optimized with O(1) result lookup using global task mapping.
    """
    
    def __init__(self, num_workers: int, queue_size: int = 1000, name_prefix: str = "process"):
        self._num_workers = num_workers
        self._queue_size = queue_size
        self._name_prefix = name_prefix
        self._workers: List[AllocatedProcessWorker] = []
        self._task_queues: List[mp.Queue] = []
        self._result_queue: Optional[mp.Queue] = None
        self._shutdown_event: Optional[mp.Event] = None
        self._manager: Optional[mp.Manager] = None
        self._current_index = 0
        self._index_lock = threading.Lock()
        self._running = False
        self._result_thread: Optional[threading.Thread] = None
        self._stats_lock = threading.Lock()
        self._total_submitted = 0
        
        self._pending_futures: Dict[str, Future] = {}
        self._futures_lock = threading.Lock()
    
    def start(self) -> None:
        if self._running:
            return
        
        self._manager = mp.Manager()
        self._result_queue = self._manager.Queue()
        self._shutdown_event = self._manager.Event()
        
        for i in range(self._num_workers):
            task_queue = self._manager.Queue(maxsize=self._queue_size)
            self._task_queues.append(task_queue)
            
            worker = AllocatedProcessWorker(
                worker_id=i,
                task_queue=task_queue,
                result_queue=self._result_queue,
                shutdown_event=self._shutdown_event,
                name=f"{self._name_prefix}_{i}",
                pending_futures=self._pending_futures,
                futures_lock=self._futures_lock
            )
            worker.start()
            self._workers.append(worker)
        
        self._result_thread = threading.Thread(
            target=self._collect_results,
            daemon=True,
            name="process_result_collector"
        )
        self._result_thread.start()
        
        self._running = True
        logger.info(
            "AllocatedProcessPool started: workers=%d, queue_size=%d, prefix=%s",
            self._num_workers, self._queue_size, self._name_prefix
        )
    
    def _collect_results(self) -> None:
        while self._running:
            try:
                result = self._result_queue.get(timeout=0.5)
                task_id = result['task_id']
                
                with self._futures_lock:
                    future = self._pending_futures.pop(task_id, None)
                
                if future:
                    if result['success']:
                        future.set_result(result['result'])
                    else:
                        future.set_exception(Exception(result['error']))
            except Empty:
                continue
            except Exception as e:
                logger.debug("Result collector error: %s", e)
    
    def submit(self, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        if not self._running:
            raise RuntimeError("Pool not started")
        
        worker = self._select_worker()
        future = worker.submit(func, *args, **kwargs)
        
        with self._stats_lock:
            self._total_submitted += 1
        
        return future
    
    def _select_worker(self) -> AllocatedProcessWorker:
        with self._index_lock:
            worker = self._workers[self._current_index]
            self._current_index = (self._current_index + 1) % self._num_workers
        return worker
    
    def stop(self) -> None:
        if not self._running:
            return
        
        self._running = False
        
        if self._shutdown_event:
            self._shutdown_event.set()
        
        for worker in self._workers:
            worker.stop()
        
        self._workers.clear()
        self._task_queues.clear()
        
        if self._manager:
            self._manager.shutdown()
            self._manager = None
        
        logger.info("AllocatedProcessPool stopped")
    
    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            return {
                'num_workers': self._num_workers,
                'total_submitted': self._total_submitted,
            }


class WorkerPool:
    """Unified worker pool using Allocate Pooling pattern."""
    
    def __init__(
        self,
        config: Optional[ParallelConfig] = None,
        shared_state: Optional[SharedState] = None
    ):
        self._config = config or ParallelConfig.from_config()
        self._shared_state = shared_state or SharedState()
        
        self._process_pool: Optional[AllocatedProcessPool] = None
        self._thread_pool: Optional[AllocatedThreadPool] = None
        self._io_pool: Optional[AllocatedThreadPool] = None
        self._db_pool: Optional[AllocatedThreadPool] = None
        
        self._async_loop: Optional[asyncio.AbstractEventLoop] = None
        self._async_thread: Optional[threading.Thread] = None
        
        self._running = False
        self._stats = {
            'cpu_tasks': 0,
            'thread_tasks': 0,
            'io_tasks': 0,
            'db_tasks': 0,
            'errors': 0,
        }
        self._stats_lock = threading.Lock()
    
    def start(self) -> None:
        if self._running:
            return
        
        self._process_pool = AllocatedProcessPool(
            num_workers=self._config.process_workers,
            queue_size=self._config.queue_size,
            name_prefix="cpu"
        )
        self._process_pool.start()
        
        self._thread_pool = AllocatedThreadPool(
            num_workers=self._config.thread_workers,
            queue_size=self._config.queue_size,
            name_prefix="worker",
            strategy=LoadBalanceStrategy.LEAST_LOADED
        )
        self._thread_pool.start()
        
        self._io_pool = AllocatedThreadPool(
            num_workers=self._config.io_workers,
            queue_size=self._config.queue_size,
            name_prefix="io",
            strategy=LoadBalanceStrategy.LEAST_LOADED
        )
        self._io_pool.start()
        
        self._db_pool = AllocatedThreadPool(
            num_workers=self._config.db_workers,
            queue_size=self._config.queue_size,
            name_prefix="db",
            strategy=LoadBalanceStrategy.LEAST_LOADED
        )
        self._db_pool.start()
        
        self._start_async_loop()
        
        self._running = True
        logger.info(
            "WorkerPool (Allocate) started: processes=%d, threads=%d, io=%d, db=%d",
            self._config.process_workers,
            self._config.thread_workers,
            self._config.io_workers,
            self._config.db_workers
        )
    
    def _start_async_loop(self) -> None:
        self._async_loop = asyncio.new_event_loop()
        
        def run_loop():
            asyncio.set_event_loop(self._async_loop)
            self._async_loop.run_forever()
        
        self._async_thread = threading.Thread(target=run_loop, daemon=True, name="async_loop")
        self._async_thread.start()
    
    def stop(self) -> None:
        if not self._running:
            return
        
        self._running = False
        
        if self._process_pool:
            self._process_pool.stop()
        if self._thread_pool:
            self._thread_pool.stop()
        if self._io_pool:
            self._io_pool.stop()
        if self._db_pool:
            self._db_pool.stop()
        
        if self._async_loop and self._async_loop.is_running():
            self._async_loop.call_soon_threadsafe(self._async_loop.stop)
        
        logger.info("WorkerPool stopped")
    
    def submit_process(self, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        if not self._running:
            raise RuntimeError("WorkerPool not started")
        
        self._increment_stat('cpu_tasks')
        return self._process_pool.submit(func, *args, **kwargs)
    
    def submit_thread(self, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        if not self._running:
            raise RuntimeError("WorkerPool not started")
        
        self._increment_stat('thread_tasks')
        return self._thread_pool.submit(func, *args, **kwargs)
    
    def submit_io(self, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        if not self._running:
            raise RuntimeError("WorkerPool not started")
        
        self._increment_stat('io_tasks')
        return self._io_pool.submit(func, *args, **kwargs)
    
    def submit_db(self, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        if not self._running:
            raise RuntimeError("WorkerPool not started")
        
        self._increment_stat('db_tasks')
        return self._db_pool.submit(func, *args, **kwargs)
    
    def submit_async(self, coro) -> Future:
        if not self._running:
            raise RuntimeError("WorkerPool not started")
        
        if not self._async_loop:
            raise RuntimeError("Async loop not started")
        
        return asyncio.run_coroutine_threadsafe(coro, self._async_loop)
    
    def submit_by_type(self, task_type: TaskType, func: Callable[..., R], *args, **kwargs) -> Future[R]:
        pool_map = {
            TaskType.CPU_BOUND: self.submit_process,
            TaskType.IO_BOUND: self.submit_io,
            TaskType.DATABASE: self.submit_db,
            TaskType.NETWORK: self.submit_io,
            TaskType.MESSAGE: self.submit_thread,
            TaskType.BROADCAST: self.submit_thread,
            TaskType.THREAD: self.submit_thread,
        }
        
        submitter = pool_map.get(task_type, self.submit_thread)
        return submitter(func, *args, **kwargs)
    
    def _increment_stat(self, key: str) -> None:
        with self._stats_lock:
            self._stats[key] = self._stats.get(key, 0) + 1
    
    def get_stats(self) -> Dict[str, Any]:
        with self._stats_lock:
            stats = dict(self._stats)
        
        if self._thread_pool:
            stats['thread_pool'] = self._thread_pool.get_stats()
        if self._io_pool:
            stats['io_pool'] = self._io_pool.get_stats()
        if self._db_pool:
            stats['db_pool'] = self._db_pool.get_stats()
        if self._process_pool:
            stats['process_pool'] = self._process_pool.get_stats()
        
        return stats
    
    @property
    def shared_state(self) -> SharedState:
        return self._shared_state
    
    @property
    def is_running(self) -> bool:
        return self._running


class TaskDispatcher:
    """Intelligent task dispatcher with load balancing."""
    
    def __init__(self, pool: Optional[WorkerPool] = None):
        self._pool = pool or WorkerPool()
        self._task_queues: Dict[TaskType, List[Callable]] = {
            TaskType.CPU_BOUND: [],
            TaskType.IO_BOUND: [],
            TaskType.DATABASE: [],
            TaskType.NETWORK: [],
            TaskType.MESSAGE: [],
            TaskType.BROADCAST: [],
        }
        self._priority_map = {
            TaskType.MESSAGE: 1,
            TaskType.BROADCAST: 2,
            TaskType.NETWORK: 3,
            TaskType.IO_BOUND: 4,
            TaskType.DATABASE: 5,
            TaskType.CPU_BOUND: 6,
        }
    
    def start(self) -> None:
        self._pool.start()
    
    def stop(self) -> None:
        self._pool.stop()
    
    def dispatch(
        self,
        func: Callable[..., R],
        *args,
        task_type: TaskType = TaskType.THREAD,
        priority: Optional[int] = None,
        **kwargs
    ) -> Future[R]:
        return self._pool.submit_by_type(task_type, func, *args, **kwargs)
    
    def dispatch_batch(
        self,
        tasks: List[Tuple[Callable, Tuple, Dict, TaskType]]
    ) -> List[Future]:
        futures = []
        for func, args, kwargs, task_type in tasks:
            future = self._pool.submit_by_type(task_type, func, *args, **kwargs)
            futures.append(future)
        return futures
    
    async def dispatch_async(
        self,
        func: Callable[..., R],
        *args,
        task_type: TaskType = TaskType.THREAD,
        **kwargs
    ) -> R:
        loop = asyncio.get_event_loop()
        future = self._pool.submit_by_type(task_type, func, *args, **kwargs)
        return await loop.run_in_executor(None, future.result)
    
    def dispatch_coroutine(self, coro) -> Future:
        return self._pool.submit_async(coro)
    
    @property
    def pool(self) -> WorkerPool:
        return self._pool
    
    @property
    def shared_state(self) -> SharedState:
        return self._pool.shared_state


_parallel_manager: Optional['ParallelManager'] = None


class ParallelManager:
    """Central manager for all parallel processing."""
    
    def __init__(self, config: Optional[ParallelConfig] = None):
        self._config = config or ParallelConfig.from_config()
        self._shared_state = SharedState()
        self._worker_pool = WorkerPool(self._config, self._shared_state)
        self._task_dispatcher = TaskDispatcher(self._worker_pool)
        self._initialized = False
    
    def initialize(self) -> None:
        if self._initialized:
            return
        
        self._worker_pool.start()
        self._initialized = True
        logger.info("ParallelManager initialized (Allocate Pooling)")
    
    def shutdown(self) -> None:
        if not self._initialized:
            return
        
        self._worker_pool.stop()
        self._shared_state.shutdown()
        self._initialized = False
        logger.info("ParallelManager shutdown")
    
    @property
    def pool(self) -> WorkerPool:
        return self._worker_pool
    
    @property
    def dispatcher(self) -> TaskDispatcher:
        return self._task_dispatcher
    
    @property
    def shared_state(self) -> SharedState:
        return self._shared_state
    
    @property
    def config(self) -> ParallelConfig:
        return self._config
    
    @property
    def is_initialized(self) -> bool:
        return self._initialized


def get_parallel_manager() -> ParallelManager:
    global _parallel_manager
    if _parallel_manager is None:
        _parallel_manager = ParallelManager()
    return _parallel_manager


def initialize_parallel() -> ParallelManager:
    manager = get_parallel_manager()
    manager.initialize()
    return manager


def shutdown_parallel() -> None:
    global _parallel_manager
    if _parallel_manager is not None:
        _parallel_manager.shutdown()
        _parallel_manager = None
