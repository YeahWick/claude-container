#!/usr/bin/env python3
"""Claude Container CLI - Run Claude Code in a sandboxed container."""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path


def get_claude_home() -> Path:
    """Get the Claude Container home directory."""
    return Path(os.environ.get("CLAUDE_HOME", Path.home() / ".claude-container"))


def get_repo_dir() -> Path:
    """Get the repository directory where docker-compose.yaml lives."""
    claude_home = get_claude_home()
    # The repo is installed at CLAUDE_HOME/repo
    repo_dir = claude_home / "repo"
    if repo_dir.exists():
        return repo_dir
    # Fallback: check if we're running from the repo itself
    script_dir = Path(__file__).parent
    for parent in [script_dir, script_dir.parent, script_dir.parent.parent]:
        if (parent / "docker-compose.yaml").exists():
            return parent
    raise RuntimeError(
        f"Cannot find docker-compose.yaml. "
        f"Expected at {repo_dir} or in package directory."
    )


def get_catalog_dir() -> Path:
    """Get the tools catalog directory."""
    repo_dir = get_repo_dir()
    return repo_dir / "catalog"


def get_tools_dir() -> Path:
    """Get the installed tools directory."""
    return get_claude_home() / "tools" / "tools.d"


def generate_instance_id(project_dir: Path) -> str:
    """Generate instance ID from project directory hash."""
    normalized = str(project_dir.resolve())
    return hashlib.md5(normalized.encode()).hexdigest()[:8]


def check_installation(claude_home: Path) -> bool:
    """Check if Claude Container is properly installed."""
    tools_bin = claude_home / "tools" / "bin"
    return tools_bin.is_dir()


