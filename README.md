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
- **Project setup hook** - `.claude-container/setup.sh` runs at startup to install dependencies
- **Per-tool setup** - `tools.d/{tool}/setup.sh` scripts run at container start
- **Per-tool restrictions** - `tools.d/{tool}/restricted.sh` wrappers intercept calls
- **Hot-loading** - Tools added after startup are discovered on first use
- **Concurrent instances** - Multiple projects can run simultaneously
- **Single mount** - `bin/` and `tools.d/` share one host directory for clean relative symlinks

## Quick Start

```bash
# Clone
git clone https://github.com/YeahWick/claude-container.git
cd claude-container

# Install (creates ~/.claude-container/)
./scripts/install.sh

# Set API keys
export ANTHROPIC_API_KEY=your_key
export GITHUB_TOKEN=your_token  # optional

# Build and run
docker compose build
./scripts/run.sh
```

## Project Setup

When you run `./scripts/run.sh` from a directory, that directory is mounted to `/workspace` in the containers. Claude can read and edit all files in your project.

### Automatic Dependency Installation

Create a `.claude-container/setup.sh` script in your project to automatically install dependencies when the container starts:

```bash
# your-project/.claude-container/setup.sh
#!/bin/bash
set -e

# Node.js
if [ -f "package.json" ]; then
    npm install
fi

# Python
if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
fi
```

The setup script runs in the tool-server container before Claude starts, so all build tools are available.

See `examples/project-setup/` for a complete example.

## Adding Tools

Create a directory in `tools.d/` with a `tool.json` manifest. No code changes needed.

**Example** - adding `npm`:

1. Create the tool definition:
   ```bash
   mkdir -p tools.d/npm
   echo '{"binary": "/usr/bin/npm", "timeout": 600}' > tools.d/npm/tool.json
   ```

2. (Optional) Add a setup script (`tools.d/npm/setup.sh`):
   ```bash
   npm config set cache /tmp/npm-cache
   ```

3. (Optional) Add a restriction wrapper (`tools.d/npm/restricted.sh`):
   ```bash
   #!/bin/bash
   case "$1" in
       publish|adduser) echo "Blocked" >&2; exit 1 ;;
   esac
   exec "$TOOL_BINARY" "$@"
   ```

4. Install the binary in `tool-server/Containerfile`:
   ```dockerfile
   RUN apt-get update && apt-get install -y npm
   ```

5. Rebuild: `docker compose build tool-server`

See `examples/npm-tool/` for a complete example.

## Directory Structure

```
claude-container/
├── docker-compose.yaml          # Container orchestration
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
├── examples/                    # Example tool configurations
│   ├── npm-tool/                # Tool definition example
│   └── project-setup/           # Project setup hook example
│
└── scripts/
    ├── install.sh               # Creates ~/.claude-container/
    ├── run.sh                   # Start/stop/status commands
    └── check-instances.sh       # List running instances
```

### Host Runtime Directory

Created by `install.sh`, mounted into both containers:

```
~/.claude-container/
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

## Scripts

```bash
./scripts/run.sh          # Start Claude interactively
./scripts/run.sh start    # Start containers in background
./scripts/run.sh stop     # Stop all containers
./scripts/run.sh status   # Show container status
./scripts/run.sh logs     # View logs
./scripts/run.sh build    # Build container images
```

## License

MIT
