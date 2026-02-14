"""
Unit tests for the refactored server components and plugin integration.

Tests cover:
- Hook system (registration, execution, priority)
- Message processing pipeline
- Plugin integration
- Connection context management
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from AloneChat.core.message.protocol import Message, MessageType
from AloneChat.core.server.interfaces import (
    HookContext,
    HookPhase,
    PluginAwareComponent,
    ProcessingResult,
)
from AloneChat.core.server.websocket_manager import (
    ConnectionContext,
    MessageProcessingPipeline,
)


# noinspection PyAbstractClass
class TestPluginAwareComponent:
    """Tests for the PluginAwareComponent base class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.component = PluginAwareComponent()
    
    def test_register_hook(self):
        """Test hook registration."""
        def sample_hook(ctx: HookContext) -> HookContext:
            return ctx
        
        self.component.register_hook(HookPhase.PRE_MESSAGE, sample_hook)
        
        assert HookPhase.PRE_MESSAGE in self.component._hooks
        assert len(self.component._hooks[HookPhase.PRE_MESSAGE]) == 1
        assert self.component._hooks[HookPhase.PRE_MESSAGE][0] == (100, sample_hook)
    
    def test_register_hook_with_priority(self):
        """Test hook registration with custom priority."""
        def hook1(ctx: HookContext) -> HookContext:
            return ctx
        
        def hook2(ctx: HookContext) -> HookContext:
            return ctx
        
        self.component.register_hook(HookPhase.PRE_MESSAGE, hook1, priority=50)
        self.component.register_hook(HookPhase.PRE_MESSAGE, hook2, priority=10)
        
        hooks = self.component._hooks[HookPhase.PRE_MESSAGE]
        assert hooks[0][0] == 10
        assert hooks[1][0] == 50
    
    def test_unregister_hook(self):
        """Test hook unregistration."""
        def sample_hook(ctx: HookContext) -> HookContext:
            return ctx
        
        self.component.register_hook(HookPhase.PRE_MESSAGE, sample_hook)
        result = self.component.unregister_hook(HookPhase.PRE_MESSAGE, sample_hook)
        
        assert result is True
        assert len(self.component._hooks[HookPhase.PRE_MESSAGE]) == 0
    
    def test_unregister_nonexistent_hook(self):
        """Test unregistering a hook that doesn't exist."""
        def sample_hook(ctx: HookContext) -> HookContext:
            return ctx
        
        result = self.component.unregister_hook(HookPhase.PRE_MESSAGE, sample_hook)
        assert result is False
    
    @pytest.mark.asyncio
    async def test_execute_hooks(self):
        """Test hook execution."""
        execution_order = []
        
        def hook1(ctx: HookContext) -> HookContext:
            execution_order.append(1)
            ctx.set('hook1', True)
            return ctx
        
        def hook2(ctx: HookContext) -> HookContext:
            execution_order.append(2)
            ctx.set('hook2', True)
            return ctx
        
        self.component.register_hook(HookPhase.PRE_MESSAGE, hook1, priority=1)
        self.component.register_hook(HookPhase.PRE_MESSAGE, hook2, priority=2)
        
        context = HookContext(phase=HookPhase.PRE_MESSAGE)
        result = await self.component._execute_hooks(HookPhase.PRE_MESSAGE, context)
        
        assert execution_order == [1, 2]
        assert result.get('hook1') is True
        assert result.get('hook2') is True
    
    @pytest.mark.asyncio
    async def test_execute_hooks_with_exception(self):
        """Test that hooks continue execution even if one fails."""
        execution_order = []
        
        def failing_hook(ctx: HookContext) -> HookContext:
            execution_order.append(1)
            raise ValueError("Hook failed")
        
        def success_hook(ctx: HookContext) -> HookContext:
            execution_order.append(2)
            return ctx
        
        self.component.register_hook(HookPhase.PRE_MESSAGE, failing_hook, priority=1)
        self.component.register_hook(HookPhase.PRE_MESSAGE, success_hook, priority=2)
        
        context = HookContext(phase=HookPhase.PRE_MESSAGE)
        result = await self.component._execute_hooks(HookPhase.PRE_MESSAGE, context)
        
        assert execution_order == [1, 2]


