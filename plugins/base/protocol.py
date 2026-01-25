"""Protocol implementation for plugin socket communication.

Message format: 4-byte big-endian length prefix + JSON payload
Max message size: 64KB
"""

import json
import struct
from typing import Any

MAX_MESSAGE_SIZE = 64 * 1024  # 64KB
LENGTH_PREFIX_SIZE = 4


class ProtocolError(Exception):
    """Raised when protocol encoding/decoding fails."""
    pass


def encode_message(data: dict[str, Any]) -> bytes:
    """Encode a dictionary as a length-prefixed JSON message.

    Args:
        data: Dictionary to encode

    Returns:
        Length-prefixed JSON bytes

    Raises:
        ProtocolError: If message exceeds max size
    """
    payload = json.dumps(data, separators=(',', ':')).encode('utf-8')

    if len(payload) > MAX_MESSAGE_SIZE:
        raise ProtocolError(f"Message size {len(payload)} exceeds max {MAX_MESSAGE_SIZE}")

    length_prefix = struct.pack('>I', len(payload))
    return length_prefix + payload


def decode_message(data: bytes) -> dict[str, Any]:
    """Decode a JSON payload (without length prefix).

    Args:
        data: JSON bytes to decode

    Returns:
        Decoded dictionary

    Raises:
        ProtocolError: If JSON is invalid
    """
    try:
        return json.loads(data.decode('utf-8'))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        raise ProtocolError(f"Invalid JSON: {e}")


def read_message(sock) -> dict[str, Any]:
    """Read a complete message from a socket.

    Args:
        sock: Socket to read from

    Returns:
        Decoded message dictionary

    Raises:
        ProtocolError: If read fails or message is invalid
    """
    # Read length prefix
    length_bytes = _recv_exact(sock, LENGTH_PREFIX_SIZE)
    if not length_bytes:
        raise ProtocolError("Connection closed")

    length = struct.unpack('>I', length_bytes)[0]

    if length > MAX_MESSAGE_SIZE:
        raise ProtocolError(f"Message size {length} exceeds max {MAX_MESSAGE_SIZE}")

    # Read payload
    payload = _recv_exact(sock, length)
    if not payload:
        raise ProtocolError("Connection closed during message read")

    return decode_message(payload)


def write_message(sock, data: dict[str, Any]) -> None:
    """Write a message to a socket.

    Args:
        sock: Socket to write to
        data: Dictionary to send
    """
    message = encode_message(data)
    sock.sendall(message)


def _recv_exact(sock, size: int) -> bytes | None:
    """Read exactly size bytes from socket.

    Args:
        sock: Socket to read from
        size: Number of bytes to read

    Returns:
        Bytes read, or None if connection closed
    """
    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)
