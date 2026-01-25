"""Security utilities for plugin credential handling.

Provides secure credential storage with memory locking to prevent
credentials from being swapped to disk.
"""

import ctypes
import os
from typing import Optional

# Try to import mlock for memory locking
try:
    import ctypes.util
    libc = ctypes.CDLL(ctypes.util.find_library('c'), use_errno=True)
    MLOCK_AVAILABLE = True
except (OSError, TypeError):
    MLOCK_AVAILABLE = False


class SecureCredentials:
    """Secure credential storage with memory locking.

    Credentials are loaded from environment variables and optionally
    locked in memory to prevent swapping to disk.
    """

    def __init__(self):
        self._credentials: dict[str, str] = {}
        self._locked = False

    def load_from_env(self, env_vars: list[str], clear_env: bool = True) -> None:
        """Load credentials from environment variables.

        Args:
            env_vars: List of environment variable names to load
            clear_env: Whether to clear env vars after loading (default True)
        """
        for var in env_vars:
            value = os.environ.get(var)
            if value:
                self._credentials[var] = value
                if clear_env:
                    os.environ.pop(var, None)

        # Try to lock credentials in memory
        if self._credentials and MLOCK_AVAILABLE:
            self._lock_memory()

    def _lock_memory(self) -> None:
        """Attempt to lock credential memory pages."""
        if not MLOCK_AVAILABLE:
            return

        try:
            # Lock all current and future pages
            MCL_CURRENT = 1
            MCL_FUTURE = 2
            result = libc.mlockall(MCL_CURRENT | MCL_FUTURE)
            if result == 0:
                self._locked = True
        except Exception:
            # Memory locking is best-effort
            pass

    def get(self, name: str) -> Optional[str]:
        """Get a credential value.

        Args:
            name: Credential name (environment variable name)

        Returns:
            Credential value or None if not found
        """
        return self._credentials.get(name)

    def get_env_dict(self, names: Optional[list[str]] = None) -> dict[str, str]:
        """Get credentials as environment dict for subprocess.

        Args:
            names: List of credential names to include, or None for all

        Returns:
            Dictionary suitable for subprocess env parameter
        """
        if names is None:
            return dict(self._credentials)
        return {k: v for k, v in self._credentials.items() if k in names}

    def is_locked(self) -> bool:
        """Check if credentials are locked in memory."""
        return self._locked

    def has(self, name: str) -> bool:
        """Check if a credential exists."""
        return name in self._credentials

    def clear(self) -> None:
        """Securely clear all credentials."""
        # Overwrite credential values before clearing
        for key in self._credentials:
            self._credentials[key] = '\x00' * len(self._credentials[key])
        self._credentials.clear()


def verify_peer_uid(sock, allowed_uids: list[int]) -> tuple[bool, int]:
    """Verify the UID of a socket peer using SO_PEERCRED.

    Args:
        sock: Unix socket connection
        allowed_uids: List of allowed user IDs

    Returns:
        Tuple of (allowed, peer_uid)
    """
    import socket

    try:
        # SO_PEERCRED returns struct ucred: { pid, uid, gid }
        SO_PEERCRED = 17  # Linux-specific
        cred = sock.getsockopt(socket.SOL_SOCKET, SO_PEERCRED, 12)
        pid, uid, gid = ctypes.c_uint32.from_buffer_copy(cred[0:4]).value, \
                        ctypes.c_uint32.from_buffer_copy(cred[4:8]).value, \
                        ctypes.c_uint32.from_buffer_copy(cred[8:12]).value

        allowed = len(allowed_uids) == 0 or uid in allowed_uids
        return allowed, uid
    except Exception:
        # If we can't check, deny access
        return False, -1
