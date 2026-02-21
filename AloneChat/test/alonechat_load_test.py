"""
Load test for AloneChat using AloneChatAPIClient.
Tests the actual client implementation rather than raw HTTP/WebSocket.
Separated into 3 stages: register, login, message.
Plus a single-user high-frequency message test.

Optimized with multiprocessing for high concurrency.
Configuration from config.py (container-aware CPU detection).
"""
import asyncio
import multiprocessing as mp
import time
import uuid
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import dataclass
from typing import List, Tuple, Dict, Any

from AloneChat.api.client import AloneChatAPIClient, close_session
from AloneChat.config import get_container_cpu_count

API_PORT = 8766
HOST = "localhost"

TOTAL_USERS = 300
MESSAGES_PER_USER = 300
MESSAGE_INTERVAL = 0
BATCH_SIZE = TOTAL_USERS
BATCH_DELAY = 0

SINGLE_USER_MESSAGES = 100000
SINGLE_USER_INTERVAL = 0

NUM_PROCESSES = max(1, get_container_cpu_count())
USERS_PER_PROCESS = max(1, TOTAL_USERS // NUM_PROCESSES)


@dataclass
class MessageResult:
    success_count: int = 0
    latencies: List[float] = None
    
    def __post_init__(self):
        if self.latencies is None:
            self.latencies = []


@dataclass
class ProcessResult:
    process_id: int
    success_count: int
    total_count: int
    latencies: List[float]
    error: str = ""


def _create_client() -> AloneChatAPIClient:
    return AloneChatAPIClient(HOST, API_PORT)


def register_user_sync(user_id: int) -> Tuple[bool, str]:
    username = f"user_{user_id}"
    password = "test123"
    
    async def _register():
        client = _create_client()
        try:
            result = await client.register(username, password)
            await close_session()
            return result.get("success", False), ""
        except Exception as e:
            await close_session()
            return False, str(e)
    
    return asyncio.run(_register())


def login_user_sync(user_id: int) -> Tuple[bool, str, str]:
    username = f"user_{user_id}"
    password = "test123"
    
    async def _login():
        client = _create_client()
        try:
            result = await client.login(username, password)
            token = result.get("token", "") if result.get("success") else ""
            await close_session()
            return result.get("success", False), token, ""
        except Exception as e:
            await close_session()
            return False, "", str(e)
    
    return asyncio.run(_login())


def send_messages_sync(user_id: int, token: str, count: int, interval: float) -> MessageResult:
    username = f"user_{user_id}"
    result = MessageResult()
    
    async def _send():
        client = _create_client()
        client.token = token
        nonlocal result
        
        try:
            for i in range(count):
                msg_content = f"hello {i} {uuid.uuid4()}"
                msg_start = time.time()
                send_result = await client.send_message(msg_content)
                msg_latency = time.time() - msg_start
                result.latencies.append(msg_latency)
                
                if send_result.get("success"):
                    result.success_count += 1
                
                if interval > 0:
                    await asyncio.sleep(interval)
            
            await close_session()
        except Exception as e:
            result.latencies.append(0.0)
            await close_session()
    
    asyncio.run(_send())
    return result


def process_worker_register(process_id: int, user_start: int, user_end: int) -> ProcessResult:
    success_count = 0
    total_count = user_end - user_start
    
    for user_id in range(user_start, user_end):
        success, _ = register_user_sync(user_id)
        if success:
            success_count += 1
    
    return ProcessResult(
        process_id=process_id,
        success_count=success_count,
        total_count=total_count,
        latencies=[]
    )


def process_worker_login(process_id: int, user_start: int, user_end: int) -> ProcessResult:
    success_count = 0
    total_count = user_end - user_start
    
    for user_id in range(user_start, user_end):
        success, _, _ = login_user_sync(user_id)
        if success:
            success_count += 1
    
    return ProcessResult(
        process_id=process_id,
        success_count=success_count,
        total_count=total_count,
        latencies=[]
    )


def process_worker_messages(
    process_id: int, 
    user_start: int, 
    user_end: int, 
    messages_per_user: int,
    interval: float
) -> ProcessResult:
    success_count = 0
    total_count = 0
    all_latencies = []
    
    for user_id in range(user_start, user_end):
        success, token, _ = login_user_sync(user_id)
        if not success or not token:
            continue
        
        result = send_messages_sync(user_id, token, messages_per_user, interval)
        success_count += result.success_count
        total_count += messages_per_user
        all_latencies.extend(result.latencies)
    
    return ProcessResult(
        process_id=process_id,
        success_count=success_count,
        total_count=total_count,
        latencies=all_latencies
    )


async def run_stage_multiprocess(
    name: str, 
    worker_func, 
    total_users: int,
    num_processes: int,
    **kwargs
) -> Tuple[float, int, int, List[float]]:
    print(f"=== Stage: {name} (Multiprocess: {num_processes}) ===")
    start = time.time()
    
    users_per_process = max(1, total_users // num_processes)
    processes_to_use = min(num_processes, total_users)
    
    results: List[ProcessResult] = []
    
    with ProcessPoolExecutor(max_workers=processes_to_use) as executor:
        futures = []
        for i in range(processes_to_use):
            user_start = i * users_per_process
            user_end = min(user_start + users_per_process, total_users)
            if user_start >= total_users:
                break
            
            future = executor.submit(
                worker_func, 
                i, 
                user_start, 
                user_end,
                **kwargs
            )
            futures.append(future)
        
        for future in as_completed(futures):
            try:
                result = future.result(timeout=300)
                results.append(result)
            except Exception as e:
                print(f"Process error: {e}")
    
    end = time.time()
    duration = end - start
    
    success_count = sum(r.success_count for r in results)
    total_count = sum(r.total_count for r in results)
    all_latencies = []
    for r in results:
        all_latencies.extend(r.latencies)
    
    print(f"  Duration: {duration:.2f}s, Success: {success_count}/{total_count}")
    return duration, success_count, total_count, all_latencies


async def single_user_high_frequency_test():
    print()
    print("=" * 50)
    print("=== Single User High-Frequency Test ===")
    print(f"Messages to send: {SINGLE_USER_MESSAGES}")
    print()
    
    client = AloneChatAPIClient(HOST, API_PORT)
    username = "single_user_test"
    password = "test123"
    
    print("Registering user...")
    await client.register(username, password)
    
    print("Logging in...")
    login_result = await client.login(username, password)
    if not login_result.get("success"):
        print(f"Login failed: {login_result.get('message')}")
        return
    
    print("Starting high-frequency message test...")
    print()
    
    success_count = 0
    fail_count = 0
    latencies = []
    
    start = time.time()
    
    for i in range(SINGLE_USER_MESSAGES):
        msg_start = time.time()
        msg_content = f"msg_{i}_{uuid.uuid4()}"
        result = await client.send_message(msg_content)
        msg_latency = time.time() - msg_start
        latencies.append(msg_latency)
        
        if result.get("success"):
            success_count += 1
        else:
            fail_count += 1
            
        if SINGLE_USER_INTERVAL > 0:
            await asyncio.sleep(SINGLE_USER_INTERVAL)
            
        if (i + 1) % 1000 == 0:
            print(f"  Progress: {i + 1}/{SINGLE_USER_MESSAGES}")
    
    end = time.time()
    duration = end - start
    
    await close_session()
    
    print()
    print("=== Single User Test Results ===")
    print(f"Total messages: {SINGLE_USER_MESSAGES}")
    print(f"Success: {success_count}")
    print(f"Failed: {fail_count}")
    print(f"Duration: {duration:.2f}s")
    
    if duration > 0:
        throughput = success_count / duration
        print(f"Throughput: {throughput:.2f} msg/s")
        print(f"Avg latency: {sum(latencies) / len(latencies) * 1000:.2f}ms")
        print(f"Min latency: {min(latencies) * 1000:.2f}ms")
        print(f"Max latency: {max(latencies) * 1000:.2f}ms")


async def multi_user_test_multiprocess():
    print(f"Starting multiprocess load test with {TOTAL_USERS} users...")
    print(f"Processes: {NUM_PROCESSES}")
    print(f"Each user sends {MESSAGES_PER_USER} message(s)")
    print()

    print()
    print("====== Starting Multi-User Test (Multiprocess) ======")
    overall_start = time.time()

    reg_duration, reg_success, reg_total, _ = await run_stage_multiprocess(
        "Register", process_worker_register, TOTAL_USERS, NUM_PROCESSES
    )

    login_duration, login_success, login_total, _ = await run_stage_multiprocess(
        "Login", process_worker_login, TOTAL_USERS, NUM_PROCESSES
    )

    msg_duration, msg_success, msg_total, msg_latencies = await run_stage_multiprocess(
        "Messages", 
        process_worker_messages, 
        TOTAL_USERS, 
        NUM_PROCESSES,
        messages_per_user=MESSAGES_PER_USER,
        interval=MESSAGE_INTERVAL
    )

    overall_end = time.time()

    print()
    print("====== Multi-User Test Finished ======")
    print(f"Total users: {TOTAL_USERS}")
    print(f"Processes used: {NUM_PROCESSES}")
    print(f"Messages per user: {MESSAGES_PER_USER}")
    print(f"Overall duration: {overall_end - overall_start:.2f}s")
    print()
    print("=== Register Stats ===")
    print(f"Count: {reg_total}, Success: {reg_success}")
    print(f"Stage duration: {reg_duration:.2f}s")
    if reg_duration > 0:
        print(f"Avg time: {reg_duration * 1000 / reg_total:.2f}ms")
        print(f"Throughput: {reg_total / reg_duration:.2f} req/s")
    print()
    print("=== Login Stats ===")
    print(f"Count: {login_total}, Success: {login_success}")
    print(f"Stage duration: {login_duration:.2f}s")
    if login_duration > 0:
        print(f"Avg time: {login_duration * 1000 / login_total:.2f}ms")
        print(f"Throughput: {login_total / login_duration:.2f} req/s")
    print()
    print("=== Message Stats ===")
    total_msg_attempted = msg_total * MESSAGES_PER_USER
    print(f"Attempted: {total_msg_attempted}, Success: {msg_success}")
    print(f"Stage duration: {msg_duration:.2f}s")
    if msg_duration > 0 and msg_success > 0:
        print(f"Avg send time: {msg_duration * 1000 / msg_success:.2f}ms")
        print(f"Throughput: {msg_success / msg_duration:.2f} msg/s")
    print()
    print("=== Forward Stats (Broadcast) ===")
    online_users = login_success
    forward_per_msg = max(0, online_users - 1)
    total_forwards = msg_success * forward_per_msg
    print(f"Online users: {online_users}")
    print(f"Forward per message: {forward_per_msg}")
    print(f"Total forward count: {total_forwards}")
    if msg_duration > 0 and total_forwards > 0:
        forward_throughput = total_forwards / msg_duration
        avg_forward_time = msg_duration * 1000 / total_forwards
        print(f"Forward throughput: {forward_throughput:.2f} forward/s")
        print(f"Avg forward time: {avg_forward_time:.4f}ms")
    if msg_latencies:
        print()
        print("=== Latency Distribution ===")
        print(f"Total samples: {len(msg_latencies)}")
        print(f"Avg latency: {sum(msg_latencies) / len(msg_latencies) * 1000:.2f}ms")
        sorted_latencies = sorted(msg_latencies)
        p50 = sorted_latencies[len(sorted_latencies) // 2]
        p90 = sorted_latencies[int(len(sorted_latencies) * 0.9)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        print(f"P50 latency: {p50 * 1000:.2f}ms")
        print(f"P90 latency: {p90 * 1000:.2f}ms")
        print(f"P99 latency: {p99 * 1000:.2f}ms")
        print(f"Min latency: {min(msg_latencies) * 1000:.2f}ms")
        print(f"Max latency: {max(msg_latencies) * 1000:.2f}ms")


async def multi_user_test_async():
    print(f"Starting async load test with {TOTAL_USERS} users...")
    print(f"Each user sends {MESSAGES_PER_USER} message(s)")
    print(f"Batch size: {BATCH_SIZE}, Batch delay: {BATCH_DELAY}s")
    print()

    clients = {}
    for i in range(TOTAL_USERS):
        clients[i] = AloneChatAPIClient(HOST, API_PORT)

    print()
    print("====== Starting Multi-User Test (Async) ======")
    overall_start = time.time()

    reg_duration, reg_success, reg_total, _ = await run_stage_async(
        "Register", register_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    login_duration, login_success, login_total, _ = await run_stage_async(
        "Login", login_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    msg_duration, msg_success, msg_total, msg_latencies = await run_stage_async(
        "Messages", send_messages, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    overall_end = time.time()
    await close_session()

    print()
    print("====== Multi-User Test Finished ======")
    print(f"Total users: {TOTAL_USERS}")
    print(f"Messages per user: {MESSAGES_PER_USER}")
    print(f"Overall duration: {overall_end - overall_start:.2f}s")
    print()
    print("=== Register Stats ===")
    print(f"Count: {reg_total}, Success: {reg_success}")
    print(f"Stage duration: {reg_duration:.2f}s")
    if reg_duration > 0:
        print(f"Avg time: {reg_duration * 1000 / reg_total:.2f}ms")
        print(f"Throughput: {reg_total / reg_duration:.2f} req/s")
    print()
    print("=== Login Stats ===")
    print(f"Count: {login_total}, Success: {login_success}")
    print(f"Stage duration: {login_duration:.2f}s")
    if login_duration > 0:
        print(f"Avg time: {login_duration * 1000 / login_total:.2f}ms")
        print(f"Throughput: {login_total / login_duration:.2f} req/s")
    print()
    print("=== Message Stats ===")
    total_msg_attempted = msg_total * MESSAGES_PER_USER
    print(f"Attempted: {total_msg_attempted}, Success: {msg_success}")
    print(f"Stage duration: {msg_duration:.2f}s")
    if msg_duration > 0 and msg_success > 0:
        print(f"Avg send time: {msg_duration * 1000 / msg_success:.2f}ms")
        print(f"Throughput: {msg_success / msg_duration:.2f} msg/s")
    print()
    print("=== Forward Stats (Broadcast) ===")
    online_users = login_success
    forward_per_msg = max(0, online_users - 1)
    total_forwards = msg_success * forward_per_msg
    print(f"Online users: {online_users}")
    print(f"Forward per message: {forward_per_msg}")
    print(f"Total forward count: {total_forwards}")
    if msg_duration > 0 and total_forwards > 0:
        forward_throughput = total_forwards / msg_duration
        avg_forward_time = msg_duration * 1000 / total_forwards
        print(f"Forward throughput: {forward_throughput:.2f} forward/s")
        print(f"Avg forward time: {avg_forward_time:.4f}ms")
    if msg_latencies:
        print()
        print("=== Latency Distribution ===")
        print(f"Total samples: {len(msg_latencies)}")
        print(f"Avg latency: {sum(msg_latencies) / len(msg_latencies) * 1000:.2f}ms")
        sorted_latencies = sorted(msg_latencies)
        p50 = sorted_latencies[len(sorted_latencies) // 2]
        p90 = sorted_latencies[int(len(sorted_latencies) * 0.9)]
        p99 = sorted_latencies[int(len(sorted_latencies) * 0.99)]
        print(f"P50 latency: {p50 * 1000:.2f}ms")
        print(f"P90 latency: {p90 * 1000:.2f}ms")
        print(f"P99 latency: {p99 * 1000:.2f}ms")
        print(f"Min latency: {min(msg_latencies) * 1000:.2f}ms")
        print(f"Max latency: {max(msg_latencies) * 1000:.2f}ms")


async def register_user(user_id: int, clients: dict) -> bool:
    username = f"user_{user_id}"
    password = "test123"
    client = clients.get(user_id)
    if not client:
        return False

    try:
        result = await client.register(username, password)
        return result.get("success", False)
    except Exception as e:
        print(f"{username} register error: {e}")
        return False


async def login_user(user_id: int, clients: dict) -> bool:
    username = f"user_{user_id}"
    password = "test123"
    client = clients.get(user_id)
    if not client:
        return False

    try:
        result = await client.login(username, password)
        return result.get("success", False)
    except Exception as e:
        print(f"{username} login error: {e}")
        return False


async def send_messages(user_id: int, clients: dict) -> MessageResult:
    username = f"user_{user_id}"
    client = clients.get(user_id)
    result = MessageResult()
    
    if not client:
        return result

    try:
        for i in range(MESSAGES_PER_USER):
            msg_content = f"hello {i} {uuid.uuid4()}"
            msg_start = time.time()
            send_result = await client.send_message(msg_content)
            msg_latency = time.time() - msg_start
            result.latencies.append(msg_latency)
            
            if send_result.get("success"):
                result.success_count += 1
            else:
                print(f"{username} send failed: {send_result.get('message')}")
            if MESSAGE_INTERVAL > 0:
                await asyncio.sleep(MESSAGE_INTERVAL)
    except Exception as e:
        print(f"{username} message error: {e}")

    return result


async def run_stage_async(
    name: str, 
    coro_func, 
    clients: dict, 
    total_users: int, 
    batch_size: int, 
    batch_delay: float
) -> Tuple[float, int, int, List[float]]:
    print(f"=== Stage: {name} ===")
    start = time.time()
    success_count = 0
    total_count = 0
    all_latencies: List[float] = []

    for batch_start in range(0, total_users, batch_size):
        batch_end = min(batch_start + batch_size, total_users)
        tasks = [
            asyncio.create_task(coro_func(i, clients))
            for i in range(batch_start, batch_end)
        ]
        results = await asyncio.gather(*tasks)
        for r in results:
            if isinstance(r, bool):
                if r:
                    success_count += 1
            elif isinstance(r, MessageResult):
                success_count += r.success_count
                all_latencies.extend(r.latencies)
            elif isinstance(r, int):
                success_count += r
        total_count += len(results)
        if batch_end < total_users:
            await asyncio.sleep(batch_delay)

    end = time.time()
    duration = end - start
    print(f"  Duration: {duration:.2f}s, Success: {success_count}/{total_count}")
    return duration, success_count, total_count, all_latencies


async def main():
    import sys
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--single":
            await single_user_high_frequency_test()
        elif arg == "--multi":
            await multi_user_test_async()
        elif arg == "--mp":
            await multi_user_test_multiprocess()
        else:
            print(f"Unknown option: {arg}")
    else:
        print("AloneChat Load Test")
        print()
        print("Usage:")
        print("  python alonechat_load_test.py --single   # Single user high-frequency test")
        print("  python alonechat_load_test.py --multi    # Multi-user concurrent test (Async)")
        print("  python alonechat_load_test.py --mp       # Multi-user concurrent test (Multiprocess)")
        print()
        print("Running multiprocess test...")
        print()
        await multi_user_test_multiprocess()


if __name__ == "__main__":
    asyncio.run(main())
