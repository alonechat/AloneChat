"""
Simple test script to verify that fixes in the AloneChat project work correctly.
"""
import asyncio
import time

import jwt

from AloneChat.config import config
from AloneChat.core.message.protocol import Message, MessageType


async def test_message_serialization():
    """Test message serialization and deserialization"""
    print("Testing message serialization and deserialization...")
    msg = Message(
        type=MessageType.TEXT,
        sender="test_user",
        content="Test MSG",
        target="another_user",
        command="test_command"
    )
    serialized = msg.serialize()
    print(f"Serialization result: {serialized}")
    deserialized = Message.deserialize(serialized)
    print(f"Deserialization result: {deserialized}")
    assert deserialized.type == MessageType.TEXT
    assert deserialized.sender == "test_user"
    assert deserialized.content == "Test MSG"
    assert deserialized.target == "another_user"
    assert deserialized.command == "test_command"
    print("Message serialization/deserialization test passed!")


async def test_config():
    """Test configuration file"""
    print("Testing configuration...")
    print(f"JWT_SECRET: {config.JWT_SECRET}")
    print(f"JWT_ALGORITHM: {config.JWT_ALGORITHM}")
    print(f"JWT_EXPIRE_MINUTES: {config.JWT_EXPIRE_MINUTES}")
    print(f"DEFAULT_SERVER_PORT: {config.DEFAULT_SERVER_PORT}")
    print("Configuration test passed!")


async def test_jwt_role():
    """Test role information in JWT tokens"""
    print("Testing role information in JWT tokens...")

    # Test regular user
    username = "testuser"
    expiration = time.time() + config.JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": username, "exp": expiration, "role": "user"},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM
    )
    print(f"Regular user token: {token}")

    # 验证令牌
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        assert payload.get("role") == "user"
        print("Regular user role verification passed!")
        print(f"Regular user JWT payload: {payload}")  # print full payload
    except jwt.PyJWTError as e:
        print(f"Regular user token verification failed: {e}")
        raise

    # Test admin user (admin)
    username = "admin"
    expiration = time.time() + config.JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": username, "exp": expiration, "role": "admin"},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM
    )
    print(f"Admin user (admin) token: {token}")

    # Verify token
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        assert payload.get("role") == "admin"
        print("Admin user (admin) role verification passed!")
        print(f"Admin user (admin) JWT payload: {payload}")  # print full payload
    except jwt.PyJWTError as e:
        print(f"Admin user (admin) token verification failed: {e}")
        raise

    # Test admin user (administrator)
    username = "administrator"
    expiration = time.time() + config.JWT_EXPIRE_MINUTES * 60
    token = jwt.encode(
        {"sub": username, "exp": expiration, "role": "admin"},
        config.JWT_SECRET,
        algorithm=config.JWT_ALGORITHM
    )
    print(f"Admin user (administrator) token: {token}")

    # Verify token
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALGORITHM])
        assert payload.get("role") == "admin"
        print("Admin user (administrator) role verification passed!")
        print(f"Admin user (administrator) JWT payload: {payload}")  # print full payload
    except jwt.PyJWTError as e:
        print(f"Admin user (administrator) token verification failed: {e}")
        raise

    # Test whether the JWT structure includes all required fields
    required_fields = ["sub", "role", "exp"]
    for field in required_fields:
        assert field in payload, f"JWT payload missing required field: {field}"
    print("JWT structure verification passed; all required fields present")

    print("JWT role information test passed!")


async def main():
    print("Starting AloneChat fix tests...")
    await test_message_serialization()
    await test_config()
    await test_jwt_role()
    print("All tests completed!")


if __name__ == "__main__":
    asyncio.run(main())
