#!/usr/bin/env python3
"""Tool Server Caller - handles tool binary invocation with permission hooks.

By default, calls the CLI tool binary as-is. Can be extended to inject
permission restrictions, argument validation, and audit logging.

Usage:
    from tool_caller import ToolCaller

    caller = ToolCaller()
    result = caller.call('git', ['push', 'origin', 'main'], cwd='/workspace')
"""

import logging
import os
import subprocess
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

logger = logging.getLogger(__name__)


@dataclass
class ToolResult:
    """Result of a tool invocation."""
    exit_code: int
    stdout: str
    stderr: str
    error: str | None = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = {
            'exit_code': self.exit_code,
            'stdout': self.stdout,
            'stderr': self.stderr,
        }
        if self.error:
            result['error'] = self.error
        return result


@dataclass
class ToolConfig:
    """Configuration for a tool."""
    binary: str
    timeout: int = 300
    allowed_subcommands: list[str] | None = None  # None = all allowed
    denied_subcommands: list[str] | None = None
    allowed_args_patterns: list[str] | None = None
    denied_args_patterns: list[str] | None = None
    env_overrides: dict[str, str] = field(default_factory=dict)


class PermissionChecker(ABC):
    """Abstract base class for permission checkers."""

    @abstractmethod
    def check(self, tool: str, args: list[str], cwd: str, config: ToolConfig) -> tuple[bool, str | None]:
        """Check if the command is allowed.

        Returns:
            (allowed, error_message) - If allowed is False, error_message explains why.
        """
        pass


class DefaultPermissionChecker(PermissionChecker):
    """Default permission checker - allows all commands."""

    def check(self, tool: str, args: list[str], cwd: str, config: ToolConfig) -> tuple[bool, str | None]:
        """Default: allow everything."""
        return True, None


class SubcommandPermissionChecker(PermissionChecker):
    """Permission checker that validates subcommands."""

    def check(self, tool: str, args: list[str], cwd: str, config: ToolConfig) -> tuple[bool, str | None]:
        """Check subcommand permissions."""
        if not args:
            return True, None

        subcommand = args[0]

        # Check denied subcommands first
        if config.denied_subcommands and subcommand in config.denied_subcommands:
            return False, f"Subcommand '{subcommand}' is not allowed for {tool}"

        # Check allowed subcommands if specified
        if config.allowed_subcommands is not None:
            if subcommand not in config.allowed_subcommands:
                return False, f"Subcommand '{subcommand}' is not in allowed list for {tool}"

        return True, None


class WorkspacePermissionChecker(PermissionChecker):
    """Permission checker that validates working directory is within workspace."""

    def __init__(self, workspace: str = '/workspace'):
        self.workspace = Path(workspace).resolve()

    def check(self, tool: str, args: list[str], cwd: str, config: ToolConfig) -> tuple[bool, str | None]:
        """Check that cwd is within workspace."""
        try:
            cwd_path = Path(cwd).resolve()
            # Check if cwd is within workspace
            cwd_path.relative_to(self.workspace)
            return True, None
        except ValueError:
            return False, f"Working directory must be within {self.workspace}"


class CompositePermissionChecker(PermissionChecker):
    """Combines multiple permission checkers."""

    def __init__(self, checkers: list[PermissionChecker]):
        self.checkers = checkers

    def check(self, tool: str, args: list[str], cwd: str, config: ToolConfig) -> tuple[bool, str | None]:
        """Run all checkers, fail if any fails."""
        for checker in self.checkers:
            allowed, error = checker.check(tool, args, cwd, config)
            if not allowed:
                return False, error
        return True, None


