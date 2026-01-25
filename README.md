# Claude Container

A minimal container architecture for running Claude Code with controlled access to development tools.

## Architecture

```
┌────────────────────────────────────────────────────────────────────────┐
│                           HOST SYSTEM                                  │
├────────────────────────────────────────────────────────────────────────┤
│                                                                        │
│  ┌─────────────────────────┐       ┌────────────────────────────────┐  │
│  │    Claude Container     │       │      Tool Server Container     │  │
│  │                         │       │                                │  │
│  │  Claude Code CLI        │       │  setup.d/git.sh  (on start)    │  │
│  │         ↓               │       │         ↓                      │  │
│  │  git push origin main   │       │  restricted/git.sh (optional)  │  │
│  │         ↓               │       │         ↓                      │  │
│  │  /home/claude/bin/git   │ sock  │  /usr/bin/git push origin main │  │
│  │  (cli-wrapper)  ────────┼───────┼→ (real binary)                 │  │
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
| **claude** | Runs Claude Code CLI with wrapper scripts | `claude/Containerfile` |
| **cli-server** | Executes tools with optional restrictions | `plugins/cli/Containerfile` |

### Key Features

- **Minimal client** - Claude container only has lightweight wrappers
- **Server-side control** - All tool execution happens in the tool server
- **Per-tool setup** - `setup.d/{tool}.sh` scripts run at container start
- **Per-tool restrictions** - `restricted/{tool}.sh` wrappers intercept calls
- **Shared workspace** - Both containers see the same `/workspace` via bind mount

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

## Adding Tools

See [plugins/README.md](plugins/README.md) for detailed instructions.

**Quick example** - adding `npm`:

1. Add symlink in `cli/`:
   ```bash
   cd cli && ln -s cli-wrapper npm
   ```

2. Register in `plugins/cli/tool-caller.py`:
   ```python
   tools = {
       'git': ToolConfig(binary='/usr/bin/git', timeout=300),
       'npm': ToolConfig(binary='/usr/bin/npm', timeout=600),
   }
   ```

3. Install binary in `plugins/cli/Containerfile`:
   ```dockerfile
   RUN apt-get update && apt-get install -y npm
   ```

4. Rebuild: `docker compose build cli-server`

## Directory Structure

```
claude-container/
├── docker-compose.yaml          # Container orchestration
│
├── claude/                      # Claude Code container
│   └── Containerfile            # Python + Claude Code CLI
│
├── plugins/
│   ├── README.md                # Plugin development guide
│   └── cli/                     # Tool server
│       ├── Containerfile        # Tool binaries + server
│       ├── server.py            # Socket server
│       ├── tool-caller.py       # Tool execution logic
│       ├── tool-setup.sh        # Entrypoint (runs setup.d/)
│       ├── setup.d/             # Per-tool setup scripts
│       │   └── git.sh           # Git configuration
│       └── restricted/          # Per-tool restriction wrappers
│           ├── git.sh.example   # Example bash wrapper
│           └── git.py.example   # Example python wrapper
│
├── cli/                         # CLI wrappers (mounted into Claude)
│   ├── cli-wrapper              # Socket client (~70 lines)
│   └── git -> cli-wrapper       # Symlink per tool
│
└── scripts/
    ├── install.sh               # Creates ~/.claude-container/
    └── run.sh                   # Start/stop/status commands
```

## Tool Customization

### Setup Scripts (`setup.d/{tool}.sh`)

Run once at container start. Use for tool configuration:

```bash
# setup.d/git.sh
git config --global --add safe.directory /workspace
git config --global init.defaultBranch main
```

### Restriction Wrappers (`restricted/{tool}.sh`)

Called instead of the real binary. Decide what to allow:

```bash
# restricted/git.sh - block force push
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
```

## License

MIT
