#!/usr/bin/env python3
"""
Credential Agent - Secure socket-based credential management.

This agent provides credentials to authorized CLI tools via Unix socket,
with several security features:

1. Memory Locking: Secrets are stored in mlock'd memory (no swap)
2. Process Isolation: Credentials cleared from environment after loading
3. SO_PEERCRED: Caller verification via kernel-level credentials
4. Policy Enforcement: Fine-grained access control per tool/operation
5. No Disk Writes: Credentials never written to disk
6. Audit Logging: All credential access is logged
"""

import ctypes
import hmac
import hashlib
import json
import logging
import os
import signal
import socket
import struct
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

import yaml

# Configuration
SOCKET_PATH = os.environ.get("AGENT_SOCKET_PATH", "/run/agent/cred.sock")
POLICY_PATH = os.environ.get("AGENT_POLICY_PATH", "/app/policy.yaml")
ALLOWED_UIDS = [int(uid) for uid in os.environ.get("AGENT_ALLOWED_UIDS", "1000").split(",")]
DEBUG = os.environ.get("AGENT_DEBUG", "false").lower() == "true"

# Set up logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Secure Memory Management
# ============================================================================

# libc for memory locking
try:
    libc = ctypes.CDLL("libc.so.6", use_errno=True)
    MLOCK_AVAILABLE = True
except OSError:
    libc = None
    MLOCK_AVAILABLE = False
    logger.warning("libc not available, memory locking disabled")


def mlock_bytes(data: bytes) -> Optional[ctypes.Array]:
    """Lock bytes in memory to prevent swapping."""
    if not MLOCK_AVAILABLE or not data:
        return None

    try:
        # Create a ctypes buffer for the data
        buf = ctypes.create_string_buffer(data, len(data))
        # Lock the memory
        result = libc.mlock(ctypes.addressof(buf), len(data))
        if result != 0:
            errno = ctypes.get_errno()
            logger.warning(f"mlock failed with errno {errno} (may need CAP_IPC_LOCK)")
            return None
        return buf
    except Exception as e:
        logger.warning(f"Failed to mlock memory: {e}")
        return None


def munlock_bytes(buf: ctypes.Array, size: int) -> None:
    """Unlock and zero memory."""
    if not MLOCK_AVAILABLE or buf is None:
        return

    try:
        # Zero the memory first
        ctypes.memset(ctypes.addressof(buf), 0, size)
        # Unlock
        libc.munlock(ctypes.addressof(buf), size)
    except Exception as e:
        logger.warning(f"Failed to munlock memory: {e}")


@dataclass
class SecureSecret:
    """A secret stored in locked memory."""
    name: str
    _data: bytes = field(repr=False)
    _locked_buf: Optional[ctypes.Array] = field(default=None, repr=False)
    created_at: float = field(default_factory=time.time)

    def __post_init__(self):
        # Lock the secret in memory
        self._locked_buf = mlock_bytes(self._data)
        if self._locked_buf:
            logger.debug(f"Secret '{self.name}' locked in memory")

    def get_value(self) -> str:
        """Get the secret value."""
        if self._locked_buf:
            return self._locked_buf.value.decode('utf-8')
        return self._data.decode('utf-8')

    def destroy(self) -> None:
        """Securely destroy the secret."""
        if self._locked_buf:
            munlock_bytes(self._locked_buf, len(self._data))
            self._locked_buf = None
        # Zero the original data reference
        self._data = b'\x00' * len(self._data)
        logger.debug(f"Secret '{self.name}' destroyed")


# ============================================================================
# Policy Engine
# ============================================================================