class TestHookContext:
    """Tests for the HookContext dataclass."""
    
    def test_create_context(self):
        """Test creating a hook context."""
        context = HookContext(
            phase=HookPhase.PRE_MESSAGE,
            user_id="test_user",
            message=MagicMock(),
            connection=MagicMock()
        )
        
        assert context.phase == HookPhase.PRE_MESSAGE
        assert context.user_id == "test_user"
        assert context.message is not None
        assert context.connection is not None
    
    def test_metadata_operations(self):
        """Test metadata get/set operations."""
        context = HookContext(phase=HookPhase.PRE_MESSAGE)
        
        context.set('key1', 'value1')
        context.set('key2', 123)
        
        assert context.get('key1') == 'value1'
        assert context.get('key2') == 123
        assert context.get('nonexistent') is None
        assert context.get('nonexistent', 'default') == 'default'


class TestProcessingResult:
    """Tests for the ProcessingResult dataclass."""
    
    def test_create_result(self):
        """Test creating a processing result."""
        result = ProcessingResult(
            success=True,
            content="processed content",
            modified=True,
            metadata={'key': 'value'}
        )
        
        assert result.success is True
        assert result.content == "processed content"
        assert result.modified is True
        assert result.metadata == {'key': 'value'}
    
    def test_default_values(self):
        """Test default values for ProcessingResult."""
        result = ProcessingResult(success=True, content="test")
        
        assert result.modified is False
        assert result.error is None
        assert result.metadata == {}


class TestConnectionContext:
    """Tests for the ConnectionContext class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_connection = MagicMock()
        self.mock_connection.send = AsyncMock(return_value=True)
        self.mock_connection.close = AsyncMock()
        self.mock_connection.is_open = MagicMock(return_value=True)
        
        self.mock_manager = MagicMock()
        
        self.context = ConnectionContext(
            user_id="test_user",
            connection=self.mock_connection,
            manager=self.mock_manager
        )
    
    def test_metadata(self):
        """Test connection metadata operations."""
        self.context.set_metadata('key', 'value')
        assert self.context.get_metadata('key') == 'value'
        assert self.context.get_metadata('nonexistent', 'default') == 'default'
    
    @pytest.mark.asyncio
    async def test_send_message(self):
        """Test sending a message."""
        message = Message(MessageType.TEXT, "sender", "content")
        
        result = await self.context.send(message)
        
        assert result is True
        self.mock_connection.send.assert_called_once()
    
    @pytest.mark.asyncio
    async def test_close_connection(self):
        """Test closing a connection."""
        await self.context.close(code=1000, reason="test")
        
        self.mock_connection.close.assert_called_once_with(1000, "test")
    
    @pytest.mark.asyncio
    async def test_send_system_message(self):
        """Test sending a system message."""
        result = await self.context.send_system_message("test message")
        
        assert result is True
        self.mock_connection.send.assert_called_once()
    
    def test_is_active(self):
        """Test checking if connection is active."""
        assert self.context.is_active is True
        
        self.mock_connection.is_open.return_value = False
        assert self.context.is_active is False


class TestMessageProcessingPipeline:
    """Tests for the MessageProcessingPipeline class."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.mock_command_processor = MagicMock()
        self.mock_command_processor.process = MagicMock(
            return_value=Message(MessageType.TEXT, "sender", "processed")
        )
        
        self.pipeline = MessageProcessingPipeline(
            command_processor=self.mock_command_processor
        )
    
    @pytest.mark.asyncio
    async def test_process_message(self):
        """Test processing a message through the pipeline."""
        result = await self.pipeline.process(
            content="test message",
            sender="user1",
            target=None
        )
        
        assert result.success is True
        assert result.content == "processed"
    
    @pytest.mark.asyncio
    async def test_pre_processor(self):
        """Test pre-processor modification of content."""
        def pre_processor(content, sender, target):
            return content.upper()
        
        self.pipeline.add_pre_processor(pre_processor)
        
        result = await self.pipeline.process(
            content="test message",
            sender="user1",
            target=None
        )
        
        assert result.modified is True
    
    @pytest.mark.asyncio
    async def test_post_processor(self):
        """Test post-processor execution."""
        post_processor_calls = []
        
        def post_processor(result: ProcessingResult):
            post_processor_calls.append(result)
        
        self.pipeline.add_post_processor(post_processor)
        
        await self.pipeline.process(
            content="test message",
            sender="user1",
            target=None
        )
        
        assert len(post_processor_calls) == 1
    
    @pytest.mark.asyncio
    async def test_plugin_manager_integration(self):
        """Test integration with plugin manager."""
        mock_plugin_manager = MagicMock()
        mock_plugin_manager.process_command = MagicMock(
            return_value="plugin processed"
        )
        
        pipeline = MessageProcessingPipeline(
            command_processor=self.mock_command_processor,
            plugin_manager=mock_plugin_manager
        )
        
        await pipeline.process(
            content="test message",
            sender="user1",
            target=None
        )
        
        mock_plugin_manager.process_command.assert_called_once()


