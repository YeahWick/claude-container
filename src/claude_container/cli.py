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


COMPOSE_FILE = "podman-compose.yaml"


def get_claude_home() -> Path:
    """Get the Claude Container home directory."""
    return Path(os.environ.get("CLAUDE_HOME", Path.home() / ".config" / "claude-container"))


def get_repo_dir() -> Path:
    """Get the repository directory where podman-compose.yaml lives."""
    claude_home = get_claude_home()
    # The repo is installed at CLAUDE_HOME/repo
    repo_dir = claude_home / "repo"
    if repo_dir.exists():
        return repo_dir
    # Fallback: check if we're running from the repo itself
    script_dir = Path(__file__).parent
    for parent in [script_dir, script_dir.parent, script_dir.parent.parent]:
        if (parent / COMPOSE_FILE).exists():
            return parent
    raise RuntimeError(
        f"Cannot find {COMPOSE_FILE}. "
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


def load_env_file(claude_home: Path) -> dict[str, str]:
    """Load environment variables from .env file if it exists."""
    env_vars = {}
    env_file = claude_home / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                if "=" in line:
                    key, _, value = line.partition("=")
                    key = key.strip()
                    value = value.strip().strip("\"'")
                    env_vars[key] = value
    return env_vars


def apply_env_file(claude_home: Path) -> None:
    """Apply .env file variables to the current environment (without overriding)."""
    env_vars = load_env_file(claude_home)
    for key, value in env_vars.items():
        if key not in os.environ:
            os.environ[key] = value


def find_compose_command() -> list[str]:
    """Find the available compose command (podman-compose preferred)."""
    # Try podman-compose first
    if shutil.which("podman-compose"):
        return ["podman-compose"]
    # Try podman compose (plugin style)
    try:
        result = subprocess.run(
            ["podman", "compose", "version"],
            capture_output=True,
            timeout=5,
        )
        if result.returncode == 0:
            return ["podman", "compose"]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    return []


def find_container_runtime() -> str:
    """Find the available container runtime."""
    if shutil.which("podman"):
        return "podman"
    return ""


def check_podman_running() -> bool:
    """Check if Podman machine is running (macOS) or Podman is available."""
    runtime = find_container_runtime()
    if not runtime:
        return False
    try:
        result = subprocess.run(
            [runtime, "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def images_exist(repo_dir: Path, env: dict[str, str]) -> bool:
    """Check if container images have been built."""
    runtime = find_container_runtime()
    if not runtime:
        return False
    for image in ["claude-code:v2", "tool-server:v2"]:
        try:
            result = subprocess.run(
                [runtime, "image", "exists", image],
                capture_output=True,
                timeout=5,
            )
            if result.returncode != 0:
                return False
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False
    return True


def run_compose(
    repo_dir: Path,
    args: list[str],
    env: dict[str, str],
    capture_output: bool = False,
) -> subprocess.CompletedProcess:
    """Run podman-compose with the given arguments."""
    compose_cmd = find_compose_command()
    if not compose_cmd:
        print("Error: podman-compose not found.")
        print("Install it with: pip install podman-compose")
        print("  or: brew install podman-compose")
        sys.exit(1)
    cmd = [*compose_cmd, "-f", COMPOSE_FILE, *args]
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

    # Auto-build if images are missing
    if not images_exist(repo_dir, env):
        print("Container images not found. Building...")
        result = run_compose(repo_dir, ["build"], env)
        if result.returncode != 0:
            print("Error: Failed to build container images.")
            return result.returncode
        print()

    # Start tool server first
    print("Starting tool server...")
    result = run_compose(repo_dir, ["up", "-d", "tool-server"], env)
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
        print(f"Error: Tool server socket not ready at {socket_file}")
        print()
        # Show tool-server logs to help debug
        print("Tool server logs:")
        print("-" * 40)
        run_compose(
            repo_dir,
            ["logs", "--tail=20", "tool-server"],
            env,
        )
        print("-" * 40)
        print()
        print("Try: claude-container logs tool-server")
        return 1

    # Start Claude client interactively
    print("Starting Claude...")
    result = run_compose(repo_dir, ["run", "--rm", "claude"], env)
    return result.returncode


def cmd_start(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Start all containers in background."""
    claude_home = get_claude_home()
    instance_id = env["INSTANCE_ID"]

    print(f"Instance: {instance_id} (from {env['PROJECT_DIR']})")
    print(f"Project:  {env['COMPOSE_PROJECT_NAME']}")
    print()

    # Auto-build if images are missing
    if not images_exist(repo_dir, env):
        print("Container images not found. Building...")
        result = run_compose(repo_dir, ["build"], env)
        if result.returncode != 0:
            return result.returncode
        print()

    print("Starting all containers...")
    result = run_compose(repo_dir, ["up", "-d"], env)
    if result.returncode == 0:
        print()
        print("Containers started. Use 'claude-container logs' to view logs.")
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
    result = run_compose(repo_dir, ["down"], env)

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
    run_compose(repo_dir, ["ps"], env)
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
    result = run_compose(repo_dir, log_args, env)
    return result.returncode


def cmd_build(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Build container images, injecting extra packages from catalog tools."""
    claude_home = get_claude_home()
    extra_packages_file = claude_home / "tools" / "extra-packages.txt"

    # Collect packages from all installed tools
    tools_dir = get_tools_dir()
    extra_packages = set()
    if tools_dir.exists():
        for tool_dir in tools_dir.iterdir():
            if not tool_dir.is_dir():
                continue
            tool_json = tool_dir / "tool.json"
            if tool_json.exists():
                with open(tool_json) as f:
                    data = json.load(f)
                for pkg in data.get("packages", []):
                    extra_packages.add(pkg)

    if extra_packages:
        print(f"Extra packages to install: {', '.join(sorted(extra_packages))}")
        env["EXTRA_PACKAGES"] = " ".join(sorted(extra_packages))
    else:
        env["EXTRA_PACKAGES"] = ""

    print("Building containers...")
    result = run_compose(repo_dir, ["build"], env)
    return result.returncode


def cmd_install(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Run the installation script."""
    # Find install.sh - check multiple locations
    locations = [
        repo_dir / "scripts" / "install.sh",
        Path(__file__).parent.parent.parent / "scripts" / "install.sh",
    ]
    for install_script in locations:
        if install_script.exists():
            result = subprocess.run(["bash", str(install_script)], cwd=install_script.parent.parent)
            return result.returncode
    print("Error: install.sh not found")
    return 1


def cmd_setup(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """One-command bootstrap: install + build + configure API key."""
    claude_home = get_claude_home()

    print("Claude Container Setup")
    print("=" * 40)
    print()

    # Step 1: Check prerequisites
    print("[1/4] Checking prerequisites...")
    runtime = find_container_runtime()
    if not runtime:
        print("  Error: Podman is not installed.")
        print("  Install it from: https://podman.io/docs/installation")
        return 1
    print(f"  Podman: found ({runtime})")

    compose_cmd = find_compose_command()
    if not compose_cmd:
        print("  Error: podman-compose is not installed.")
        print("  Install with: pip install podman-compose")
        print("    or: brew install podman-compose")
        return 1
    print(f"  Compose: found ({' '.join(compose_cmd)})")

    if not check_podman_running():
        print("  Warning: Podman does not appear to be running.")
        print("  On macOS, run: podman machine start")
        print()
    else:
        print("  Podman: running")
    print()

    # Step 2: Run install
    print("[2/4] Installing to ~/.config/claude-container/...")
    ret = cmd_install(args, env, repo_dir)
    if ret != 0:
        return ret
    print()

    # Step 3: Configure API key
    print("[3/4] Configuring API key...")
    env_file = claude_home / ".env"
    existing_env = load_env_file(claude_home)

    if os.environ.get("ANTHROPIC_API_KEY"):
        print("  ANTHROPIC_API_KEY found in environment.")
    elif existing_env.get("ANTHROPIC_API_KEY"):
        print("  ANTHROPIC_API_KEY found in .env file.")
    else:
        print("  No ANTHROPIC_API_KEY found.")
        print(f"  Create {env_file} with:")
        print(f"    echo 'ANTHROPIC_API_KEY=your_key' > {env_file}")
        print()

    if os.environ.get("GITHUB_TOKEN"):
        print("  GITHUB_TOKEN found in environment.")
    elif existing_env.get("GITHUB_TOKEN"):
        print("  GITHUB_TOKEN found in .env file.")
    else:
        print("  No GITHUB_TOKEN found (optional, needed for authenticated git).")
    print()

    # Step 4: Build images
    print("[4/4] Building container images...")
    # Re-resolve repo_dir after install (it may have been created)
    try:
        build_repo_dir = get_repo_dir()
    except RuntimeError:
        build_repo_dir = repo_dir
    result = run_compose(build_repo_dir, ["build"], env)
    if result.returncode != 0:
        print("Error: Failed to build images.")
        return result.returncode
    print()

    print("Setup complete!")
    print()
    print("Quick start:")
    print("  cd /path/to/your/project")
    print("  claude-container")
    print()
    print("Manage tools:")
    print("  claude-container tools list")
    print("  claude-container tools add npm")
    return 0


def cmd_doctor(args: argparse.Namespace, env: dict[str, str], repo_dir: Path) -> int:
    """Run health checks and report status."""
    claude_home = get_claude_home()
    all_ok = True

    print("Claude Container Health Check")
    print("=" * 40)
    print()

    # Check Podman
    runtime = find_container_runtime()
    if runtime:
        try:
            result = subprocess.run(
                [runtime, "--version"], capture_output=True, text=True, timeout=5
            )
            version = result.stdout.strip()
            print(f"  Podman:         OK ({version})")
        except (FileNotFoundError, subprocess.TimeoutExpired):
            print(f"  Podman:         OK ({runtime})")
    else:
        print("  Podman:         MISSING")
        print("    Install from: https://podman.io/docs/installation")
        all_ok = False

    # Check Podman running
    if runtime and check_podman_running():
        print("  Podman running: OK")
    elif runtime:
        print("  Podman running: NO")
        print("    On macOS, run: podman machine start")
        all_ok = False

    # Check podman-compose
    compose_cmd = find_compose_command()
    if compose_cmd:
        print(f"  Compose:        OK ({' '.join(compose_cmd)})")
    else:
        print("  Compose:        MISSING")
        print("    Install with: pip install podman-compose")
        all_ok = False

    # Check installation
    if check_installation(claude_home):
        print(f"  Installed:      OK ({claude_home})")
    else:
        print(f"  Installed:      NO")
        print("    Run: claude-container setup")
        all_ok = False

    # Check compose file
    try:
        rd = get_repo_dir()
        if (rd / COMPOSE_FILE).exists():
            print(f"  Compose file:   OK ({rd / COMPOSE_FILE})")
        else:
            print(f"  Compose file:   MISSING ({rd / COMPOSE_FILE})")
            all_ok = False
    except RuntimeError:
        print("  Compose file:   NOT FOUND")
        all_ok = False

    # Check images
    if runtime and images_exist(repo_dir, env):
        print("  Images:         OK (claude-code:v2, tool-server:v2)")
    else:
        print("  Images:         NOT BUILT")
        print("    Run: claude-container build")
        all_ok = False

    # Check API key
    env_vars = load_env_file(claude_home)
    if os.environ.get("ANTHROPIC_API_KEY") or env_vars.get("ANTHROPIC_API_KEY"):
        print("  API key:        OK")
    else:
        print("  API key:        MISSING")
        print(f"    Set: export ANTHROPIC_API_KEY=your_key")
        print(f"    Or:  echo 'ANTHROPIC_API_KEY=your_key' > {claude_home / '.env'}")
        all_ok = False

    # Check GitHub token
    if os.environ.get("GITHUB_TOKEN") or env_vars.get("GITHUB_TOKEN"):
        print("  GitHub token:   OK")
    else:
        print("  GitHub token:   NOT SET (optional)")

    # Check sockets directory
    sockets_dir = claude_home / "sockets"
    if sockets_dir.exists():
        sockets = list(sockets_dir.glob("*.sock"))
        print(f"  Sockets dir:    OK ({len(sockets)} active)")
    else:
        print("  Sockets dir:    MISSING")
        all_ok = False

    # Check tools
    tools_dir = get_tools_dir()
    if tools_dir.exists():
        tools = [d.name for d in tools_dir.iterdir() if d.is_dir() and (d / "tool.json").exists()]
        print(f"  Tools:          {len(tools)} installed ({', '.join(tools) if tools else 'none'})")
    else:
        print("  Tools:          NONE")

    print()
    if all_ok:
        print("All checks passed.")
    else:
        print("Some checks failed. Run 'claude-container setup' to fix.")
    return 0 if all_ok else 1


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
                "packages": data.get("packages", []),
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


def generate_extra_packages_file(tools_dir: Path) -> None:
    """Generate a file listing all extra packages needed by installed tools."""
    claude_home = get_claude_home()
    packages = set()
    for tool_dir in tools_dir.iterdir():
        if not tool_dir.is_dir():
            continue
        tool_json = tool_dir / "tool.json"
        if tool_json.exists():
            with open(tool_json) as f:
                data = json.load(f)
            for pkg in data.get("packages", []):
                packages.add(pkg)

    packages_file = claude_home / "tools" / "extra-packages.txt"
    packages_file.write_text("\n".join(sorted(packages)) + "\n" if packages else "")


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

    # Update extra packages file
    generate_extra_packages_file(tools_dir)

    # Show package installation note
    tool_json = dest_dir / "tool.json"
    if tool_json.exists():
        with open(tool_json) as f:
            data = json.load(f)
        packages = data.get("packages", [])
        if packages:
            print()
            print(f"This tool requires packages: {', '.join(packages)}")
            print("Rebuild to install them:")
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

    # Update extra packages file
    generate_extra_packages_file(tools_dir)

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

    # Update extra packages file
    generate_extra_packages_file(tools_dir)

    return 0


def main() -> int:
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Run Claude Code in a sandboxed container",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Commands:
  run          Start tool server and run Claude interactively (default)
  setup        One-command bootstrap: install + build + configure
  start        Start all containers in background
  stop         Stop all containers
  status       Show container status
  logs         View container logs (optionally specify service)
  build        Build container images
  install      Run installation script
  doctor       Run health checks
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

    # setup command
    subparsers.add_parser("setup", help="One-command bootstrap: install + build + configure")

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

    # doctor command
    subparsers.add_parser("doctor", help="Run health checks and report status")

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

    # Handle tools commands separately (they don't need container setup)
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

    # Load .env file early
    apply_env_file(claude_home)

    # Check installation (except for install/setup/doctor commands)
    if args.command not in ("install", "setup", "doctor") and not check_installation(claude_home):
        print("Error: Claude Container not installed.")
        print("Run: claude-container setup")
        return 1

    # Check for API key (only for run/start commands)
    if args.command in ("run", "start"):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            print("Warning: ANTHROPIC_API_KEY not set")
            print("Claude Code may not work without an API key.")
            print(f"Set it in environment or in {claude_home / '.env'}")
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
        if args.command == "setup":
            # For setup, use the package directory as fallback
            repo_dir = Path(__file__).parent.parent.parent
        else:
            print(f"Error: {e}")
            return 1

    # Dispatch to command handler
    commands = {
        "run": cmd_run,
        "setup": cmd_setup,
        "start": cmd_start,
        "stop": cmd_stop,
        "status": cmd_status,
        "logs": cmd_logs,
        "build": cmd_build,
        "install": cmd_install,
        "doctor": cmd_doctor,
    }

    handler = commands.get(args.command)
    if handler:
        return handler(args, env, repo_dir)
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