@dataclass
class Policy:
    """Access control policy for tools and operations."""
    tools: dict[str, dict] = field(default_factory=dict)
    allowed_uids: list[int] = field(default_factory=list)
    default_deny: bool = True
    audit_all: bool = True

    @classmethod
    def load(cls, path: str) -> "Policy":
        """Load policy from YAML file."""
        policy_file = Path(path)
        if not policy_file.exists():
            logger.warning(f"Policy file not found: {path}, using defaults")
            return cls(allowed_uids=ALLOWED_UIDS)

        try:
            with open(policy_file) as f:
                data = yaml.safe_load(f) or {}

            return cls(
                tools=data.get("tools", {}),
                allowed_uids=data.get("allowed_uids", ALLOWED_UIDS),
                default_deny=data.get("default_deny", True),
                audit_all=data.get("audit_all", True),
            )
        except Exception as e:
            logger.error(f"Failed to load policy: {e}")
            return cls(allowed_uids=ALLOWED_UIDS)

    def check_access(
        self,
        tool: str,
        operation: str,
        uid: int,
        pid: int
    ) -> tuple[bool, str]:
        """Check if access is allowed for the given tool/operation."""
        # Check UID first
        if uid not in self.allowed_uids:
            return False, f"UID {uid} not in allowed list"

        # Get tool policy
        tool_policy = self.tools.get(tool, {})

        # Check if tool is explicitly disabled
        if not tool_policy.get("enabled", True):
            return False, f"Tool '{tool}' is disabled"

        # Check operation permissions
        operations = tool_policy.get("operations", {})
        if operations:
            if operation not in operations:
                if self.default_deny:
                    return False, f"Operation '{operation}' not allowed for tool '{tool}'"
            else:
                if not operations[operation]:
                    return False, f"Operation '{operation}' explicitly denied for tool '{tool}'"

        return True, "Access granted"


# ============================================================================
# Credential Store
# ============================================================================

class CredentialStore:
    """Secure in-memory credential storage."""

    def __init__(self):
        self._secrets: dict[str, SecureSecret] = {}
        self._load_from_environment()

    def _load_from_environment(self) -> None:
        """Load credentials from environment and clear the env vars."""
        # Map of env var prefixes to credential names
        credential_map = {
            "GITHUB_TOKEN": "github",
            "GITLAB_TOKEN": "gitlab",
            "AWS_ACCESS_KEY_ID": "aws_access_key",
            "AWS_SECRET_ACCESS_KEY": "aws_secret_key",
            "NPM_TOKEN": "npm",
            "PYPI_TOKEN": "pypi",
            "DOCKER_TOKEN": "docker",
        }

        for env_var, cred_name in credential_map.items():
            value = os.environ.get(env_var)
            if value:
                self._secrets[cred_name] = SecureSecret(
                    name=cred_name,
                    _data=value.encode('utf-8')
                )
                # Clear from environment
                del os.environ[env_var]
                logger.info(f"Loaded credential '{cred_name}' and cleared from environment")

        # Also check for generic AGENT_SECRET_* pattern
        for key in list(os.environ.keys()):
            if key.startswith("AGENT_SECRET_"):
                cred_name = key[13:].lower()  # Strip prefix and lowercase
                value = os.environ[key]
                self._secrets[cred_name] = SecureSecret(
                    name=cred_name,
                    _data=value.encode('utf-8')
                )
                del os.environ[key]
                logger.info(f"Loaded credential '{cred_name}' from AGENT_SECRET_*")

    def get(self, name: str) -> Optional[str]:
        """Get a credential value."""
        secret = self._secrets.get(name)
        if secret:
            return secret.get_value()
        return None

    def has(self, name: str) -> bool:
        """Check if a credential exists."""
        return name in self._secrets

    def list_available(self) -> list[str]:
        """List available credential names (not values)."""
        return list(self._secrets.keys())

    def destroy_all(self) -> None:
        """Securely destroy all credentials."""
        for secret in self._secrets.values():
            secret.destroy()
        self._secrets.clear()
        logger.info("All credentials destroyed")


# ============================================================================
# Request Handlers
# ============================================================================

@dataclass
class PeerCredentials:
    """Credentials of the connecting process."""
    pid: int
    uid: int
    gid: int


def get_peer_credentials(conn: socket.socket) -> PeerCredentials:
    """Get the UID/GID/PID of the connecting process via SO_PEERCRED."""
    # SO_PEERCRED returns a struct ucred: pid_t, uid_t, gid_t (3 ints)
    cred = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    pid, uid, gid = struct.unpack('iii', cred)
    return PeerCredentials(pid=pid, uid=uid, gid=gid)


