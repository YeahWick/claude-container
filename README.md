# Claude Container

A minimal container architecture for running Claude Code with controlled access to development tools.

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                           HOST SYSTEM                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────────────────┐       ┌────────────────────────────────┐  │
│  │   Claude (Client)       │       │      Tool Server               │  │
│  │                         │       │                                │  │
│  │  Claude Code CLI        │       │  tools.d/git/setup.sh (start)  │  │
│  │         ↓               │       │         ↓                      │  │
│  │  git push origin main   │       │  restricted/git.sh (optional)  │  │
│  │         ↓               │       │         ↓                      │  │
│  │  /app/tools/bin/git     │ sock  │  /usr/bin/git push origin main │  │
│  │  (tool-client)  ────────┼───────┼→ (real binary)                 │  │
│  │                         │       │                                │  │
│  └─────────────────────────┘       └────────────────────────────────┘  │
│           │                                    │                       │
│           └──────────── /workspace ────────────┘                       │
│                    (shared bind mount)                                 │
└────────────────────────────────────────────────────────────────────────┘
```

### Containers

| Container | Purpose | Dockerfile |
|-----------|---------|------------|
| **claude** (client) | Runs Claude Code CLI with tool-client wrappers | `claude/Containerfile` |
| **tool-server** | Executes tools with optional restrictions | `tool-server/Containerfile` |

### Key Features

- **Minimal client** - Claude container only has lightweight tool-client wrappers
- **Server-side control** - All tool execution happens in the tool server
- **Auto-discovery** - Tools defined in `tools.d/` are auto-registered, no code changes needed
- **Project mounting** - Current directory mounted to `/workspace` for file editing
- **Project setup hook** - `.claude-container/config.json` specifies a setup script for dependencies
- **Per-tool setup** - `tools.d/{tool}/setup.sh` scripts run at container start
- **Per-tool restrictions** - `tools.d/{tool}/restricted.sh` wrappers intercept calls
- **Hot-loading** - Tools added after startup are discovered on first use
- **Concurrent instances** - Multiple projects can run simultaneously
- **Single mount** - `bin/` and `tools.d/` share one host directory for clean relative symlinks

## Quick Start

```bash
# Install CLI via uv
uv tool install git+https://github.com/YeahWick/claude-container.git

# Run setup (creates ~/.claude-container/)
claude-container install

# Set API keys
export ANTHROPIC_API_KEY=your_key
export GITHUB_TOKEN=your_token  # optional

# Build containers
cd ~/.claude-container/repo && docker compose build

# Run from any project directory
cd /path/to/your/project
claude-container
```

### Alternative: Clone and Run

```bash
git clone https://github.com/YeahWick/claude-container.git
cd claude-container
./scripts/install.sh
docker compose build
./scripts/run.sh
```

## Project Setup

When you run `claude-container` from a directory, that directory is mounted to `/workspace` in the containers. Claude can read and edit all files in your project.

### Automatic Dependency Installation

Create a `.claude-container/config.json` file that specifies setup scripts for each container:

```json
{
  "setup": {
    "server": "scripts/server-setup.sh",
    "client": "scripts/client-setup.sh"
  }
}
```

- **server** - Runs in the tool-server container (has build tools: npm, pip, cargo, etc.)
- **client** - Runs in the Claude container (for client-side configuration)

Example server setup script:

```bash
# your-project/scripts/server-setup.sh
#!/bin/bash
set -e
npm install
# or: pip install -r requirements.txt
```

See `examples/project-setup/` for a complete example.

## Managing Tools

### Adding Tools from Catalog

List and add tools from the built-in catalog:

```bash
# List available tools
claude-container tools list

# Add a tool from the catalog
claude-container tools add npm
claude-container tools add python

