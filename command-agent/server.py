#!/usr/bin/env python3
"""
Command Agent - Secure socket-based command execution.

This agent executes restricted commands (git, gh, curl) on behalf of the
claude container, with credentials and policy enforcement.

Security features:
1. Memory Locking: Secrets stored in mlock'd memory (no swap)
2. Process Isolation: Credentials cleared from environment after loading
3. SO_PEERCRED: Caller verification via kernel-level credentials
4. Policy Enforcement: Branch protection, allowed commands
5. No credential exposure: Commands run here, not in claude container
"""

import ctypes
import fnmatch
import json
import logging
import os
import re
import shlex
import signal
import socket
import struct
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Configuration
SOCKET_PATH = os.environ.get("AGENT_SOCKET_PATH", "/run/agent/cmd.sock")
ALLOWED_UIDS = [int(uid) for uid in os.environ.get("AGENT_ALLOWED_UIDS", "1000").split(",")]
DEBUG = os.environ.get("AGENT_DEBUG", "false").lower() == "true"

# Branch protection
BLOCKED_BRANCHES = json.loads(os.environ.get("BLOCKED_BRANCHES", '["main", "master"]'))
ALLOWED_BRANCH_PATTERNS = json.loads(os.environ.get("ALLOWED_BRANCH_PATTERNS", "[]"))