class RequestHandler:
    """Handle incoming credential requests."""

    def __init__(self, store: CredentialStore, policy: Policy):
        self.store = store
        self.policy = policy

    def handle(self, conn: socket.socket, request: dict) -> dict:
        """Process a request and return a response."""
        # Get peer credentials
        peer = get_peer_credentials(conn)

        action = request.get("action", "")
        tool = request.get("tool", "")
        operation = request.get("operation", "get")

        # Audit log
        if self.policy.audit_all:
            logger.info(
                f"Request: action={action} tool={tool} operation={operation} "
                f"from pid={peer.pid} uid={peer.uid}"
            )

        # Route to handler
        if action == "get":
            return self._handle_get(peer, tool, operation)
        elif action == "inject":
            return self._handle_inject(peer, tool, request)
        elif action == "sign":
            return self._handle_sign(peer, tool, request)
        elif action == "list":
            return self._handle_list(peer)
        elif action == "check":
            return self._handle_check(peer, tool, operation)
        elif action == "health":
            return {"status": "ok", "secrets_loaded": len(self.store.list_available())}
        else:
            return {"error": f"Unknown action: {action}"}

    def _handle_get(self, peer: PeerCredentials, tool: str, operation: str) -> dict:
        """Get a credential for a tool."""
        # Check policy
        allowed, reason = self.policy.check_access(tool, operation, peer.uid, peer.pid)
        if not allowed:
            logger.warning(f"Access denied for {tool}/{operation}: {reason}")
            return {"error": reason, "code": "ACCESS_DENIED"}

        # Get credential
        value = self.store.get(tool)
        if value is None:
            return {"error": f"No credential found for '{tool}'", "code": "NOT_FOUND"}

        logger.info(f"Credential '{tool}' provided to pid={peer.pid}")
        return {"value": value, "tool": tool}

    def _handle_inject(self, peer: PeerCredentials, tool: str, request: dict) -> dict:
        """Inject credentials into environment format for subprocess."""
        # Check policy
        operation = request.get("operation", "inject")
        allowed, reason = self.policy.check_access(tool, operation, peer.uid, peer.pid)
        if not allowed:
            logger.warning(f"Access denied for {tool}/{operation}: {reason}")
            return {"error": reason, "code": "ACCESS_DENIED"}

        # Build injection based on tool type
        if tool == "github":
            token = self.store.get("github")
            if not token:
                return {"error": "GitHub token not configured", "code": "NOT_FOUND"}

            return {
                "env": {
                    "GIT_ASKPASS": "echo",
                    "GIT_USERNAME": "x-access-token",
                    "GIT_PASSWORD": token,
                },
                "tool": tool,
            }

        elif tool == "aws":
            access_key = self.store.get("aws_access_key")
            secret_key = self.store.get("aws_secret_key")
            if not access_key or not secret_key:
                return {"error": "AWS credentials not configured", "code": "NOT_FOUND"}

            return {
                "env": {
                    "AWS_ACCESS_KEY_ID": access_key,
                    "AWS_SECRET_ACCESS_KEY": secret_key,
                },
                "tool": tool,
            }

        elif tool == "npm":
            token = self.store.get("npm")
            if not token:
                return {"error": "NPM token not configured", "code": "NOT_FOUND"}

            return {
                "env": {
                    "NPM_TOKEN": token,
                },
                "tool": tool,
            }

        else:
            # Generic credential injection
            value = self.store.get(tool)
            if value is None:
                return {"error": f"No credential found for '{tool}'", "code": "NOT_FOUND"}

            return {
                "env": {
                    f"{tool.upper()}_TOKEN": value,
                },
                "tool": tool,
            }

    def _handle_sign(self, peer: PeerCredentials, tool: str, request: dict) -> dict:
        """Sign data with a credential (without exposing the key)."""
        allowed, reason = self.policy.check_access(tool, "sign", peer.uid, peer.pid)
        if not allowed:
            return {"error": reason, "code": "ACCESS_DENIED"}

        data = request.get("data", "")
        if not data:
            return {"error": "No data to sign", "code": "INVALID_REQUEST"}

        # Get the signing key
        key = self.store.get(tool)
        if not key:
            return {"error": f"No signing key for '{tool}'", "code": "NOT_FOUND"}

        # Sign the data
        signature = hmac.new(
            key.encode('utf-8'),
            data.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()

        logger.info(f"Signed data for '{tool}' (pid={peer.pid})")
        return {"signature": signature, "algorithm": "hmac-sha256"}

    def _handle_list(self, peer: PeerCredentials) -> dict:
        """List available credentials (names only)."""
        # Anyone with valid UID can list
        if peer.uid not in self.policy.allowed_uids:
            return {"error": "Access denied", "code": "ACCESS_DENIED"}

        return {"credentials": self.store.list_available()}

    def _handle_check(self, peer: PeerCredentials, tool: str, operation: str) -> dict:
        """Check if access would be allowed (without getting credential)."""
        allowed, reason = self.policy.check_access(tool, operation, peer.uid, peer.pid)
        return {"allowed": allowed, "reason": reason, "tool": tool, "operation": operation}


# ============================================================================
# Socket Server
# ============================================================================

class CredentialAgent:
    """Main credential agent server."""

    def __init__(self):
        self.store = CredentialStore()
        self.policy = Policy.load(POLICY_PATH)
        self.handler = RequestHandler(self.store, self.policy)
        self.running = False
        self.sock: Optional[socket.socket] = None

    def _setup_socket(self) -> socket.socket:
        """Set up the Unix domain socket."""
        # Remove stale socket
        socket_path = Path(SOCKET_PATH)
        if socket_path.exists():
            socket_path.unlink()

        # Create socket
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(SOCKET_PATH)

        # Set permissions (owner read/write only)
        os.chmod(SOCKET_PATH, 0o660)

        sock.listen(10)
        sock.settimeout(1.0)  # Allow periodic checks for shutdown

        logger.info(f"Listening on {SOCKET_PATH}")
        return sock

    def _handle_connection(self, conn: socket.socket) -> None:
        """Handle a single connection."""
        try:
            conn.settimeout(5.0)
            data = conn.recv(8192)

            if not data:
                return

            try:
                request = json.loads(data.decode('utf-8'))
            except json.JSONDecodeError as e:
                response = {"error": f"Invalid JSON: {e}"}
                conn.send(json.dumps(response).encode('utf-8'))
                return

            response = self.handler.handle(conn, request)
            conn.send(json.dumps(response).encode('utf-8'))

        except socket.timeout:
            logger.warning("Connection timed out")
        except Exception as e:
            logger.error(f"Error handling connection: {e}")
            try:
                conn.send(json.dumps({"error": str(e)}).encode('utf-8'))
            except Exception:
                pass
        finally:
            conn.close()

    def _signal_handler(self, signum: int, frame: Any) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def run(self) -> None:
        """Run the credential agent."""
        # Set up signal handlers
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Prevent core dumps (which might contain secrets)
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except Exception:
            pass

        # Make process non-dumpable (prevents /proc/pid/mem access)
        try:
            import ctypes
            PR_SET_DUMPABLE = 4
            libc.prctl(PR_SET_DUMPABLE, 0)
            logger.info("Process set to non-dumpable")
        except Exception as e:
            logger.warning(f"Could not set non-dumpable: {e}")

        self.sock = self._setup_socket()
        self.running = True

        logger.info("Credential agent started")
        logger.info(f"Loaded {len(self.store.list_available())} credentials: {self.store.list_available()}")

        while self.running:
            try:
                conn, _ = self.sock.accept()
                self._handle_connection(conn)
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    logger.error(f"Error accepting connection: {e}")

        # Cleanup
        logger.info("Cleaning up...")
        self.store.destroy_all()
        if self.sock:
            self.sock.close()

        socket_path = Path(SOCKET_PATH)
        if socket_path.exists():
            socket_path.unlink()

        logger.info("Credential agent stopped")


def main():
    """Entry point."""
    logger.info("Starting Credential Agent")
    logger.info(f"Socket path: {SOCKET_PATH}")
    logger.info(f"Policy path: {POLICY_PATH}")
    logger.info(f"Allowed UIDs: {ALLOWED_UIDS}")
    logger.info(f"Debug mode: {DEBUG}")

    agent = CredentialAgent()
    agent.run()


if __name__ == "__main__":
    main()
