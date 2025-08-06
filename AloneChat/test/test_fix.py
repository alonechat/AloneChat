"""
简单的测试脚本，用于验证AloneChat项目的修复是否有效。
"""
import asyncio
import time

import jwt

from AloneChat.config import config
from AloneChat.core.message.protocol import Message, MessageType


async def test_message_serialization():
    """测试消息序列化和反序列化"""
    print("测试消息序列化和反序列化...")
    msg = Message(
        type=MessageType.TEXT,
        sender="test_user",
        content="测试消息",
        target="another_user",
        command="test_command"
    )
    serialized = msg.serialize()
    print(f"序列化结果: {serialized}")
    deserialized = Message.deserialize(serialized)
    print(f"反序列化结果: {deserialized}")
    assert deserialized.type == MessageType.TEXT
    assert deserialized.sender == "test_user"
    assert deserialized.content == "测试消息"
    assert deserialized.target == "another_user"
    assert deserialized.command == "test_command"
    print("消息序列化和反序列化测试通过！")


async def test_config():
    """测试配置文件"""
    print("测试配置文件...")
    print(f"JWT_SECRET: {config.JWT_SECRET}")
    print(f"JWT_ALGORITHM: {config.JWT_ALGORITHM}")
    print(f"JWT_EXPIRE_MINUTES: {config.JWT_EXPIRE_MINUTES}")
    print(f"DEFAULT_SERVER_PORT: {config.DEFAULT_SERVER_PORT}")
    print("配置文件测试通过！")


async def test_jwt_role():
    """测试JWT令牌中的角色信息"""
    print("测试JWT令牌中的角色信息...")

    # 测试普通用户
    username = "testuser"
    expiration = time.time() + config.JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": username, "exp": expiration, "role": "user"},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM
    )
    print(f"普通用户令牌: {token}")

    # 验证令牌
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        assert payload.get("role") == "user"
        print("普通用户角色验证通过！")
        print(f"普通用户JWT payload: {payload}")  # 打印完整payload
    except jwt.PyJWTError as e:
        print(f"普通用户令牌验证失败: {e}")
        raise

    # 测试管理员用户(admin)
    username = "admin"
    expiration = time.time() + config.JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": username, "exp": expiration, "role": "admin"},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM
    )
    print(f"管理员用户(admin)令牌: {token}")

    # 验证令牌
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        assert payload.get("role") == "admin"
        print("管理员用户(admin)角色验证通过！")
        print(f"管理员用户(admin)JWT payload: {payload}")  # 打印完整payload
    except jwt.PyJWTError as e:
        print(f"管理员用户(admin)令牌验证失败: {e}")
        raise

    # 测试管理员用户(administrator)
    username = "administrator"
    expiration = time.time() + config.JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": username, "exp": expiration, "role": "admin"},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM
    )
    print(f"管理员用户(administrator)令牌: {token}")

    # 验证令牌
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        assert payload.get("role") == "admin"
        print("管理员用户(administrator)角色验证通过！")
        print(f"管理员用户(administrator)JWT payload: {payload}")  # 打印完整payload
    except jwt.PyJWTError as e:
        print(f"管理员用户(administrator)令牌验证失败: {e}")
        raise

    # 测试JWT结构是否包含所有必要字段
    required_fields = ["sub", "role", "exp"]
    for field in required_fields:
        assert field in payload, f"JWT payload missing required field: {field}"
    print("JWT结构验证通过，包含所有必要字段")

    print("JWT角色信息测试通过！")


async def main():
    print("开始测试AloneChat修复...")
    await test_message_serialization()
    await test_config()
    await test_jwt_role()
    print("所有测试完成！")


if __name__ == "__main__":
    asyncio.run(main())
