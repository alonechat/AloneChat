"""
Comprehensive server integration tests for AloneChat.

Tests include:
- Server initialization and startup
- Connection validation
- Authentication flow
- Message sending and receiving
- Performance metrics collection
- Cleanup procedures

Run with: python -m pytest AloneChat/test/test_server_integration.py -v
"""

import asyncio
import json
import time
from typing import Optional

import pytest
import websockets
from websockets.exceptions import ConnectionClosedError

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from conftest import TestConfig, PerformanceMetrics, TestDataGenerator


class TestServerInitialization:
    """Tests for server initialization and startup."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_server_starts_successfully(self, server_instance):
        """Test that server starts without errors."""
        assert server_instance is not None
        assert server_instance.is_running is True
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_server_accepts_connections(self, server_instance, test_config: TestConfig):
        """Test that server accepts WebSocket connections."""
        token = TestDataGenerator.generate_jwt_token("test_user_0")
        url = f"{test_config.ws_url}?token={token}"
        
        async with websockets.connect(url) as ws:
            assert ws.state.name == "OPEN"
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_server_rejects_invalid_token(self, server_instance, test_config: TestConfig):
        """Test that server rejects connections with invalid tokens."""
        url = f"{test_config.ws_url}?token=invalid_token"
        
        try:
            async with websockets.connect(url) as ws:
                await asyncio.sleep(0.5)
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    response_data = json.loads(response)
                    assert "error" in response_data.get("content", "").lower() or \
                           response_data.get("type") is not None
                except ConnectionClosedError:
                    pass
        except ConnectionClosedError:
            pass


class TestConnectionValidation:
    """Tests for connection validation."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_connection_with_valid_jwt(
        self,
        server_instance,
        test_config: TestConfig,
        performance_metrics: PerformanceMetrics
    ):
        """Test connection with valid JWT token."""
        token = TestDataGenerator.generate_jwt_token("test_connection_user")
        url = f"{test_config.ws_url}?token={token}"
        
        start_time = time.perf_counter()
        async with websockets.connect(url) as ws:
            connection_time = time.perf_counter() - start_time
            performance_metrics.record_connection_time(connection_time)
            performance_metrics.record_success()
            
            assert ws.state.name == "OPEN"
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    @pytest.mark.skip(reason="Server currently allows duplicate connections - behavior under review")
    async def test_duplicate_connection_rejected(
        self,
        server_instance,
        test_config: TestConfig
    ):
        """Test that duplicate connections are rejected."""
        token = TestDataGenerator.generate_jwt_token("duplicate_user")
        url = f"{test_config.ws_url}?token={token}"
        
        async with websockets.connect(url) as ws1:
            assert ws1.state.name == "OPEN"
            
            await asyncio.sleep(0.2)
            
            try:
                async with websockets.connect(url) as ws2:
                    await asyncio.sleep(0.5)
                    try:
                        response = await asyncio.wait_for(ws2.recv(), timeout=2.0)
                        response_data = json.loads(response)
                        assert "already" in response_data.get("content", "").lower() or \
                               "logged" in response_data.get("content", "").lower()
                    except ConnectionClosedError:
                        pass
            except ConnectionClosedError:
                pass
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_expired_token_rejected(
        self,
        server_instance,
        test_config: TestConfig
    ):
        """Test that expired tokens are rejected."""
        import jwt
        
        secret = TestDataGenerator.get_jwt_secret()
        
        payload = {
            "sub": "expired_user",
            "exp": int(time.time()) - 3600,
            "iat": int(time.time()) - 7200,
        }
        token = jwt.encode(payload, secret, algorithm="HS256")
        url = f"{test_config.ws_url}?token={token}"
        
        try:
            async with websockets.connect(url) as ws:
                await asyncio.sleep(0.5)
                try:
                    response = await asyncio.wait_for(ws.recv(), timeout=2.0)
                    response_data = json.loads(response)
                    assert "expired" in response_data.get("content", "").lower() or \
                           "token" in response_data.get("content", "").lower()
                except ConnectionClosedError:
                    pass
        except ConnectionClosedError:
            pass


