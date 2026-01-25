#!/usr/bin/env python3
"""Unified CLI server - handles all tool execution requests.

Receives requests with {"tool": "git", "args": [...], "cwd": "..."}
and executes them with appropriate restrictions.

All validation and restrictions are enforced here, keeping the
client wrapper as simple as possible.

Uses the ToolCaller module for actual tool invocation, which allows
injecting permission restrictions and audit logging.
"""

import json
import logging
import os
import signal
import socket
import struct
import sys
import threading
from pathlib import Path

# Add app directory to path for imports
sys.path.insert(0, '/app')

from tool_caller import ToolCaller, ToolConfig, create_default_caller

logger = logging.getLogger(__name__)

# Configuration
SOCKET_PATH = '/run/plugins/cli.sock'
WORKSPACE = '/workspace'
MAX_MSG = 64 * 1024


class CLIServer:
    """Simple CLI server that forwards commands to tools.

    Uses ToolCaller for actual tool invocation, allowing permission
    restrictions to be injected.
    """

    def __init__(
        self,
        socket_path: str = SOCKET_PATH,
        tool_caller: ToolCaller | None = None,
    ):
        self.socket_path = socket_path
        self._running = False
        self._server: socket.socket | None = None

        # Use provided caller or create default
        if tool_caller is None:
            self._caller = create_default_caller(workspace=WORKSPACE)
        else:
            self._caller = tool_caller

    def start(self):
        """Start the server."""
        # Clean up old socket
        sock_file = Path(self.socket_path)
        if sock_file.exists():
            sock_file.unlink()
        sock_file.parent.mkdir(parents=True, exist_ok=True)

        # Create socket
        self._server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self._server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._server.bind(self.socket_path)
        self._server.listen(5)
        os.chmod(self.socket_path, 0o660)

        self._running = True
        logger.info(f'CLI server listening on {self.socket_path}')

        # Signal handlers
        signal.signal(signal.SIGTERM, self._shutdown)
        signal.signal(signal.SIGINT, self._shutdown)

        # Accept loop
        while self._running:
            try:
                self._server.settimeout(1.0)
                conn, _ = self._server.accept()
                threading.Thread(
                    target=self._handle,
                    args=(conn,),
                    daemon=True
                ).start()
            except socket.timeout:
                continue
            except Exception as e:
                if self._running:
                    logger.error(f'Accept error: {e}')

        self._cleanup()

    def _shutdown(self, *_):
        """Handle shutdown signal."""
        logger.info('Shutting down...')
        self._running = False

    def _cleanup(self):
        """Clean up resources."""
        if self._server:
            self._server.close()
        sock_file = Path(self.socket_path)
        if sock_file.exists():
            sock_file.unlink()

    def _handle(self, conn: socket.socket):
        """Handle a client connection."""
        try:
            # Read request
            request = self._read(conn)
            if not request:
                return

            # Process and respond
            response = self._process(request)
            self._write(conn, response)

        except Exception as e:
            logger.exception(f'Handler error: {e}')
        finally:
            conn.close()

    def _read(self, conn: socket.socket) -> dict | None:
        """Read a request from connection."""
        try:
            # Read length prefix
            length_data = b''
            while len(length_data) < 4:
                chunk = conn.recv(4 - len(length_data))
                if not chunk:
                    return None
                length_data += chunk

            length = struct.unpack('>I', length_data)[0]
            if length > MAX_MSG:
                return None

            # Read payload
            data = b''
            while len(data) < length:
                chunk = conn.recv(min(4096, length - len(data)))
                if not chunk:
                    return None
                data += chunk

            return json.loads(data)
        except Exception as e:
            logger.error(f'Read error: {e}')
            return None

    def _write(self, conn: socket.socket, response: dict):
        """Write response to connection."""
        try:
            payload = json.dumps(response).encode()
            conn.sendall(struct.pack('>I', len(payload)) + payload)
        except Exception as e:
            logger.error(f'Write error: {e}')

    def _process(self, request: dict) -> dict:
        """Process a request and return response.

        Delegates to ToolCaller for actual execution, which handles
        permission checks and tool invocation.
        """
        tool = request.get('tool', '')
        args = request.get('args', [])
        cwd = request.get('cwd', WORKSPACE)

        # Delegate to tool caller
        result = self._caller.call(tool, args, cwd)
        return result.to_dict()


def create_tool_caller() -> ToolCaller:
    """Create the tool caller with configuration from environment.

    Environment variables:
        WORKSPACE        - Working directory (default: /workspace)
        RESTRICTED_DIR   - Directory for wrapper scripts (default: /app/restricted)

    If wrapper scripts exist in RESTRICTED_DIR matching the tool name
    (e.g., git.sh or git.py), they will be called instead of the real
    binary. The wrapper decides what to allow.
    """
    workspace = os.environ.get('WORKSPACE', WORKSPACE)
    restricted_dir = os.environ.get('RESTRICTED_DIR', '/app/restricted')

    logger.info(f'Tool caller: workspace={workspace}, restricted_dir={restricted_dir}')
    return create_default_caller(workspace=workspace, restricted_dir=restricted_dir)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    socket_path = os.environ.get('CLI_SOCKET', SOCKET_PATH)
    tool_caller = create_tool_caller()
    server = CLIServer(socket_path, tool_caller=tool_caller)

    logger.info('Starting CLI server')
    server.start()


if __name__ == '__main__':
    main()
