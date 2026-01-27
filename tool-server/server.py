#!/usr/bin/env python3
"""Tool Server - handles all tool execution requests.

Receives requests with {"tool": "git", "args": [...], "cwd": "..."}
and executes them with appropriate restrictions.

All validation and restrictions are enforced here, keeping the
client wrapper as simple as possible.

Uses the ToolCaller module for actual tool invocation, which supports
auto-discovery from the tools.d directory. Tools added after startup
are discovered lazily on first request — no server restart required.
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

from tool_caller import ToolCaller, ToolConfig, create_auto_caller

logger = logging.getLogger(__name__)

# Configuration
WORKSPACE = '/workspace'
MAX_MSG = 64 * 1024


class ToolServer:
    """Tool execution server that forwards commands to tools.

    Uses ToolCaller for actual tool invocation, allowing permission
    restrictions to be injected.
    """

    def __init__(
        self,
        socket_path: str,
        tool_caller: ToolCaller | None = None,
    ):
        self.socket_path = socket_path
        self._running = False
        self._server: socket.socket | None = None

        # Use provided caller or create default
        if tool_caller is None:
            self._caller = create_auto_caller(workspace=WORKSPACE)
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
        logger.info(f'Server listening on {self.socket_path}')

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
                    logger.error(f'Failed to accept connection: {type(e).__name__}: {e}')

        self._cleanup()

    def _shutdown(self, *_):
        """Handle shutdown signal."""
        logger.info('Received shutdown signal, stopping server')
        self._running = False

    def _cleanup(self):
        """Clean up resources."""
        if self._server:
            self._server.close()
        sock_file = Path(self.socket_path)
        if sock_file.exists():
            sock_file.unlink()
        logger.info('Server stopped, socket cleaned up')

    def _handle(self, conn: socket.socket):
        """Handle a client connection."""
        try:
            # Read request
            request = self._read(conn)
            if not request:
                return

            tool = request.get('tool', '?')
            logger.info(f'Request: tool={tool}, args={len(request.get("args", []))}')

            # Process and respond
            response = self._process(request)

            exit_code = response.get('exit_code', -1)
            has_error = bool(response.get('error'))
            log_fn = logger.warning if (exit_code != 0 or has_error) else logger.info
            log_fn(f'Response: tool={tool}, exit_code={exit_code}, error={has_error}')

            self._write(conn, response)

        except Exception as e:
            logger.exception(f'Connection handler failed: {type(e).__name__}: {e}')
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
                    logger.debug('Client disconnected before sending data')
                    return None
                length_data += chunk

            length = struct.unpack('>I', length_data)[0]
            if length > MAX_MSG:
                logger.warning(f'Rejected oversized message: {length} bytes (max={MAX_MSG})')
                return None

            # Read payload
            data = b''
            while len(data) < length:
                chunk = conn.recv(min(4096, length - len(data)))
                if not chunk:
                    logger.warning(f'Client disconnected mid-read: got {len(data)}/{length} bytes')
                    return None
                data += chunk

            return json.loads(data)
        except json.JSONDecodeError as e:
            logger.error(f'Failed to parse request JSON: {e}')
            return None
        except Exception as e:
            logger.error(f'Failed to read request: {type(e).__name__}: {e}')
            return None

    def _write(self, conn: socket.socket, response: dict):
        """Write response to connection."""
        try:
            payload = json.dumps(response).encode()
            conn.sendall(struct.pack('>I', len(payload)) + payload)
        except BrokenPipeError:
            logger.warning('Client disconnected before response could be sent')
        except Exception as e:
            logger.error(f'Failed to write response: {type(e).__name__}: {e}')

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
        RESTRICTED_DIR   - Directory for global wrapper scripts (default: /app/restricted)
        TOOLS_DIR        - Directory for tool definitions (default: /app/tools.d)
    """
    workspace = os.environ.get('WORKSPACE', WORKSPACE)
    restricted_dir = os.environ.get('RESTRICTED_DIR', '/app/restricted')
    tools_dir = os.environ.get('TOOLS_DIR', '/app/tools.d')

    logger.info(f'Configuration: workspace={workspace}, tools_dir={tools_dir}, restricted_dir={restricted_dir}')
    return create_auto_caller(
        tools_dir=tools_dir,
        workspace=workspace,
        restricted_dir=restricted_dir,
    )


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s [%(name)s] %(message)s',
    )

    socket_path = os.environ.get('TOOL_SOCKET')
    if not socket_path:
        logger.error('TOOL_SOCKET environment variable must be set')
        sys.exit(1)

    tool_caller = create_tool_caller()
    server = ToolServer(socket_path, tool_caller=tool_caller)

    logger.info('Starting tool server')
    server.start()


if __name__ == '__main__':
    main()