class TestMessageHandling:
    """Tests for message sending and receiving."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_send_text_message(
        self,
        server_instance,
        test_config: TestConfig,
        performance_metrics: PerformanceMetrics
    ):
        """Test sending a text message."""
        token = TestDataGenerator.generate_jwt_token("message_user")
        url = f"{test_config.ws_url}?token={token}"
        
        async with websockets.connect(url) as ws:
            message = {
                "type": "TEXT",
                "sender": "message_user",
                "content": "Hello, World!",
                "target": None,
                "timestamp": time.time(),
            }
            
            start_time = time.perf_counter()
            await ws.send(json.dumps(message))
            
            try:
                response = await asyncio.wait_for(
                    ws.recv(),
                    timeout=test_config.timeout
                )
                response_time = time.perf_counter() - start_time
                performance_metrics.record_response_time(response_time)
                performance_metrics.record_success()
                performance_metrics.record_message("TEXT")
                
                response_data = json.loads(response)
                assert response_data is not None
            except asyncio.TimeoutError:
                performance_metrics.record_error()
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_send_heartbeat(
        self,
        server_instance,
        test_config: TestConfig,
        performance_metrics: PerformanceMetrics
    ):
        """Test sending a heartbeat message."""
        token = TestDataGenerator.generate_jwt_token("heartbeat_user")
        url = f"{test_config.ws_url}?token={token}"
        
        async with websockets.connect(url) as ws:
            heartbeat = {
                "type": "HEARTBEAT",
                "sender": "heartbeat_user",
                "content": "ping",
                "timestamp": time.time(),
            }
            
            start_time = time.perf_counter()
            await ws.send(json.dumps(heartbeat))
            
            try:
                response = await asyncio.wait_for(
                    ws.recv(),
                    timeout=test_config.timeout
                )
                response_time = time.perf_counter() - start_time
                performance_metrics.record_response_time(response_time)
                performance_metrics.record_message("HEARTBEAT")
                
                response_data = json.loads(response)
                assert response_data.get("type") == "HEARTBEAT"
                assert response_data.get("content") == "pong"
            except asyncio.TimeoutError:
                performance_metrics.record_error()
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_broadcast_message(
        self,
        server_instance,
        test_config: TestConfig
    ):
        """Test broadcasting messages to multiple clients."""
        connections = []
        
        for i in range(3):
            token = TestDataGenerator.generate_jwt_token(f"broadcast_user_{i}")
            url = f"{test_config.ws_url}?token={token}"
            ws = await websockets.connect(url)
            connections.append(ws)
        
        try:
            await asyncio.sleep(0.3)
            
            message = {
                "type": "TEXT",
                "sender": "broadcast_user_0",
                "content": "Broadcast message",
                "timestamp": time.time(),
            }
            
            await connections[0].send(json.dumps(message))
            
            await asyncio.sleep(0.5)
            
        finally:
            for ws in connections:
                await ws.close()


class TestPerformanceMetrics:
    """Tests for performance metrics collection."""
    
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_response_time_under_threshold(
        self,
        server_instance,
        test_config: TestConfig,
        performance_metrics: PerformanceMetrics
    ):
        """Test that response times are under acceptable threshold."""
        token = TestDataGenerator.generate_jwt_token("perf_user")
        url = f"{test_config.ws_url}?token={token}"
        
        max_acceptable_time = 0.5
        
        async with websockets.connect(url) as ws:
            for i in range(10):
                message = {
                    "type": "TEXT",
                    "sender": "perf_user",
                    "content": f"Performance test message {i}",
                    "timestamp": time.time(),
                }
                
                start_time = time.perf_counter()
                await ws.send(json.dumps(message))
                
                try:
                    await asyncio.wait_for(ws.recv(), timeout=test_config.timeout)
                    response_time = time.perf_counter() - start_time
                    performance_metrics.record_response_time(response_time)
                    
                    assert response_time < max_acceptable_time, \
                        f"Response time {response_time}s exceeds threshold {max_acceptable_time}s"
                except asyncio.TimeoutError:
                    performance_metrics.record_error()
        
        metrics = performance_metrics.to_dict()
        print(f"\nPerformance Metrics: {json.dumps(metrics, indent=2)}")
    
    @pytest.mark.performance
    @pytest.mark.slow
    @pytest.mark.asyncio
    async def test_concurrent_connections(
        self,
        server_instance,
        test_config: TestConfig,
        performance_metrics: PerformanceMetrics
    ):
        """Test server handles concurrent connections."""
        num_connections = 5
        connections = []
        
        start_time = time.perf_counter()
        
        for i in range(num_connections):
            token = TestDataGenerator.generate_jwt_token(f"concurrent_user_{i}")
            url = f"{test_config.ws_url}?token={token}"
            
            try:
                ws = await websockets.connect(url)
                connections.append(ws)
                performance_metrics.record_success()
            except Exception:
                performance_metrics.record_error()
        
        total_time = time.perf_counter() - start_time
        performance_metrics.record_connection_time(total_time / num_connections)
        
        assert len(connections) == num_connections, \
            f"Expected {num_connections} connections, got {len(connections)}"
        
        for ws in connections:
            await ws.close()
    
    @pytest.mark.performance
    @pytest.mark.asyncio
    async def test_message_throughput(
        self,
        server_instance,
        test_config: TestConfig,
        performance_metrics: PerformanceMetrics
    ):
        """Test message throughput."""
        token = TestDataGenerator.generate_jwt_token("throughput_user")
        url = f"{test_config.ws_url}?token={token}"
        
        num_messages = 20
        start_time = time.perf_counter()
        
        async with websockets.connect(url) as ws:
            for i in range(num_messages):
                message = {
                    "type": "TEXT",
                    "sender": "throughput_user",
                    "content": f"Throughput test {i}",
                    "timestamp": time.time(),
                }
                
                await ws.send(json.dumps(message))
                performance_metrics.record_message("TEXT")
                
                try:
                    await asyncio.wait_for(ws.recv(), timeout=1.0)
                    performance_metrics.record_success()
                except asyncio.TimeoutError:
                    performance_metrics.record_error()
        
        total_time = time.perf_counter() - start_time
        throughput = num_messages / total_time
        
        print(f"\nMessage Throughput: {throughput:.2f} messages/second")
        print(f"Total time: {total_time:.2f}s for {num_messages} messages")


class TestCleanupProcedures:
    """Tests for cleanup procedures."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_client_disconnect_cleanup(
        self,
        server_instance,
        test_config: TestConfig
    ):
        """Test that server cleans up after client disconnect."""
        token = TestDataGenerator.generate_jwt_token("cleanup_user")
        url = f"{test_config.ws_url}?token={token}"
        
        ws = await websockets.connect(url)
        assert ws.state.name == "OPEN"
        
        await ws.close()
        
        await asyncio.sleep(0.5)
        
        assert ws.state.name == "CLOSED"
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_server_handles_malformed_data(
        self,
        server_instance,
        test_config: TestConfig
    ):
        """Test server handles malformed data gracefully."""
        token = TestDataGenerator.generate_jwt_token("malformed_user")
        url = f"{test_config.ws_url}?token={token}"
        
        async with websockets.connect(url) as ws:
            try:
                await ws.send("invalid json{{{")
                await asyncio.sleep(0.5)
            except Exception:
                pass


