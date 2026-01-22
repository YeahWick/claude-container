"""
Configuration management for the Claude Code Proxy.

Configuration can be provided via:
1. Environment variables (prefixed with PROXY_)
2. Configuration file (config.yaml)
3. Default values
"""

import os
from pathlib import Path
from typing import Any

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings


class ProxySettings(BaseSettings):
    """Main proxy configuration settings."""

    # Server settings
    host: str = Field(default="0.0.0.0", description="Server host")
    port: int = Field(default=8080, description="Server port")
    debug: bool = Field(default=False, description="Enable debug mode")

    # GitHub settings
    github_token: str = Field(default="", description="GitHub personal access token")
    github_blocked_branches: list[str] = Field(
        default=["main", "master"],
        description="Branches that cannot be pushed to",
    )
    github_allowed_repos: list[str] = Field(
        default=[],
        description="List of allowed repositories (empty = all allowed)",
    )
    github_blocked_repos: list[str] = Field(
        default=[],
        description="List of blocked repositories",
    )

    # General settings
    allowed_tools: list[str] = Field(
        default=[],
        description="List of allowed tools (empty = all allowed)",
    )
    blocked_tools: list[str] = Field(
        default=[],
        description="List of blocked tools",
    )

    class Config:
        env_prefix = "PROXY_"
        env_file = ".env"
        extra = "ignore"

    def __init__(self, **kwargs):
        # Load from config file first
        config_file = Path("/app/config.yaml")
        file_config = {}
        if config_file.exists():
            try:
                with open(config_file) as f:
                    file_config = yaml.safe_load(f) or {}
            except Exception as e:
                print(f"Warning: Failed to load config file: {e}")

        # Merge file config with kwargs (kwargs take precedence)
        merged = {**file_config, **kwargs}
        super().__init__(**merged)


def load_tool_config(tool_name: str) -> dict[str, Any]:
    """Load configuration specific to a tool."""
    config_file = Path(f"/app/tools/{tool_name}.yaml")
    if config_file.exists():
        try:
            with open(config_file) as f:
                return yaml.safe_load(f) or {}
        except Exception:
            pass
    return {}


# Global settings instance
settings = ProxySettings()
