"""
Load test for AloneChat using AloneChatAPIClient.
Tests the actual client implementation rather than raw HTTP/WebSocket.
Separated into 3 stages: register, login, message.
Plus a single-user high-frequency message test.

Supports comparison between HTTP and WebSocket message sending.
"""
import asyncio
import json
import time
import uuid
from dataclasses import dataclass
from typing import List, Tuple

import websockets

from AloneChat.api.client import AloneChatAPIClient, close_session
from AloneChat.core.message import Message, MessageType

API_PORT = 8766
HOST = "localhost"

TOTAL_USERS = 200
MESSAGES_PER_USER = 200
MESSAGE_INTERVAL = 0
BATCH_SIZE = TOTAL_USERS # 50
BATCH_DELAY = 0

SINGLE_USER_MESSAGES = 100000
SINGLE_USER_INTERVAL = 0


@dataclass
class MessageResult:
    success_count: int = 0
    latencies: List[float] = None
    
    def __post_init__(self):
        if self.latencies is None:
            self.latencies = []


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
        ws_url = client.get_ws_url()
        async with websockets.connect(ws_url, proxy=None) as ws:
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


async def send_messages_ws(user_id: int, clients: dict) -> MessageResult:
    username = f"user_{user_id}"
    client = clients.get(user_id)
    result = MessageResult()
    
    if not client:
        return result

    try:
        ws_url = client.get_ws_url()
        async with websockets.connect(ws_url, proxy=None) as ws:
            for i in range(MESSAGES_PER_USER):
                msg_content = f"hello {i} {uuid.uuid4()}"
                msg = Message(MessageType.TEXT, username, msg_content)
                
                msg_start = time.time()
                await ws.send(msg.serialize())
                msg_latency = time.time() - msg_start
                
                result.latencies.append(msg_latency)
                result.success_count += 1
                
                if MESSAGE_INTERVAL > 0:
                    await asyncio.sleep(MESSAGE_INTERVAL)
    except Exception as e:
        print(f"{username} message error: {e}")

    return result


async def create_clients(count: int) -> dict:
    print(f"Pre-creating {count} client instances...")
    clients = {}
    for i in range(count):
        clients[i] = AloneChatAPIClient(HOST, API_PORT)
    print("Client instances created.")
    return clients