class ToolCaller:
    """Handles tool binary invocation with extensible permission checks.

    By default, calls the CLI tool binary as-is. Permission checkers can be
    added to inject restrictions.
    """

    def __init__(
        self,
        tools: dict[str, ToolConfig] | None = None,
        permission_checker: PermissionChecker | None = None,
        workspace: str = '/workspace',
        pre_call_hook: Callable[[str, list[str], str], None] | None = None,
        post_call_hook: Callable[[str, list[str], str, ToolResult], None] | None = None,
    ):
        """Initialize the tool caller.

        Args:
            tools: Tool configurations. If None, uses default configurations.
            permission_checker: Permission checker to use. If None, uses DefaultPermissionChecker.
            workspace: Default workspace directory.
            pre_call_hook: Optional function called before tool execution.
            post_call_hook: Optional function called after tool execution.
        """
        self.tools = tools or {}
        self.permission_checker = permission_checker or DefaultPermissionChecker()
        self.workspace = workspace
        self.pre_call_hook = pre_call_hook
        self.post_call_hook = post_call_hook

    def register_tool(self, name: str, config: ToolConfig):
        """Register a tool configuration."""
        self.tools[name] = config

    def call(self, tool: str, args: list[str], cwd: str | None = None) -> ToolResult:
        """Call a tool with the given arguments.

        Args:
            tool: Name of the tool to call.
            args: Command-line arguments to pass to the tool.
            cwd: Working directory. Defaults to workspace.

        Returns:
            ToolResult with exit code, stdout, stderr, and optional error.
        """
        cwd = cwd or self.workspace

        # Check tool is registered
        if tool not in self.tools:
            return ToolResult(
                exit_code=1,
                stdout='',
                stderr='',
                error=f"Unknown tool: {tool}",
            )

        config = self.tools[tool]

        # Validate binary exists
        if not Path(config.binary).exists():
            return ToolResult(
                exit_code=127,
                stdout='',
                stderr='',
                error=f"Tool not installed: {tool}",
            )

        # Validate cwd
        cwd_path = Path(cwd)
        if not cwd_path.exists():
            cwd = self.workspace

        # Check permissions
        allowed, error = self.permission_checker.check(tool, args, cwd, config)
        if not allowed:
            return ToolResult(
                exit_code=1,
                stdout='',
                stderr='',
                error=f"Permission denied: {error}",
            )

        # Pre-call hook
        if self.pre_call_hook:
            try:
                self.pre_call_hook(tool, args, cwd)
            except Exception as e:
                logger.warning(f"Pre-call hook failed: {e}")

        # Execute command
        result = self._execute(tool, args, cwd, config)

        # Post-call hook
        if self.post_call_hook:
            try:
                self.post_call_hook(tool, args, cwd, result)
            except Exception as e:
                logger.warning(f"Post-call hook failed: {e}")

        return result

    def _execute(self, tool: str, args: list[str], cwd: str, config: ToolConfig) -> ToolResult:
        """Execute the tool binary."""
        try:
            # Build command
            cmd = [config.binary] + args

            # Build environment
            env = os.environ.copy()
            env.update(config.env_overrides)

            # Execute
            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                timeout=config.timeout,
                env=env,
            )

            return ToolResult(
                exit_code=result.returncode,
                stdout=result.stdout.decode('utf-8', errors='replace'),
                stderr=result.stderr.decode('utf-8', errors='replace'),
            )

        except subprocess.TimeoutExpired:
            return ToolResult(
                exit_code=124,
                stdout='',
                stderr=f'Command timed out after {config.timeout}s',
                error='Timeout',
            )
        except Exception as e:
            return ToolResult(
                exit_code=1,
                stdout='',
                stderr=str(e),
                error=f'Execution failed: {e}',
            )


def create_default_caller(workspace: str = '/workspace') -> ToolCaller:
    """Create a ToolCaller with default configuration.

    This creates a caller that simply executes tools as-is, without any
    additional permission restrictions.
    """
    tools = {
        'git': ToolConfig(
            binary='/usr/bin/git',
            timeout=300,
        ),
    }

    return ToolCaller(tools=tools, workspace=workspace)


def create_restricted_caller(workspace: str = '/workspace') -> ToolCaller:
    """Create a ToolCaller with permission restrictions.

    This creates a caller with:
    - Workspace directory enforcement
    - Subcommand validation (based on tool config)
    """
    tools = {
        'git': ToolConfig(
            binary='/usr/bin/git',
            timeout=300,
            # Example: deny dangerous git operations
            denied_subcommands=['push', 'force-push'],
        ),
    }

    permission_checker = CompositePermissionChecker([
        WorkspacePermissionChecker(workspace),
        SubcommandPermissionChecker(),
    ])

    def audit_log(tool: str, args: list[str], cwd: str):
        logger.info(f"AUDIT: {tool} {' '.join(args)} in {cwd}")

    return ToolCaller(
        tools=tools,
        permission_checker=permission_checker,
        workspace=workspace,
        pre_call_hook=audit_log,
    )


# For direct CLI usage
if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.INFO)

    if len(sys.argv) < 2:
        print("Usage: tool-caller.py <tool> [args...]")
        sys.exit(1)

    tool = sys.argv[1]
    args = sys.argv[2:]

    caller = create_default_caller()
    result = caller.call(tool, args)

    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)

    sys.exit(result.exit_code)
