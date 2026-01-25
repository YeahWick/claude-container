#!/usr/bin/env python3
"""Unified CLI server - handles all tool execution requests.

Receives requests with {"tool": "git", "args": [...], "cwd": "..."}
and executes them with appropriate restrictions.

All validation and restrictions are enforced here, keeping the
client wrapper as simple as possible.
"""

import json
import logging
import os
import signal
import socket
import struct
import subprocess
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

# Configuration
SOCKET_PATH = '/run/plugins/cli.sock'
WORKSPACE = '/workspace'
MAX_MSG = 64 * 1024

# Tool configurations - add new tools here
ALLOWED_TOOLS = {
    'git': {
        'binary': '/usr/bin/git',
        'timeout': 300,
    },
    # Easy to add more tools:
    # 'npm': {'binary': '/usr/bin/npm', 'timeout': 600},
    # 'cargo': {'binary': '/usr/bin/cargo', 'timeout': 600},
}


class CLIServer:
    """Simple CLI server that forwards commands to tools."""

    def __init__(self, socket_path: str = SOCKET_PATH):
        self.socket_path = socket_path
        self._running = False
        self._server: socket.socket | None = None

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
        """Process a request and return response."""
        tool = request.get('tool', '')
        args = request.get('args', [])
        cwd = request.get('cwd', WORKSPACE)

        # Check tool is allowed
        if tool not in ALLOWED_TOOLS:
            return {
                'exit_code': 1,
                'stdout': '',
                'stderr': '',
                'error': f"Unknown tool: {tool}",
            }

        config = ALLOWED_TOOLS[tool]
        binary = config['binary']
        timeout = config.get('timeout', 300)

        # Validate binary exists
        if not Path(binary).exists():
            return {
                'exit_code': 127,
                'stdout': '',
                'stderr': '',
                'error': f"Tool not installed: {tool}",
            }

        # Validate cwd
        cwd_path = Path(cwd)
        if not cwd_path.exists():
            cwd = WORKSPACE

        # Execute command
        try:
            cmd = [binary] + args
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
            return {
                'exit_code': result.returncode,
                'stdout': result.stdout.decode('utf-8', errors='replace'),
                'stderr': result.stderr.decode('utf-8', errors='replace'),
            }
        except subprocess.TimeoutExpired:
            return {
                'exit_code': 124,
                'stdout': '',
                'stderr': f'Command timed out after {timeout}s',
                'error': 'Timeout',
            }
        except Exception as e:
            return {
                'exit_code': 1,
                'stdout': '',
                'stderr': str(e),
                'error': f'Execution failed: {e}',
            }


def main():
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    socket_path = os.environ.get('CLI_SOCKET', SOCKET_PATH)
    server = CLIServer(socket_path)

    logger.info('Starting CLI server')
    server.start()


if __name__ == '__main__':
    main()
