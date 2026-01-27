#!/usr/bin/env python3
"""Tool Caller - handles tool binary invocation with auto-discovery.

Tools are auto-discovered from TOOLS_DIR (default: /app/tools.d/).
Each tool is a subdirectory containing:

  tool.json     - Required: {"binary": "/usr/bin/git", "timeout": 300}
  setup.sh      - Optional: runs on first use (lazy) or at container start
  restricted.sh - Optional: restriction wrapper (bash)
  restricted.py - Optional: restriction wrapper (python, takes priority)

If no tool.json exists, the tool name is used to locate the binary
at /usr/bin/{name} or /usr/local/bin/{name}.

Hot-loading: Tools added to tools.d/ after startup are discovered lazily
on first request. The server checks the filesystem for unknown tool names
before rejecting, registers them on the fly, and runs their setup scripts.

Wrapper lookup order:
  1. {TOOLS_DIR}/{tool}/restricted.py
  2. {TOOLS_DIR}/{tool}/restricted.sh
  3. {TOOLS_DIR}/{tool}/restricted    (any executable)
  4. {RESTRICTED_DIR}/{tool}.py       (global fallback)
  5. {RESTRICTED_DIR}/{tool}.sh       (global fallback)
  6. {RESTRICTED_DIR}/{tool}          (global fallback)

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
DEFAULT_TOOLS_DIR = '/app/tools.d'
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

    If a wrapper script exists for the tool, calls that instead.
    The wrapper handles all permission logic and can call through
    to the real binary.
    """

    def __init__(
        self,
        tools: dict[str, ToolConfig] | None = None,
        tools_dir: str = DEFAULT_TOOLS_DIR,
        restricted_dir: str = DEFAULT_RESTRICTED_DIR,
        workspace: str = DEFAULT_WORKSPACE,
    ):
        self.tools = tools or {}
        self.tools_dir = Path(tools_dir)
        self.restricted_dir = Path(restricted_dir)
        self.workspace = workspace
        self._setup_completed: set[str] = set()

    def register_tool(self, name: str, config: ToolConfig):
        """Register a tool configuration."""
        self.tools[name] = config
        logger.info(f'Registered tool: {name} (binary={config.binary}, timeout={config.timeout}s)')

    def discover_tools(self) -> int:
        """Auto-discover tools from the tools directory.

        Scans TOOLS_DIR for subdirectories containing tool.json manifests.
        Each subdirectory name becomes the tool name.

        Returns the number of tools discovered.
        """
        if not self.tools_dir.exists():
            logger.warning(f'Tools directory not found: {self.tools_dir}')
            return 0

        count = 0
        for entry in sorted(self.tools_dir.iterdir()):
            if not entry.is_dir():
                continue

            tool_name = entry.name
            manifest = entry / 'tool.json'

            if manifest.exists():
                try:
                    config = self._load_manifest(tool_name, manifest)
                    self.register_tool(tool_name, config)
                    # Mark setup as done — tool-setup.sh already ran it at boot
                    self._setup_completed.add(tool_name)
                    count += 1
                except (json.JSONDecodeError, KeyError) as e:
                    logger.error(f'Invalid manifest for tool {tool_name}: {e}')
                    continue
            else:
                # Auto-detect binary from common paths
                config = self._auto_detect_binary(tool_name)
                if config:
                    self.register_tool(tool_name, config)
                    self._setup_completed.add(tool_name)
                    count += 1
                else:
                    logger.warning(f'Tool {tool_name}: no tool.json and binary not found in PATH')

        return count

    def _load_manifest(self, tool_name: str, manifest_path: Path) -> ToolConfig:
        """Load a tool configuration from a manifest file."""
        with open(manifest_path) as f:
            data = json.load(f)

        binary = data.get('binary')
        if not binary:
            # Auto-detect if binary not specified
            config = self._auto_detect_binary(tool_name)
            if config:
                binary = config.binary
            else:
                raise KeyError(f'binary not specified and {tool_name} not found in standard paths')

        timeout = data.get('timeout', 300)
        return ToolConfig(binary=binary, timeout=timeout)

    def _auto_detect_binary(self, tool_name: str) -> ToolConfig | None:
        """Try to find a binary for the tool in standard paths."""
        candidates = [
            Path(f'/usr/bin/{tool_name}'),
            Path(f'/usr/local/bin/{tool_name}'),
            Path(f'/bin/{tool_name}'),
        ]
        for candidate in candidates:
            if candidate.exists() and os.access(candidate, os.X_OK):
                logger.debug(f'Auto-detected binary for {tool_name}: {candidate}')
                return ToolConfig(binary=str(candidate))
        return None

    def _try_lazy_discover(self, tool_name: str) -> bool:
        """Attempt to discover a single tool on demand.

        Called when a request arrives for an unregistered tool.
        Checks if tools.d/{tool_name}/ exists and registers it.

        Returns True if the tool was discovered and registered.
        """
        tool_dir = self.tools_dir / tool_name
        if not tool_dir.is_dir():
            return False

        manifest = tool_dir / 'tool.json'
        if manifest.exists():
            try:
                config = self._load_manifest(tool_name, manifest)
            except (json.JSONDecodeError, KeyError) as e:
                logger.error(f'Hot-load failed for {tool_name}: invalid manifest: {e}')
                return False
        else:
            config = self._auto_detect_binary(tool_name)
            if not config:
                logger.warning(f'Hot-load failed for {tool_name}: no manifest and binary not found')
                return False

        self.register_tool(tool_name, config)
        logger.info(f'Hot-loaded tool: {tool_name}')

        # Run setup script if present and not yet run
        self._run_setup_if_needed(tool_name)

        return True

    def _run_setup_if_needed(self, tool_name: str):
        """Run a tool's setup.sh if it exists and hasn't been run yet."""
        if tool_name in self._setup_completed:
            return

        setup_script = self.tools_dir / tool_name / 'setup.sh'
        if not setup_script.exists():
            self._setup_completed.add(tool_name)
            return

        logger.info(f'Running setup script for hot-loaded tool: {tool_name}')
        try:
            result = subprocess.run(
                ['bash', str(setup_script)],
                capture_output=True,
                timeout=30,
            )
            if result.returncode == 0:
                logger.info(f'Setup complete for: {tool_name}')
            else:
                stderr = result.stderr.decode('utf-8', errors='replace').strip()
                logger.warning(f'Setup failed for {tool_name} (exit {result.returncode}): {stderr}')
        except subprocess.TimeoutExpired:
            logger.warning(f'Setup script timed out for: {tool_name}')
        except Exception as e:
            logger.warning(f'Setup script error for {tool_name}: {type(e).__name__}: {e}')

        self._setup_completed.add(tool_name)

    def mark_setup_done(self, tool_name: str):
        """Mark a tool's setup as already completed (e.g. run at startup)."""
        self._setup_completed.add(tool_name)

    def find_wrapper(self, tool: str) -> Path | None:
        """Find a wrapper script for the tool.

        Checks tool-specific directory first, then global restricted dir.
        Returns path to wrapper if found, None otherwise.
        """
        # Check tool-specific directory first
        tool_dir = self.tools_dir / tool
        if tool_dir.is_dir():
            tool_candidates = [
                tool_dir / 'restricted.py',
                tool_dir / 'restricted.sh',
                tool_dir / 'restricted',
            ]
            for candidate in tool_candidates:
                if candidate.exists() and candidate.is_file():
                    if os.access(candidate, os.X_OK) or candidate.suffix == '.py':
                        logger.debug(f'Found tool-specific wrapper: {candidate}')
                        return candidate

        # Fall back to global restricted directory
        if self.restricted_dir.exists():
            global_candidates = [
                self.restricted_dir / f'{tool}.py',
                self.restricted_dir / f'{tool}.sh',
                self.restricted_dir / tool,
            ]
            for candidate in global_candidates:
                if candidate.exists() and candidate.is_file():
                    if os.access(candidate, os.X_OK) or candidate.suffix == '.py':
                        logger.debug(f'Found global wrapper: {candidate}')
                        return candidate

        return None

    def call(self, tool: str, args: list[str], cwd: str | None = None) -> ToolResult:
        """Call a tool with the given arguments.

        If a wrapper exists, calls the wrapper instead of the real binary.
        The wrapper receives environment variables with tool info.
        """
        cwd = cwd or self.workspace

        # Check tool is registered; try lazy discovery if not
        if tool not in self.tools:
            if not self._try_lazy_discover(tool):
                logger.warning(f'Rejected unknown tool: {tool}')
                return ToolResult(
                    exit_code=1,
                    stdout='',
                    stderr='',
                    error=f"Unknown tool: {tool}",
                )

        config = self.tools[tool]

        # Validate real binary exists
        if not Path(config.binary).exists():
            logger.error(f'Binary not found for tool {tool}: {config.binary}')
            return ToolResult(
                exit_code=127,
                stdout='',
                stderr='',
                error=f"Tool not installed: {tool}",
            )

        # Validate cwd
        cwd_path = Path(cwd)
        if not cwd_path.exists():
            logger.warning(f'CWD not found for {tool}, falling back to workspace: {cwd} -> {self.workspace}')
            cwd = self.workspace

        # Check for wrapper script
        wrapper = self.find_wrapper(tool)

        if wrapper:
            logger.info(f'Executing {tool} via wrapper {wrapper.name} (args={len(args)}, cwd={cwd})')
            return self._execute_wrapper(wrapper, tool, args, cwd, config)
        else:
            logger.info(f'Executing {tool} directly (args={len(args)}, cwd={cwd})')
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
            logger.warning(f'Tool {tool} timed out after {config.timeout}s (wrapper={wrapper.name})')
            return ToolResult(
                exit_code=124,
                stdout='',
                stderr=f'Command timed out after {config.timeout}s',
                error='Timeout',
            )
        except Exception as e:
            logger.error(f'Wrapper execution failed for {tool}: {type(e).__name__}: {e}')
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
            logger.warning(f'Tool {tool} timed out after {config.timeout}s')
            return ToolResult(
                exit_code=124,
                stdout='',
                stderr=f'Command timed out after {config.timeout}s',
                error='Timeout',
            )
        except Exception as e:
            logger.error(f'Direct execution failed for {tool}: {type(e).__name__}: {e}')
            return ToolResult(
                exit_code=1,
                stdout='',
                stderr=str(e),
                error=f'Execution failed: {e}',
            )


def create_auto_caller(
    tools_dir: str = DEFAULT_TOOLS_DIR,
    restricted_dir: str = DEFAULT_RESTRICTED_DIR,
    workspace: str = DEFAULT_WORKSPACE,
) -> ToolCaller:
    """Create a ToolCaller that auto-discovers tools from tools.d directory.

    Scans the tools directory for subdirectories with tool.json manifests.
    Each subdirectory becomes a registered tool.
    """
    caller = ToolCaller(
        tools_dir=tools_dir,
        restricted_dir=restricted_dir,
        workspace=workspace,
    )

    count = caller.discover_tools()
    logger.info(f'Auto-discovered {count} tool(s) from {tools_dir}')

    return caller


# For direct CLI usage
if __name__ == '__main__':
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s %(levelname)s %(message)s',
    )

    if len(sys.argv) < 2:
        print("Usage: tool-caller.py <tool> [args...]")
        sys.exit(1)

    tool = sys.argv[1]
    args = sys.argv[2:]

    caller = create_auto_caller()
    result = caller.call(tool, args)

    if result.stdout:
        print(result.stdout, end='')
    if result.stderr:
        print(result.stderr, end='', file=sys.stderr)

    sys.exit(result.exit_code)
