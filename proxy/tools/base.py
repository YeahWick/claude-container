"""
Base classes and utilities for proxy tools.
"""

from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class ToolResponse:
    """Standard response format for tool operations."""

    success: bool
    message: str
    data: Optional[dict[str, Any]] = None
    errors: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        result = {
            "success": self.success,
            "message": self.message,
        }
        if self.data:
            result["data"] = self.data
        if self.errors:
            result["errors"] = self.errors
        return result


class ToolError(Exception):
    """Base exception for tool errors."""

    def __init__(self, message: str, code: str = "TOOL_ERROR", details: Optional[dict] = None):
        self.message = message
        self.code = code
        self.details = details or {}
        super().__init__(message)

    def to_dict(self) -> dict[str, Any]:
        return {
            "error": self.code,
            "message": self.message,
            "details": self.details,
        }


class BaseTool:
    """Base class for proxy tools."""

    name: str = "base"
    description: str = "Base tool class"
    version: str = "1.0.0"

    def __init__(self, config: Optional[dict] = None):
        self.config = config or {}

    def validate_access(self, **kwargs) -> bool:
        """Validate if the operation is allowed. Override in subclasses."""
        return True

    def get_info(self) -> dict[str, Any]:
        """Get tool information."""
        return {
            "name": self.name,
            "description": self.description,
            "version": self.version,
        }
