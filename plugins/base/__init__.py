"""Plugin base library for socket-based tool plugins."""

from .protocol import encode_message, decode_message, ProtocolError
from .server import PluginServer
from .security import SecureCredentials

__all__ = [
    'encode_message',
    'decode_message',
    'ProtocolError',
    'PluginServer',
    'SecureCredentials',
]