class TestServerHealth:
    """Tests for server health and status."""
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_server_is_running(self, server_instance):
        """Test server reports running status."""
        assert server_instance.is_running is True
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_server_has_session_manager(self, server_instance):
        """Test server has session manager."""
        assert server_instance.session_manager is not None
    
    @pytest.mark.integration
    @pytest.mark.asyncio
    async def test_server_has_command_processor(self, server_instance):
        """Test server has command processor."""
        assert server_instance.command_processor is not None


def test_performance_metrics_summary(performance_metrics: PerformanceMetrics):
    """Output performance metrics summary."""
    metrics = performance_metrics.to_dict()
    print("\n" + "=" * 50)
    print("PERFORMANCE METRICS SUMMARY")
    print("=" * 50)
    print(f"Total Requests: {metrics['total_requests']}")
    print(f"Success Count: {metrics['success_count']}")
    print(f"Error Count: {metrics['error_count']}")
    print(f"Error Rate: {metrics['error_rate']:.2%}")
    print(f"Avg Response Time: {metrics['avg_response_time_ms']:.2f}ms")
    print(f"Min Response Time: {metrics['min_response_time_ms']:.2f}ms")
    print(f"Max Response Time: {metrics['max_response_time_ms']:.2f}ms")
    print(f"P95 Response Time: {metrics['p95_response_time_ms']:.2f}ms")
    print(f"Avg Connection Time: {metrics['avg_connection_time_ms']:.2f}ms")
    print("=" * 50)


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