async def run_stage(name: str, coro_func, clients: dict, total_users: int, batch_size: int, batch_delay: float) -> Tuple[float, int, int, List[float]]:
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
    
    ws_url = client.get_ws_url()
    
    try:
        async with websockets.connect(ws_url, proxy=None) as ws:
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
    print(f"Starting load test with {TOTAL_USERS} users...")
    print(f"Each user sends {MESSAGES_PER_USER} message(s)")
    print(f"Batch size: {BATCH_SIZE}, Batch delay: {BATCH_DELAY}s")
    print()

    clients = await create_clients(TOTAL_USERS)

    print()
    print("====== Starting Multi-User Test (HTTP) ======")
    overall_start = time.time()

    reg_duration, reg_success, reg_total, _ = await run_stage(
        "Register", register_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    login_duration, login_success, login_total, _ = await run_stage(
        "Login", login_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    msg_duration, msg_success, msg_total, msg_latencies = await run_stage(
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


async def multi_user_test_ws():
    print(f"Starting WebSocket load test with {TOTAL_USERS} users...")
    print(f"Each user sends {MESSAGES_PER_USER} message(s)")
    print(f"Batch size: {BATCH_SIZE}, Batch delay: {BATCH_DELAY}s")
    print()

    clients = await create_clients(TOTAL_USERS)

    print()
    print("====== Starting Multi-User Test (WebSocket) ======")
    overall_start = time.time()

    reg_duration, reg_success, reg_total, _ = await run_stage(
        "Register", register_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    login_duration, login_success, login_total, _ = await run_stage(
        "Login", login_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    msg_duration, msg_success, msg_total, msg_latencies = await run_stage(
        "Messages", send_messages_ws, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
    )

    overall_end = time.time()
    await close_session()

    print()
    print("====== Multi-User WebSocket Test Finished ======")
    print(f"Total users: {TOTAL_USERS}")
    print(f"Messages per user: {MESSAGES_PER_USER}")
    print(f"Overall duration: {overall_end - overall_start:.2f}s")
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


async def comparison_test():
    print("=" * 60)
    print("=== HTTP vs WebSocket Comparison Test ===")
    print(f"Users: {TOTAL_USERS}, Messages per user: {MESSAGES_PER_USER}")
    print("=" * 60)
    
    results = {}
    
    for mode, send_func, label in [
        ("http", send_messages, "HTTP POST"),
        ("ws", send_messages_ws, "WebSocket")
    ]:
        print()
        print(f"--- Testing with {label} ---")
        
        clients = await create_clients(TOTAL_USERS)
        
        reg_duration, reg_success, reg_total, _ = await run_stage(
            "Register", register_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
        )
        
        login_duration, login_success, login_total, _ = await run_stage(
            "Login", login_user, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
        )
        
        msg_duration, msg_success, msg_total, msg_latencies = await run_stage(
            "Messages", send_func, clients, TOTAL_USERS, BATCH_SIZE, BATCH_DELAY
        )
        
        await close_session()
        
        results[mode] = {
            "label": label,
            "login_success": login_success,
            "msg_success": msg_success,
            "msg_duration": msg_duration,
            "latencies": msg_latencies
        }
    
    print()
    print("=" * 60)
    print("=== Comparison Results ===")
    print("=" * 60)
    print()
    print(f"{'Metric':<25} {'HTTP POST':>15} {'WebSocket':>15} {'Improvement':>15}")
    print("-" * 70)
    
    http = results["http"]
    ws = results["ws"]
    
    http_throughput = http["msg_success"] / http["msg_duration"] if http["msg_duration"] > 0 else 0
    ws_throughput = ws["msg_success"] / ws["msg_duration"] if ws["msg_duration"] > 0 else 0
    throughput_improve = ((ws_throughput - http_throughput) / http_throughput * 100) if http_throughput > 0 else 0
    
    http_avg = sum(http["latencies"]) / len(http["latencies"]) * 1000 if http["latencies"] else 0
    ws_avg = sum(ws["latencies"]) / len(ws["latencies"]) * 1000 if ws["latencies"] else 0
    latency_improve = ((http_avg - ws_avg) / http_avg * 100) if http_avg > 0 else 0
    
    print(f"{'Throughput (msg/s)':<25} {http_throughput:>15.2f} {ws_throughput:>15.2f} {throughput_improve:>+14.1f}%")
    print(f"{'Avg Latency (ms)':<25} {http_avg:>15.2f} {ws_avg:>15.2f} {latency_improve:>+14.1f}%")
    
    if http["latencies"]:
        sorted_http = sorted(http["latencies"])
        http_p50 = sorted_http[len(sorted_http) // 2] * 1000
        http_p99 = sorted_http[int(len(sorted_http) * 0.99)] * 1000
        print(f"{'HTTP P50 (ms)':<25} {http_p50:>15.2f}")
        print(f"{'HTTP P99 (ms)':<25} {http_p99:>15.2f}")
    
    if ws["latencies"]:
        sorted_ws = sorted(ws["latencies"])
        ws_p50 = sorted_ws[len(sorted_ws) // 2] * 1000
        ws_p99 = sorted_ws[int(len(sorted_ws) * 0.99)] * 1000
        print(f"{'WS P50 (ms)':<25} {'':>15} {ws_p50:>15.2f}")
        print(f"{'WS P99 (ms)':<25} {'':>15} {ws_p99:>15.2f}")
    
    print()
    print(f"Duration: HTTP={http['msg_duration']:.2f}s, WebSocket={ws['msg_duration']:.2f}s")
    print(f"Speedup: {http['msg_duration'] / ws['msg_duration']:.2f}x" if ws['msg_duration'] > 0 else "N/A")


async def main():
    import sys
    
    if len(sys.argv) > 1:
        arg = sys.argv[1]
        if arg == "--single":
            await single_user_high_frequency_test()
        elif arg == "--multi":
            await multi_user_test()
        elif arg == "--compare":
            await comparison_test()
        elif arg == "--ws":
            await multi_user_test_ws()
        else:
            print(f"Unknown option: {arg}")
    else:
        print("AloneChat Load Test")
        print()
        print("Usage:")
        print("  python alonechat_load_test.py --single   # Single user high-frequency test")
        print("  python alonechat_load_test.py --multi    # Multi-user concurrent test (HTTP)")
        print("  python alonechat_load_test.py --ws       # Multi-user concurrent test (WebSocket)")
        print("  python alonechat_load_test.py --compare  # HTTP vs WebSocket comparison")
        print()
        print("Running comparison test...")
        print()
        await comparison_test()


if __name__ == "__main__":
    asyncio.run(main())