class TestHookPhases:
    """Tests for hook phase execution order."""
    
    def test_hook_phases_exist(self):
        """Test that all expected hook phases are defined."""
        expected_phases = [
            HookPhase.PRE_CONNECT,
            HookPhase.POST_CONNECT,
            HookPhase.PRE_AUTHENTICATE,
            HookPhase.POST_AUTHENTICATE,
            HookPhase.PRE_MESSAGE,
            HookPhase.POST_MESSAGE,
            HookPhase.PRE_BROADCAST,
            HookPhase.POST_BROADCAST,
            HookPhase.PRE_DISCONNECT,
            HookPhase.POST_DISCONNECT,
            HookPhase.PRE_COMMAND,
            HookPhase.POST_COMMAND,
        ]
        
        for phase in expected_phases:
            assert hasattr(HookPhase, phase.name)
    
    def test_hook_phase_order(self):
        """Test that hook phases have unique values."""
        phases = list(HookPhase)
        values = [p.value for p in phases]
        
        assert len(values) == len(set(values))


class TestBackwardCompatibility:
    """Tests for backward compatibility with legacy code."""
    
    def test_import_legacy_manager(self):
        """Test that WebSocketManager alias works (now points to UnifiedWebSocketManager)."""
        from AloneChat.core.server import WebSocketManager, UnifiedWebSocketManager
        
        # WebSocketManager should now be an alias to UnifiedWebSocketManager
        assert WebSocketManager is UnifiedWebSocketManager
    
    def test_import_legacy_command_system(self):
        """Test that legacy command system can be imported."""
        from AloneChat.core.server.command import CommandSystem
        
        assert CommandSystem is not None
    
    def test_import_unified_manager(self):
        """Test that unified manager can be imported."""
        from AloneChat.core.server.websocket_manager import UnifiedWebSocketManager
        
        assert UnifiedWebSocketManager is not None


# noinspection PyAbstractClass
@pytest.mark.asyncio
class TestAsyncOperations:
    """Tests for async operations."""
    
    async def test_concurrent_hook_execution(self):
        """Test that hooks can be executed concurrently."""
        component = PluginAwareComponent()
        execution_times = []
        
        import time
        
        def slow_hook(ctx: HookContext) -> HookContext:
            time.sleep(0.01)
            execution_times.append(time.time())
            return ctx
        
        component.register_hook(HookPhase.PRE_MESSAGE, slow_hook)
        component.register_hook(HookPhase.PRE_MESSAGE, slow_hook)
        
        context = HookContext(phase=HookPhase.PRE_MESSAGE)
        await component._execute_hooks(HookPhase.PRE_MESSAGE, context)
        
        assert len(execution_times) == 2


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
