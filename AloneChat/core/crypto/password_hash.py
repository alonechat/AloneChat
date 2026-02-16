"""
Password hashing module using Argon2.

Argon2 is the winner of the Password Hashing Competition (2015).
It provides:
- High performance (~10-30ms per hash)
- Memory-hard security (resistant to GPU attacks)
- Configurable time/memory tradeoffs
"""

import logging
from typing import Optional

logger = logging.getLogger(__name__)

_HAS_ARGON2 = False

try:
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError
    _HAS_ARGON2 = True
    _argon2_hasher = PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=4,
        hash_len=32,
        salt_len=16
    )
except ImportError:
    logger.error("argon2-cffi not installed. Install with: pip install argon2-cffi")


def hash_password(password: str) -> str:
    """
    Hash a password using Argon2id.
    
    Args:
        password: Plain text password
    
    Returns:
        Hashed password string
    
    Raises:
        RuntimeError: If argon2-cffi is not installed
    """
    if not _HAS_ARGON2:
        raise RuntimeError("argon2-cffi is required. Install with: pip install argon2-cffi")
    
    return _argon2_hasher.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """
    Verify a password against an Argon2 hash.
    
    Args:
        password: Plain text password
        hashed_password: Argon2 hashed password
    
    Returns:
        True if password matches, False otherwise
    """
    if not _HAS_ARGON2:
        raise RuntimeError("argon2-cffi is required. Install with: pip install argon2-cffi")
    
    if not hashed_password:
        return False
    
    try:
        _argon2_hasher.verify(hashed_password, password)
        return True
    except (VerifyMismatchError, VerificationError):
        return False
    except Exception as e:
        logger.error("Password verification error: %s", e)
        return False


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a hash should be rehashed with current settings.
    
    Args:
        hashed_password: Current Argon2 hash
    
    Returns:
        True if rehashing is recommended
    """
    if not _HAS_ARGON2:
        return False
    
    try:
        return _argon2_hasher.check_needs_rehash(hashed_password)
    except Exception:
        return False


def get_backend_info() -> dict:
    """
    Get information about the hashing backend.
    
    Returns:
        Dictionary with backend information
    """
    return {
        "algorithm": "argon2id",
        "available": _HAS_ARGON2,
        "time_cost": 2,
        "memory_cost": 65536,
        "parallelism": 4
    }
