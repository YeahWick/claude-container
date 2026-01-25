#!/usr/bin/env python3
"""Tool Server Caller - handles tool binary invocation.

By default, calls the CLI tool binary as-is. If a wrapper script exists
in the RESTRICTED_TOOLS_DIR, that wrapper is called instead. The wrapper
decides what to allow and whether to pass through to the real tool.

Wrapper lookup order:
  1. {RESTRICTED_TOOLS_DIR}/{tool}.py  (Python script)
  2. {RESTRICTED_TOOLS_DIR}/{tool}.sh  (Bash script)
  3. {RESTRICTED_TOOLS_DIR}/{tool}     (Any executable)

If no wrapper exists, calls the real binary directly.

Environment variables passed to wrappers:
  TOOL_NAME      - Name of the tool being called
  TOOL_BINARY    - Path to the real binary
  TOOL_CWD       - Working directory for the command
  TOOL_ARGS      - JSON array of arguments
"""

import json
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Default locations
DEFAULT_RESTRICTED_DIR = '/app/restricted'
DEFAULT_WORKSPACE = '/workspace'


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


class ToolCaller:
    """Handles tool binary invocation with optional wrapper scripts.

    If a wrapper script exists in restricted_dir for the tool, calls that
    instead. The wrapper handles all permission logic and can call through
    to the real binary.
    """

    def __init__(
        self,
        tools: dict[str, ToolConfig] | None = None,
        restricted_dir: str = DEFAULT_RESTRICTED_DIR,
        workspace: str = DEFAULT_WORKSPACE,
    ):
        """Initialize the tool caller.

        Args:
            tools: Tool configurations mapping name -> config.
            restricted_dir: Directory to look for wrapper scripts.
            workspace: Default workspace directory.
        """
        self.tools = tools or {}
        self.restricted_dir = Path(restricted_dir)
        self.workspace = workspace

    def register_tool(self, name: str, config: ToolConfig):
        """Register a tool configuration."""
        self.tools[name] = config

    def find_wrapper(self, tool: str) -> Path | None:
        """Find a wrapper script for the tool.

        Returns path to wrapper if found, None otherwise.
        """
        if not self.restricted_dir.exists():
            return None

        # Check in order: .py, .sh, bare name
        candidates = [
            self.restricted_dir / f'{tool}.py',
            self.restricted_dir / f'{tool}.sh',
            self.restricted_dir / tool,
        ]

        for candidate in candidates:
            if candidate.exists() and candidate.is_file():
                # Check if executable
                if os.access(candidate, os.X_OK):
                    return candidate
                # For .py files, we can run with python
                if candidate.suffix == '.py':
                    return candidate

        return None

    def call(self, tool: str, args: list[str], cwd: str | None = None) -> ToolResult:
        """Call a tool with the given arguments.

        If a wrapper exists, calls the wrapper instead of the real binary.
        The wrapper receives environment variables with tool info.
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

        # Validate real binary exists
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

        # Check for wrapper script
        wrapper = self.find_wrapper(tool)

        if wrapper:
            logger.info(f"Using wrapper {wrapper} for {tool}")
            return self._execute_wrapper(wrapper, tool, args, cwd, config)
        else:
            logger.debug(f"No wrapper for {tool}, calling binary directly")
            return self._execute_direct(tool, args, cwd, config)

    def _execute_wrapper(
        self,
        wrapper: Path,
        tool: str,
        args: list[str],
        cwd: str,
        config: ToolConfig,
    ) -> ToolResult:
        """Execute via wrapper script."""
        try:
            # Build environment for wrapper
            env = os.environ.copy()
            env['TOOL_NAME'] = tool
            env['TOOL_BINARY'] = config.binary
            env['TOOL_CWD'] = cwd
            env['TOOL_ARGS'] = json.dumps(args)

            # Determine how to run the wrapper
            if wrapper.suffix == '.py':
                cmd = ['python3', str(wrapper)] + args
            elif wrapper.suffix == '.sh':
                cmd = ['bash', str(wrapper)] + args
            else:
                cmd = [str(wrapper)] + args

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
                error=f'Wrapper execution failed: {e}',
            )

    def _execute_direct(
        self,
        tool: str,
        args: list[str],
        cwd: str,
        config: ToolConfig,
    ) -> ToolResult:
        """Execute the tool binary directly."""
        try:
            cmd = [config.binary] + args

            result = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                timeout=config.timeout,
                env=os.environ.copy(),
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


def create_default_caller(
    workspace: str = DEFAULT_WORKSPACE,
    restricted_dir: str = DEFAULT_RESTRICTED_DIR,
) -> ToolCaller:
    """Create a ToolCaller with default tool configuration."""
    tools = {
        'git': ToolConfig(
            binary='/usr/bin/git',
            timeout=300,
        ),
    }

    return ToolCaller(
        tools=tools,
        workspace=workspace,
        restricted_dir=restricted_dir,
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
