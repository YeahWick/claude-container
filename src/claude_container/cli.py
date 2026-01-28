#!/usr/bin/env python3
"""Claude Container CLI - Run Claude Code in a sandboxed container."""

import argparse
import hashlib
import os
import subprocess
import sys
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


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Claude Code in a sandboxed container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run      Start tool server and run Claude interactively (default)
  start    Start all containers in background
  stop     Stop all containers
  status   Show container status
  logs     View container logs (optionally specify service)
  build    Build container images
  install  Run installation script
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

    args = parser.parse_args()

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

    # Check for API key
    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Warning: ANTHROPIC_API_KEY not set")
        print("Claude Code may not work without an API key.")
        print()

    # Check for GitHub token
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
