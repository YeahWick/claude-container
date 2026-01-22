"""
Tools package for Claude Code Proxy.

Each tool module should expose:
- router: FastAPI APIRouter instance
- TOOL_INFO: dict with 'name', 'description', and optionally 'version'
"""

from .base import BaseTool, ToolResponse, ToolError

__all__ = ["BaseTool", "ToolResponse", "ToolError"]