def run_docker_compose(
    repo_dir: Path,
    args: list[str],
    env: dict[str, str],
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run docker compose with the given arguments."""
    cmd = ["docker", "compose", *args]
    return subprocess.run(
        cmd,
        cwd=repo_dir,
        env={**os.environ, **env},
        capture_output=capture_output,
    )


def cmd_run(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Start tool server and run Claude interactively."""
    claude_home = get_claude_home()
    instance_id = env["INSTANCE_ID"]

    print(f"Instance: {instance_id} (from {env['PROJECT_DIR']})")
    print(f"Project:  {env['COMPOSE_PROJECT_NAME']}")
    print()

    # Start tool server first
    print("Starting tool server...")
    result = run_docker_compose(repo_dir, ["up", "-d", "tool-server"], env)
    if result.returncode != 0:
        return result.returncode

    # Wait for tool server socket
    print("Waiting for tool server...")
    socket_file = claude_home / "sockets" / f"tool-{instance_id}.sock"
    for _ in range(10):
        if socket_file.exists():
            break
        time.sleep(0.5)

    if not socket_file.exists():
        print(f"Warning: Tool server socket not ready at {socket_file}")
        print("Check: docker compose logs tool-server")

    # Start Claude client interactively
    print("Starting Claude...")
    result = run_docker_compose(repo_dir, ["run", "--rm", "claude"], env)
    return result.returncode


def cmd_start(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Start all containers in background."""
    claude_home = get_claude_home()
    instance_id = env["INSTANCE_ID"]

    print(f"Instance: {instance_id} (from {env['PROJECT_DIR']})")
    print(f"Project:  {env['COMPOSE_PROJECT_NAME']}")
    print()

    print("Starting all containers...")
    result = run_docker_compose(repo_dir, ["up", "-d"], env)
    if result.returncode == 0:
        print()
        print("Containers started. Use 'docker compose logs -f' to view logs.")
        print("To connect to Claude: docker compose exec claude bash")
        print(f"Socket: {claude_home}/sockets/tool-{instance_id}.sock")
    return result.returncode


def cmd_stop(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Stop all containers."""
    claude_home = get_claude_home()
    instance_id = env["INSTANCE_ID"]

    print(f"Instance: {instance_id}")
    print(f"Project:  {env['COMPOSE_PROJECT_NAME']}")
    print()

    print("Stopping all containers...")
    result = run_docker_compose(repo_dir, ["down"], env)

    # Clean up instance socket
    socket_file = claude_home / "sockets" / f"tool-{instance_id}.sock"
    if socket_file.exists():
        socket_file.unlink()
        print(f"Removed socket: {socket_file}")

    return result.returncode


def cmd_status(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Show container status."""
    claude_home = get_claude_home()
    instance_id = env["INSTANCE_ID"]

    print(f"Instance: {instance_id}")
    print(f"Project:  {env['COMPOSE_PROJECT_NAME']}")
    print()

    print("Container status:")
    run_docker_compose(repo_dir, ["ps"], env)
    print()

    print("Instance socket:")
    socket_file = claude_home / "sockets" / f"tool-{instance_id}.sock"
    if socket_file.exists():
        print(f"  {socket_file}")
    else:
        print("  (not found)")
    print()

    print("All sockets:")
    sockets_dir = claude_home / "sockets"
    sockets = list(sockets_dir.glob("*.sock")) if sockets_dir.exists() else []
    if sockets:
        for sock in sockets:
            print(f"  {sock}")
    else:
        print("  (none)")

    return 0


def cmd_logs(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """View container logs."""
    log_args = ["logs", "-f"]
    if args.service:
        log_args.append(args.service)
    result = run_docker_compose(repo_dir, log_args, env)
    return result.returncode


def cmd_build(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Build container images."""
    print("Building containers...")
    result = run_docker_compose(repo_dir, ["build"], env)
    return result.returncode


def cmd_install(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Run the installation script."""
    install_script = repo_dir / "scripts" / "install.sh"
    if not install_script.exists():
        print(f"Error: install.sh not found at {install_script}")
        return 1
    result = subprocess.run(["bash", str(install_script)], cwd=repo_dir)
    return result.returncode


# Tools management commands


def get_catalog_tools() -> dict:
    """Get available tools from the catalog."""
    catalog_dir = get_catalog_dir()
    index_file = catalog_dir / "index.json"

    if not index_file.exists():
        return {}

    with open(index_file) as f:
        data = json.load(f)
    return data.get("tools", {})


def get_installed_tools() -> dict:
    """Get installed tools with their metadata."""
    tools_dir = get_tools_dir()
    tools = {}

    if not tools_dir.exists():
        return tools

    for tool_dir in tools_dir.iterdir():
        if not tool_dir.is_dir():
            continue

        tool_json = tool_dir / "tool.json"
        if tool_json.exists():
            with open(tool_json) as f:
                data = json.load(f)
            tools[tool_dir.name] = {
                "binary": data.get("binary", ""),
                "description": data.get("description", ""),
                "installed": True,
            }

    return tools


def cmd_tools_list(args: argparse.Namespace) -> int:
    """List available and installed tools."""
    catalog_tools = get_catalog_tools()
    installed_tools = get_installed_tools()

    print("Available tools (catalog):")
    print("-" * 50)

    if not catalog_tools:
        print("  (no tools in catalog)")
    else:
        for name, info in sorted(catalog_tools.items()):
            status = "[installed]" if name in installed_tools else ""
            desc = info.get("description", "")
            category = info.get("category", "")
            print(f"  {name:12} {status:12} {desc} ({category})")

    print()
    print("Installed tools:")
    print("-" * 50)

    if not installed_tools:
        print("  (no tools installed)")
    else:
        for name, info in sorted(installed_tools.items()):
            in_catalog = "[catalog]" if name in catalog_tools else "[custom]"
            desc = info.get("description", "")
            print(f"  {name:12} {in_catalog:10} {desc}")

    return 0


def cmd_tools_add(args: argparse.Namespace) -> int:
    """Add a tool from catalog or URL."""
    tools_dir = get_tools_dir()
    tools_dir.mkdir(parents=True, exist_ok=True)

    if args.url:
        # Add tool from git URL
        return add_tool_from_url(args.name, args.url, tools_dir)
    else:
        # Add tool from catalog
        return add_tool_from_catalog(args.name, tools_dir)


def add_tool_from_catalog(name: str, tools_dir: Path) -> int:
    """Add a tool from the built-in catalog."""
    catalog_dir = get_catalog_dir()
    source_dir = catalog_dir / name

    if not source_dir.exists():
        print(f"Error: Tool '{name}' not found in catalog")
        print("Run 'claude-container tools list' to see available tools")
        return 1

    dest_dir = tools_dir / name

    if dest_dir.exists():
        print(f"Tool '{name}' is already installed at {dest_dir}")
        return 1

    # Copy tool from catalog
    shutil.copytree(source_dir, dest_dir)
    print(f"Added tool '{name}' from catalog")

    # Create symlink in bin/
    create_tool_symlink(name)

    # Show package installation note
    tool_json = dest_dir / "tool.json"
    if tool_json.exists():
        with open(tool_json) as f:
            data = json.load(f)
        packages = data.get("packages", [])
        if packages:
            print()
            print(f"Note: This tool requires these packages in tool-server container:")
            print(f"  {', '.join(packages)}")
            print()
            print("Add to tool-server/Containerfile and rebuild:")
            print(f"  RUN apt-get update && apt-get install -y {' '.join(packages)}")
            print("  claude-container build")

    return 0


def add_tool_from_url(name: str, url: str, tools_dir: Path) -> int:
    """Add a tool from a git repository URL."""
    dest_dir = tools_dir / name

    if dest_dir.exists():
        print(f"Tool '{name}' is already installed at {dest_dir}")
        return 1

    # Clone repo to temp directory
    with tempfile.TemporaryDirectory() as tmpdir:
        print(f"Cloning {url}...")
        result = subprocess.run(
            ["git", "clone", "--depth", "1", url, tmpdir],
            capture_output=True,
            text=True,
        )

        if result.returncode != 0:
            print(f"Error cloning repository: {result.stderr}")
            return 1

        # Check for tool.json
        tool_json = Path(tmpdir) / "tool.json"
        if not tool_json.exists():
            print(f"Error: Repository does not contain a tool.json file")
            return 1

        # Copy to tools directory (excluding .git)
        shutil.copytree(
            tmpdir,
            dest_dir,
            ignore=shutil.ignore_patterns(".git", ".github"),
        )

    print(f"Added tool '{name}' from {url}")

    # Create symlink in bin/
    create_tool_symlink(name)

    return 0


def create_tool_symlink(name: str) -> None:
    """Create a symlink for the tool in bin/."""
    claude_home = get_claude_home()
    bin_dir = claude_home / "tools" / "bin"
    symlink = bin_dir / name

    if not symlink.exists():
        symlink.symlink_to("tool-client")
        print(f"Created symlink: {name} -> tool-client")


def cmd_tools_remove(args: argparse.Namespace) -> int:
    """Remove an installed tool."""
    tools_dir = get_tools_dir()
    tool_dir = tools_dir / args.name

    if not tool_dir.exists():
        print(f"Tool '{args.name}' is not installed")
        return 1

    # Remove tool directory
    shutil.rmtree(tool_dir)
    print(f"Removed tool '{args.name}'")

    # Remove symlink
    claude_home = get_claude_home()
    symlink = claude_home / "tools" / "bin" / args.name
    if symlink.exists() or symlink.is_symlink():
        symlink.unlink()
        print(f"Removed symlink: {args.name}")

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Claude Code in a sandboxed container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run          Start tool server and run Claude interactively (default)
  start        Start all containers in background
  stop         Stop all containers
  status       Show container status
  logs         View container logs (optionally specify service)
  build        Build container images
  install      Run installation script
  tools list   List available and installed tools
  tools add    Add a tool from catalog or URL
  tools remove Remove an installed tool
""",
    )
    parser.add_argument(
        "-C",
        "--directory",
        type=Path,
        default=Path.cwd(),
        help="Project directory to mount (default: current directory)",
    )

    subparsers = parser.add_subparsers(dest="command", help="Command to run")

    # run command (default)
    subparsers.add_parser("run", help="Start tool server and run Claude interactively")

    # start command
    subparsers.add_parser("start", help="Start all containers in background")

    # stop command
    subparsers.add_parser("stop", help="Stop all containers")

    # status command
    subparsers.add_parser("status", help="Show container status")

    # logs command
    logs_parser = subparsers.add_parser("logs", help="View container logs")
    logs_parser.add_argument("service", nargs="?", help="Service to show logs for")

    # build command
    subparsers.add_parser("build", help="Build container images")

    # install command
    subparsers.add_parser("install", help="Run installation script")

    # tools command with subcommands
    tools_parser = subparsers.add_parser("tools", help="Manage tools")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command")

    # tools list
    tools_subparsers.add_parser("list", help="List available and installed tools")

    # tools add
    tools_add_parser = tools_subparsers.add_parser(
        "add", help="Add a tool from catalog or URL"
    )
    tools_add_parser.add_argument("name", help="Tool name")
    tools_add_parser.add_argument(
        "--url", help="Git repository URL (for custom tools)"
    )

    # tools remove
    tools_remove_parser = tools_subparsers.add_parser(
        "remove", help="Remove an installed tool"
    )
    tools_remove_parser.add_argument("name", help="Tool name to remove")

    args = parser.parse_args()

    # Handle tools commands separately (they don't need docker setup)
    if args.command == "tools":
        if args.tools_command == "list":
            return cmd_tools_list(args)
        elif args.tools_command == "add":
            return cmd_tools_add(args)
        elif args.tools_command == "remove":
            return cmd_tools_remove(args)
        else:
            tools_parser.print_help()
            return 1

    # Default to 'run' if no command specified
    if args.command is None:
        args.command = "run"

    # Get paths
    claude_home = get_claude_home()
    project_dir = args.directory.resolve()

    # Check installation (except for install command)
    if args.command != "install" and not check_installation(claude_home):
        print("Error: Claude Container not installed.")
        print("Run: claude-container install")
        return 1

    # Check for API key (only for run/start commands)
    if args.command in ("run", "start"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Warning: ANTHROPIC_API_KEY not set")
            print("Claude Code may not work without an API key.")
            print()

        if not os.environ.get("GITHUB_TOKEN"):
            print("Note: GITHUB_TOKEN not set")
            print("Git operations requiring authentication will fail.")
            print()

    # Generate instance ID
    instance_id = os.environ.get("INSTANCE_ID") or generate_instance_id(project_dir)

    # Set up environment
    env = {
        "CLAUDE_HOME": str(claude_home),
        "PROJECT_DIR": str(project_dir),
        "INSTANCE_ID": instance_id,
        "COMPOSE_PROJECT_NAME": os.environ.get(
            "COMPOSE_PROJECT_NAME", f"claude-{instance_id}"
        ),
    }

    # Get repo directory
    try:
        repo_dir = get_repo_dir()
    except RuntimeError as e:
        print(f"Error: {e}")
        return 1

    # Dispatch to command handler
    commands = {
        "run": cmd_run,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "logs": cmd_logs,
        "build": cmd_build,
        "install": cmd_install,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, env, repo_dir)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