# Logging
logging.basicConfig(
    level=logging.DEBUG if DEBUG else logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger(__name__)


# ============================================================================
# Secure Memory Management
# ============================================================================

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
        buf = ctypes.create_string_buffer(data, len(data))
        result = libc.mlock(ctypes.addressof(buf), len(data))
        if result != 0:
            errno = ctypes.get_errno()
            logger.warning(f"mlock failed with errno {errno}")
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
        ctypes.memset(ctypes.addressof(buf), 0, size)
        libc.munlock(ctypes.addressof(buf), size)
    except Exception as e:
        logger.warning(f"Failed to munlock memory: {e}")


@dataclass
class SecureSecret:
    """A secret stored in locked memory."""
    name: str
    _data: bytes = field(repr=False)
    _locked_buf: Optional[ctypes.Array] = field(default=None, repr=False)

    def __post_init__(self):
        self._locked_buf = mlock_bytes(self._data)

    def get_value(self) -> str:
        if self._locked_buf:
            return self._locked_buf.value.decode('utf-8')
        return self._data.decode('utf-8')

    def destroy(self) -> None:
        if self._locked_buf:
            munlock_bytes(self._locked_buf, len(self._data))
            self._locked_buf = None
        self._data = b'\x00' * len(self._data)


class CredentialStore:
    """Secure in-memory credential storage."""

    def __init__(self):
        self._secrets: dict[str, SecureSecret] = {}
        self._load_from_environment()

    def _load_from_environment(self) -> None:
        """Load credentials from environment and clear the env vars."""
        credential_map = {
            "GITHUB_TOKEN": "github",
            "GH_TOKEN": "gh",
            "GITLAB_TOKEN": "gitlab",
        }

        for env_var, cred_name in credential_map.items():
            value = os.environ.get(env_var)
            if value:
                self._secrets[cred_name] = SecureSecret(name=cred_name, _data=value.encode('utf-8'))
                del os.environ[env_var]
                logger.info(f"Loaded credential '{cred_name}' and cleared from environment")

        # Copy github to gh if gh not separately set
        if "github" in self._secrets and "gh" not in self._secrets:
            self._secrets["gh"] = self._secrets["github"]

    def get(self, name: str) -> Optional[str]:
        secret = self._secrets.get(name)
        return secret.get_value() if secret else None

    def list_available(self) -> list[str]:
        return list(self._secrets.keys())

    def destroy_all(self) -> None:
        for secret in self._secrets.values():
            secret.destroy()
        self._secrets.clear()


# ============================================================================
# Branch Protection
# ============================================================================

def check_branch_allowed(branch: str) -> tuple[bool, str]:
    """Check if operations on this branch are allowed."""
    # Blocked branches always blocked
    if branch in BLOCKED_BRANCHES:
        return False, f"Branch '{branch}' is protected"

    # If allowlist mode, must match a pattern
    if ALLOWED_BRANCH_PATTERNS:
        for pattern in ALLOWED_BRANCH_PATTERNS:
            if fnmatch.fnmatch(branch, pattern):
                return True, "Allowed by pattern"
        return False, f"Branch '{branch}' does not match allowed patterns"

    return True, "Allowed"


def extract_push_branch(args: list[str]) -> Optional[str]:
    """Extract the branch name from git push arguments."""
    # git push [options] [remote] [refspec...]
    # Common patterns:
    #   git push origin main
    #   git push origin feature-branch
    #   git push -u origin feature-branch
    #   git push (uses current branch)

    skip_next = False
    non_option_args = []

    for arg in args:
        if skip_next:
            skip_next = False
            continue
        if arg in ['-u', '--set-upstream', '-f', '--force', '--force-with-lease',
                   '-n', '--dry-run', '-v', '--verbose', '-q', '--quiet',
                   '--all', '--tags', '--delete', '--prune']:
            continue
        if arg.startswith('-'):
            # Options with values
            if arg in ['-o', '--push-option', '--repo', '--receive-pack', '--exec']:
                skip_next = True
            continue
        non_option_args.append(arg)

    # non_option_args should be [remote, refspec...] or just [refspec...]
    if len(non_option_args) >= 2:
        refspec = non_option_args[1]
        # Handle refspec formats: branch, src:dst, :dst (delete)
        if ':' in refspec:
            dst = refspec.split(':')[1]
            return dst if dst else None
        return refspec
    elif len(non_option_args) == 1:
        # Could be remote name or branch, depends on context
        # If it looks like a remote (origin, upstream), return None (will push current branch)
        if non_option_args[0] in ['origin', 'upstream']:
            return None
        return non_option_args[0]

    return None


def get_current_branch(cwd: str) -> Optional[str]:
    """Get the current git branch."""
    try:
        result = subprocess.run(
            ['git', 'branch', '--show-current'],
            capture_output=True, text=True, cwd=cwd, timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except Exception:
        pass
    return None


# ============================================================================
# Command Execution
# ============================================================================

ALLOWED_COMMANDS = {'git', 'gh', 'curl'}
MAX_OUTPUT_SIZE = 1024 * 1024  # 1MB


def validate_command(cmd: str, args: list[str], cwd: str) -> tuple[bool, str]:
    """Validate a command before execution."""
    if cmd not in ALLOWED_COMMANDS:
        return False, f"Command '{cmd}' not allowed. Allowed: {ALLOWED_COMMANDS}"

    # Git-specific validation
    if cmd == 'git':
        if args and args[0] == 'push':
            branch = extract_push_branch(args[1:])
            if branch is None:
                branch = get_current_branch(cwd)
            if branch:
                allowed, reason = check_branch_allowed(branch)
                if not allowed:
                    return False, reason

        # Block dangerous operations
        if args and args[0] in ['config', 'remote'] and '--global' in args:
            return False, "Global git config changes not allowed"

    # gh-specific validation
    if cmd == 'gh':
        # Block dangerous gh operations
        if args and args[0] in ['auth', 'config']:
            return False, f"gh {args[0]} not allowed"

    return True, "OK"


def execute_command(cmd: str, args: list[str], cwd: str, store: CredentialStore) -> dict:
    """Execute a command with credentials."""
    # Build environment with credentials
    env = os.environ.copy()

    if cmd == 'git':
        token = store.get('github')
        if token:
            # Use credential helper approach
            env['GIT_ASKPASS'] = '/bin/echo'
            env['GIT_USERNAME'] = 'x-access-token'
            env['GIT_PASSWORD'] = token
            # Also set for HTTPS URLs
            env['GIT_TERMINAL_PROMPT'] = '0'

    elif cmd == 'gh':
        token = store.get('gh') or store.get('github')
        if token:
            env['GH_TOKEN'] = token

    elif cmd == 'curl':
        # For curl, credentials should be passed in args if needed
        pass

    # Execute
    try:
        full_cmd = [cmd] + args
        logger.info(f"Executing: {' '.join(shlex.quote(a) for a in full_cmd)} in {cwd}")

        result = subprocess.run(
            full_cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            timeout=300  # 5 minute timeout
        )

        stdout = result.stdout
        stderr = result.stderr

        # Truncate if too large
        if len(stdout) > MAX_OUTPUT_SIZE:
            stdout = stdout[:MAX_OUTPUT_SIZE] + "\n... (truncated)"
        if len(stderr) > MAX_OUTPUT_SIZE:
            stderr = stderr[:MAX_OUTPUT_SIZE] + "\n... (truncated)"

        return {
            "exit_code": result.returncode,
            "stdout": stdout,
            "stderr": stderr,
        }

    except subprocess.TimeoutExpired:
        return {"exit_code": 124, "stdout": "", "stderr": "Command timed out"}
    except FileNotFoundError:
        return {"exit_code": 127, "stdout": "", "stderr": f"Command not found: {cmd}"}
    except Exception as e:
        return {"exit_code": 1, "stdout": "", "stderr": str(e)}


# ============================================================================
# Socket Server
# ============================================================================

@dataclass
class PeerCredentials:
    pid: int
    uid: int
    gid: int


def get_peer_credentials(conn: socket.socket) -> PeerCredentials:
    """Get the UID/GID/PID of the connecting process via SO_PEERCRED."""
    cred = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12)
    pid, uid, gid = struct.unpack('iii', cred)
    return PeerCredentials(pid=pid, uid=uid, gid=gid)


class CommandAgent:
    """Main command agent server."""

    def __init__(self):
        self.store = CredentialStore()
        self.running = False
        self.sock: Optional[socket.socket] = None

    def handle_request(self, conn: socket.socket, request: dict) -> dict:
        """Process a request and return a response."""
        peer = get_peer_credentials(conn)

        # Check UID
        if peer.uid not in ALLOWED_UIDS:
            logger.warning(f"Access denied for UID {peer.uid}")
            return {"error": f"Access denied for UID {peer.uid}", "exit_code": 1}

        action = request.get("action", "exec")

        if action == "health":
            return {
                "status": "ok",
                "credentials": self.store.list_available(),
                "blocked_branches": BLOCKED_BRANCHES,
                "allowed_patterns": ALLOWED_BRANCH_PATTERNS,
            }

        if action == "exec":
            cmd = request.get("cmd", "")
            args = request.get("args", [])
            cwd = request.get("cwd", "/workspace")

            if not cmd:
                return {"error": "No command specified", "exit_code": 1}

            # Validate
            allowed, reason = validate_command(cmd, args, cwd)
            if not allowed:
                logger.warning(f"Command rejected: {reason}")
                return {"error": reason, "exit_code": 1}

            # Execute
            logger.info(f"Request from pid={peer.pid}: {cmd} {' '.join(args)}")
            return execute_command(cmd, args, cwd, self.store)

        return {"error": f"Unknown action: {action}", "exit_code": 1}

    def _setup_socket(self) -> socket.socket:
        """Set up the Unix domain socket."""
        socket_path = Path(SOCKET_PATH)
        if socket_path.exists():
            socket_path.unlink()

        # Ensure parent directory exists
        socket_path.parent.mkdir(parents=True, exist_ok=True)

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.bind(SOCKET_PATH)
        os.chmod(SOCKET_PATH, 0o660)
        sock.listen(10)
        sock.settimeout(1.0)

        logger.info(f"Listening on {SOCKET_PATH}")
        return sock

    def _handle_connection(self, conn: socket.socket) -> None:
        """Handle a single connection."""
        try:
            conn.settimeout(310.0)  # Slightly longer than command timeout
            data = conn.recv(65536)

            if not data:
                return

            try:
                request = json.loads(data.decode('utf-8'))
            except json.JSONDecodeError as e:
                response = {"error": f"Invalid JSON: {e}", "exit_code": 1}
                conn.send(json.dumps(response).encode('utf-8'))
                return

            response = self.handle_request(conn, request)
            conn.send(json.dumps(response).encode('utf-8'))

        except socket.timeout:
            logger.warning("Connection timed out")
        except Exception as e:
            logger.error(f"Error handling connection: {e}")
            try:
                conn.send(json.dumps({"error": str(e), "exit_code": 1}).encode('utf-8'))
            except Exception:
                pass
        finally:
            conn.close()

    def _signal_handler(self, signum: int, frame: Any) -> None:
        logger.info(f"Received signal {signum}, shutting down...")
        self.running = False

    def run(self) -> None:
        """Run the command agent."""
        signal.signal(signal.SIGTERM, self._signal_handler)
        signal.signal(signal.SIGINT, self._signal_handler)

        # Prevent core dumps
        try:
            import resource
            resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
        except Exception:
            pass

        # Make non-dumpable
        try:
            PR_SET_DUMPABLE = 4
            libc.prctl(PR_SET_DUMPABLE, 0)
        except Exception:
            pass

        self.sock = self._setup_socket()
        self.running = True

        logger.info("Command agent started")
        logger.info(f"Credentials loaded: {self.store.list_available()}")
        logger.info(f"Blocked branches: {BLOCKED_BRANCHES}")
        logger.info(f"Allowed patterns: {ALLOWED_BRANCH_PATTERNS}")

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
        self.store.destroy_all()
        if self.sock:
            self.sock.close()
        socket_path = Path(SOCKET_PATH)
        if socket_path.exists():
            socket_path.unlink()
        logger.info("Command agent stopped")


def main():
    logger.info("Starting Command Agent")
    logger.info(f"Socket: {SOCKET_PATH}")
    logger.info(f"Allowed UIDs: {ALLOWED_UIDS}")
    agent = CommandAgent()
    agent.run()


if __name__ == "__main__":
    main()