# Rebuild containers after adding tools (if they need new packages)
claude-container build
```

### Adding Tools from External Repos

Add custom tools from any git repository:

```bash
claude-container tools add mytool --url https://github.com/user/tool-repo
```

The repository must contain a `tool.json` file at its root.

### Removing Tools

```bash
claude-container tools remove npm
```

### Manual Tool Setup

Create a directory in `tools.d/` with a `tool.json` manifest:

```bash
mkdir -p ~/.claude-container/tools/tools.d/npm
cat > ~/.claude-container/tools/tools.d/npm/tool.json << 'EOF'
{"binary": "/usr/bin/npm", "timeout": 600}
EOF
```

Optionally add:
- `setup.sh` - Run at container start
- `restricted.sh` - Intercept and filter commands

See `examples/npm-tool/` for a complete example.

## Directory Structure

```
claude-container/
├── pyproject.toml               # Python package config (for uv tool install)
├── docker-compose.yaml          # Container orchestration
│
├── src/claude_container/        # Python CLI package
│   ├── __init__.py
│   └── cli.py                   # Main CLI entry point
│
├── claude/                      # Claude Code container (client)
│   ├── Containerfile            # Python + Claude Code CLI
│   └── entrypoint.sh           # Minimal entrypoint (exec only)
│
├── client/                      # Tool client (source for install)
│   └── tool-client              # Socket client script (~90 lines)
│
├── tool-server/                 # Tool execution server
│   ├── Containerfile            # Tool binaries + server
│   ├── server.py                # Unix socket server
│   ├── tool-caller.py           # Tool execution + auto-discovery
│   ├── tool-setup.sh            # Entrypoint (runs setup scripts)
│   └── restricted/              # Global restriction wrapper examples
│       ├── git.sh.example
│       └── git.py.example
│
├── tools.d/                     # Tool definitions (auto-discovered)
│   └── git/
│       ├── tool.json            # {"binary": "/usr/bin/git", "timeout": 300}
│       └── setup.sh             # Git configuration at startup
│
├── catalog/                     # Built-in tool catalog
│   ├── index.json               # Tool metadata index
│   ├── npm/                     # npm tool definition
│   ├── python/                  # Python tool definition
│   └── ...
│
├── examples/                    # Example tool configurations
│   ├── npm-tool/                # Tool definition example
│   └── project-setup/           # Project setup hook example
│
└── scripts/
    ├── install.sh               # Creates ~/.claude-container/
    ├── run.sh                   # Legacy bash script
    └── check-instances.sh       # List running instances
```

### Host Runtime Directory

Created by `claude-container install`, mounted into both containers:

```
~/.claude-container/
├── repo/                # Copy of repo (docker-compose.yaml, Containerfiles)
├── tools/               # Single mount → /app/tools (read-only)
│   ├── bin/             # tool-client + relative symlinks
│   │   ├── tool-client
│   │   ├── git -> tool-client
│   │   └── ...
│   └── tools.d/         # Tool definitions
│       ├── git/
│       └── ...
├── sockets/             # Unix sockets (one per instance)
└── config/              # Configuration files
```

## Tool Customization

### Setup Scripts (`tools.d/{tool}/setup.sh`)

Run once at container start. Use for tool configuration:

```bash
# tools.d/git/setup.sh
git config --global --add safe.directory /workspace
git config --global init.defaultBranch main
```

### Restriction Wrappers (`tools.d/{tool}/restricted.sh`)

Called instead of the real binary. Decide what to allow:

```bash
# tools.d/git/restricted.sh - block force push
#!/bin/bash
case "$1" in
    push)
        for arg in "$@"; do
            [[ "$arg" == "--force" ]] && { echo "Blocked" >&2; exit 1; }
        done
        ;;
esac
exec "$TOOL_BINARY" "$@"
```

Environment variables available to wrappers:
- `TOOL_NAME` - Tool name (e.g., "git")
- `TOOL_BINARY` - Path to real binary (e.g., "/usr/bin/git")
- `TOOL_CWD` - Working directory
- `TOOL_ARGS` - JSON array of arguments

## Protocol

Socket communication using length-prefixed JSON:

```
┌──────────────┬─────────────────────────────────┐
│ 4 bytes      │ JSON payload                    │
│ (length BE)  │ {"tool": "git", "args": [...]}  │
└──────────────┴─────────────────────────────────┘
```

**Request**: `{"tool": "git", "args": ["status"], "cwd": "/workspace"}`

**Response**: `{"exit_code": 0, "stdout": "...", "stderr": ""}`

## CLI Commands

```bash
# Container management
claude-container              # Start Claude interactively (default)
claude-container run          # Same as above
claude-container start        # Start containers in background
claude-container stop         # Stop all containers
claude-container status       # Show container status
claude-container logs         # View logs
claude-container build        # Build container images
claude-container install      # Run installation script

# Tool management
claude-container tools list   # List available and installed tools
claude-container tools add <name>           # Add tool from catalog
claude-container tools add <name> --url <url>  # Add tool from git repo
claude-container tools remove <name>        # Remove an installed tool

# Run from a specific directory
claude-container -C /path/to/project
```

## License

MIT
