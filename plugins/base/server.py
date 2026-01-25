"""Base plugin server implementation.

Provides Unix domain socket server with request handling,
connection management, and graceful shutdown.
"""

import os
import signal
import socket
import threading
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Optional

from .protocol import read_message, write_message, ProtocolError
from .security import SecureCredentials, verify_peer_uid

logger = logging.getLogger(__name__)


class PluginServer(ABC):
    """Base class for plugin socket servers.

    Subclasses must implement:
    - validate(): Check if command is allowed
    - execute(): Run the command
    - health(): Return health status
    - capabilities(): Return allowed operations
    """

    def __init__(
        self,
        socket_path: str,
        tool_name: str,
        config: Optional[dict[str, Any]] = None,
    ):
        """Initialize plugin server.

        Args:
            socket_path: Path for Unix domain socket
            tool_name: Name of this tool (e.g., 'git')
            config: Plugin configuration dictionary
        """
        self.socket_path = socket_path
        self.tool_name = tool_name
        self.config = config or {}
        self.credentials = SecureCredentials()
        self._running = False
        self._server_socket: Optional[socket.socket] = None
        self._threads: list[threading.Thread] = []

        # Load configuration defaults
        self._timeout = self.config.get('limits', {}).get('timeout_seconds', 300)
        self._max_output = self.config.get('limits', {}).get('max_output_bytes', 1048576)
        self._allowed_uids = self.config.get('access', {}).get('allowed_uids', [])
        self._socket_perms = self.config.get('access', {}).get('socket_permissions', 0o660)

    def load_credentials(self, env_vars: list[str], clear_env: bool = True) -> None:
        """Load credentials from environment variables.

        Args:
            env_vars: List of environment variable names
            clear_env: Whether to clear env vars after loading
        """
        self.credentials.load_from_env(env_vars, clear_env)
        if self.credentials.is_locked():
            logger.info("Credentials locked in memory")

    def start(self) -> None:
        """Start the plugin server."""
        # Remove existing socket
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            socket_file.unlink()

        # Create socket directory if needed
        socket_file.parent.mkdir(parents=True, exist_ok=True)

        # Create and bind socket
        self._server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server_socket.bind(self.socket_path)
        self._server_socket.listen(5)

        # Set socket permissions
        os.chmod(self.socket_path, self._socket_perms)

        self._running = True
        logger.info(f"{self.tool_name} plugin listening on {self.socket_path}")

        # Setup signal handlers
        signal.signal(signal.SIGTERM, self._handle_signal)
        signal.signal(signal.SIGINT, self._handle_signal)

        # Accept connections
        try:
            while self._running:
                try:
                    self._server_socket.settimeout(1.0)
                    conn, addr = self._server_socket.accept()
                    thread = threading.Thread(
                        target=self._handle_connection,
                        args=(conn,),
                        daemon=True,
                    )
                    thread.start()
                    self._threads.append(thread)
                except socket.timeout:
                    continue
        finally:
            self.stop()

    def stop(self) -> None:
        """Stop the plugin server."""
        self._running = False

        if self._server_socket:
            self._server_socket.close()
            self._server_socket = None

        # Clean up socket file
        socket_file = Path(self.socket_path)
        if socket_file.exists():
            socket_file.unlink()

        # Wait for threads
        for thread in self._threads:
            thread.join(timeout=5.0)

        logger.info(f"{self.tool_name} plugin stopped")

    def _handle_signal(self, signum: int, frame) -> None:
        """Handle shutdown signals."""
        logger.info(f"Received signal {signum}, shutting down...")
        self._running = False

    def _handle_connection(self, conn: socket.socket) -> None:
        """Handle a single client connection."""
        try:
            # Verify peer credentials if configured
            if self._allowed_uids:
                allowed, uid = verify_peer_uid(conn, self._allowed_uids)
                if not allowed:
                    logger.warning(f"Rejected connection from UID {uid}")
                    response = {
                        'success': False,
                        'error': f"Access denied for UID {uid}",
                    }
                    write_message(conn, response)
                    return

            # Read request
            try:
                request = read_message(conn)
            except ProtocolError as e:
                logger.error(f"Protocol error: {e}")
                return

            # Process request
            response = self._process_request(request)

            # Send response
            write_message(conn, response)

        except Exception as e:
            logger.exception(f"Error handling connection: {e}")
        finally:
            conn.close()

    def _process_request(self, request: dict[str, Any]) -> dict[str, Any]:
        """Process a request and return response."""
        action = request.get('action', 'exec')

        if action == 'health':
            return self.health()

        if action == 'capabilities':
            return self.capabilities()

        if action == 'exec':
            args = request.get('args', [])
            cwd = request.get('cwd', '/workspace')
            env = request.get('env', {})

            # Validate command
            allowed, reason = self.validate(args, cwd)
            if not allowed:
                logger.info(f"Blocked command: {args} - {reason}")
                return {
                    'success': False,
                    'exit_code': 1,
                    'stdout': '',
                    'stderr': '',
                    'error': reason,
                }

            # Execute command
            try:
                result = self.execute(args, cwd, env)
                return {
                    'success': result.get('exit_code', 0) == 0,
                    **result,
                }
            except Exception as e:
                logger.exception(f"Execution error: {e}")
                return {
                    'success': False,
                    'exit_code': 1,
                    'stdout': '',
                    'stderr': str(e),
                    'error': f"Execution failed: {e}",
                }

        return {
            'success': False,
            'error': f"Unknown action: {action}",
        }

    @abstractmethod
    def validate(self, args: list[str], cwd: str) -> tuple[bool, str]:
        """Validate if command is allowed.

        Args:
            args: Command arguments
            cwd: Working directory

        Returns:
            Tuple of (allowed, reason)
        """
        pass

    @abstractmethod
    def execute(self, args: list[str], cwd: str, env: dict[str, str]) -> dict[str, Any]:
        """Execute command and return result.

        Args:
            args: Command arguments
            cwd: Working directory
            env: Additional environment variables

        Returns:
            Dictionary with exit_code, stdout, stderr
        """
        pass

    @abstractmethod
    def health(self) -> dict[str, Any]:
        """Return health status.

        Returns:
            Dictionary with success and status info
        """
        pass

    @abstractmethod
    def capabilities(self) -> dict[str, Any]:
        """Return what operations are allowed.

        Returns:
            Dictionary describing allowed operations
        """
        pass
