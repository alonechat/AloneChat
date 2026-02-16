"""
Load test for AloneChat using AloneChatAPIClient.
Tests the actual client implementation rather than raw HTTP/WebSocket.
Separated into 3 stages: register, login, message.
Plus a single-user high-frequency message test.
"""
import asyncio
import os
import time
import uuid

# Disable proxy for localhost connections
os.environ.pop('HTTP_PROXY', None)
os.environ.pop('HTTPS_PROXY', None)
os.environ.pop('http_proxy', None)
os.environ.pop('https_proxy', None)
os.environ.pop('ALL_PROXY', None)
os.environ.pop('all_proxy', None)

import websockets

from AloneChat.api.client import AloneChatAPIClient, close_session
from AloneChat.core.client.utils import DEFAULT_API_PORT

WS_PORT = 8765
API_PORT = 8766
HOST = "localhost"

TOTAL_USERS = 200
MESSAGES_PER_USER = 200
MESSAGE_INTERVAL = 0
BATCH_SIZE = 50
BATCH_DELAY = 0

SINGLE_USER_MESSAGES = 10000
SINGLE_USER_INTERVAL = 0


async def register_user(user_id: int, clients: dict) -> bool:
    """
    Stage 1: Register a user.
    
    Returns:
        True if registration successful or user already exists
    """
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
    """
    Stage 2: Login a user.
    
    Returns:
        True if login successful
    """
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


async def send_messages(user_id: int, clients: dict) -> int:
    """
    Stage 3: Send messages for a user.
    
    Returns:
        Number of successful messages
    """
    username = f"user_{user_id}"
    client = clients.get(user_id)
    if not client:
        return 0

    success_count = 0
    try:
        ws_url = client.get_ws_url()
        async with websockets.connect(ws_url,proxy=None) as ws:
            for i in range(MESSAGES_PER_USER):
                msg_content = f"hello {i} {uuid.uuid4()}"
                result = await client.send_message(msg_content)
                if result.get("success"):
                    success_count += 1
                else:
                    print(f"{username} send failed: {result.get('message')}")
                if MESSAGE_INTERVAL > 0:
                    await asyncio.sleep(MESSAGE_INTERVAL)
    except Exception as e:
        print(f"{username} message error: {e}")

    return success_count


async def create_clients(count: int) -> dict:
    """
    Pre-create client instances (not counted in test time).
    """
    print(f"Pre-creating {count} client instances...")
    clients = {}
    for i in range(count):
        clients[i] = AloneChatAPIClient(HOST, API_PORT)
    print("Client instances created.")
    return clients


async def run_stage(name: str, coro_func, clients: dict, total_users: int, batch_size: int, batch_delay: float):
    """
    Run a stage with batching and return stats.
    
    Returns:
        Tuple of (stage_duration, success_count, total_count)
        For message stage, success_count is total successful messages.
    """
    print(f"=== Stage: {name} ===")
    start = time.time()
    success_count = 0
    total_count = 0

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
            elif isinstance(r, int):
                success_count += r
        total_count += len(results)
        if batch_end < total_users:
            await asyncio.sleep(batch_delay)

    end = time.time()
    duration = end - start
    print(f"  Duration: {duration:.2f}s, Success: {success_count}/{total_count}")
    return duration, success_count, total_count


async def single_user_high_frequency_test():
    """
    Single user high-frequency message test.
    Tests message throughput for a single connection.
    """
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
    
    ws_url = client.get_ws_url()
    
    try:
        async with websockets.connect(ws_url,proxy=None) as ws:
            print(f"WebSocket connected, sending {SINGLE_USER_MESSAGES} messages...")
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
                    
                if (i + 1) % 100 == 0:
                    print(f"  Progress: {i + 1}/{SINGLE_USER_MESSAGES}")
            
            end = time.time()
            duration = end - start
            
    except Exception as e:
        print(f"Error: {e}")
        return
    
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
    
    await close_session()


async def multi_user_test():
    """
    Multi-user concurrent test.
    """
    print(f"Starting load test with {TOTAL_USERS} users...")
    print(f"Each user sends {MESSAGES_PER_USER} message(s)")
    print(f"Batch size: {BATCH_SIZE}, Batch delay: {BATCH_DELAY}s")
    print()

    clients = await create_clients(TOTAL_USERS)

    print()
    print("====== Starting Multi-User Test ======")
    overall_start = time.time()

    reg_duration, reg_success, reg_total = await run_stage(
        "Register", register_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    login_duration, login_success, login_total = await run_stage(
        "Login", login_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    msg_duration, msg_success, msg_total = await run_stage(
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
    if msg_duration > 0:
        print(f"Avg time: {msg_duration * 1000 / msg_success:.2f}ms" if msg_success > 0 else "Avg time: N/A")
        print(f"Throughput: {msg_success / msg_duration:.2f} msg/s")


async def main():
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "--single":
        await single_user_high_frequency_test()
    elif len(sys.argv) > 1 and sys.argv[1] == "--multi":
        await multi_user_test()
    else:
        print("AloneChat Load Test")
        print()
        print("Usage:")
        print("  python alonechat_load_test.py --single   # Single user high-frequency test")
        print("  python alonechat_load_test.py --multi    # Multi-user concurrent test")
        print()
        print("Running both tests...")
        print()
        await single_user_high_frequency_test()
        print()
        await multi_user_test()


if __name__ == "__main__":
    asyncio.run(main())
