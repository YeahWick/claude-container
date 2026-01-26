# Tool Server Plugins

This directory contains the tool server that executes commands on behalf of Claude.

## Structure

```
plugins/cli/
├── Containerfile        # Container image definition
├── server.py            # Socket server (receives requests)
├── tool-caller.py       # Tool execution with auto-discovery
├── tool-setup.sh        # Entrypoint (runs setup scripts from tools.d/)
└── restricted/          # Global restriction wrappers (optional)
    ├── git.sh.example
    └── git.py.example

tools.d/                 # Tool definitions (auto-discovered)
└── git/
    ├── tool.json        # Required: tool manifest
    └── setup.sh         # Optional: runs at container start
```

## Adding a New Tool

Tools are auto-discovered from the `tools.d/` directory. No code changes or symlinks needed.

### Step 1: Create a tool directory

```bash
mkdir -p tools.d/mytool
```

### Step 2: Create tool.json manifest

```bash
cat > tools.d/mytool/tool.json << 'EOF'
{
  "binary": "/usr/bin/mytool",
  "timeout": 300
}
EOF
```

The `binary` field is optional. If omitted, the system auto-detects from
`/usr/bin/{name}`, `/usr/local/bin/{name}`, or `/bin/{name}`.

### Step 3: (Optional) Add setup script

Create `tools.d/mytool/setup.sh`:

```bash
#!/bin/bash
# Runs once at container start
command -v mytool &>/dev/null || exit 0

mytool config --global some.setting value
```

### Step 4: (Optional) Add restriction wrapper

Create `tools.d/mytool/restricted.sh` or `tools.d/mytool/restricted.py`:

```bash
#!/bin/bash
# Block dangerous subcommands
case "$1" in
    dangerous-command)
        echo "Error: This command is not allowed" >&2
        exit 1
        ;;
esac

# Pass through to real binary
exec "$TOOL_BINARY" "$@"
```

### Step 5: Install the binary

Edit `plugins/cli/Containerfile`:

```dockerfile
# Install tools (add more as needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    mytool \
    && rm -rf /var/lib/apt/lists/*
```

### Step 6: Rebuild

```bash
docker compose build cli-server
./scripts/install.sh  # Copies tool definitions and generates symlinks
```

## Adding a Tool from an External Repo

The simplest workflow for tools maintained in separate repositories:

```bash
# Clone the tool repo
git clone https://github.com/example/my-tool-plugin.git

# Copy into tools.d
cp -r my-tool-plugin ~/.claude-container/tools.d/mytool

# Re-run install to generate symlinks
./scripts/install.sh

# Rebuild if the binary needs installing in the container
docker compose build cli-server
```

A tool repo just needs:
```
my-tool-plugin/
├── tool.json        # Required: {"binary": "/usr/bin/mytool", "timeout": 300}
├── setup.sh         # Optional: container startup configuration
├── restricted.sh    # Optional: permission wrapper (bash)
└── restricted.py    # Optional: permission wrapper (python, takes priority)
```

## How Auto-Discovery Works

### Server side (tool-caller.py)
1. At startup, scans `TOOLS_DIR` (default: `/app/tools.d/`)
2. Each subdirectory becomes a registered tool
3. `tool.json` provides binary path and timeout
4. If no `tool.json`, binary is auto-detected from standard paths
5. Restriction wrappers checked in tool directory first, then global `restricted/`

### Client side (entrypoint.sh)
1. At container start, scans `TOOLS_DIR`
2. Creates symlinks in `/home/claude/bin/` pointing to `cli-wrapper`
3. Claude sees each tool as a regular command in PATH

### Install script
1. Copies tool definitions from repo `tools.d/` to `~/.claude-container/tools.d/`
2. Generates symlinks in `~/.claude-container/cli/` for each tool
3. Preserves user customizations (won't overwrite setup/restricted scripts)

## Customization Patterns

### Pattern 1: Mount tool definitions at runtime

No rebuild needed. Add tools to `~/.claude-container/tools.d/` and restart:

```bash
mkdir -p ~/.claude-container/tools.d/curl
echo '{"binary": "/usr/bin/curl", "timeout": 60}' > ~/.claude-container/tools.d/curl/tool.json
./scripts/install.sh   # Generate symlinks
# Restart containers
```

### Pattern 2: Custom Containerfile

For more complex setups, create your own Containerfile that extends the base:

```dockerfile
# my-tools/Containerfile
FROM cli-server:v2

# Install additional tools
RUN apt-get update && apt-get install -y \
    nodejs npm cargo rustc \
    && rm -rf /var/lib/apt/lists/*

# Add custom tool definitions
COPY tools.d/ /app/tools.d/
```

Update `docker-compose.yaml`:

```yaml
cli-server:
  build:
    context: .
    dockerfile: my-tools/Containerfile
```

### Pattern 3: Volume mount external tools

Mount a directory from another repo directly:

```yaml
cli-server:
  volumes:
    - ./my-external-tools:/app/tools.d:ro
```

## Writing Restriction Wrappers

Wrappers receive these environment variables:

| Variable | Description | Example |
|----------|-------------|---------|
| `TOOL_NAME` | Tool name | `git` |
| `TOOL_BINARY` | Real binary path | `/usr/bin/git` |
| `TOOL_CWD` | Working directory | `/workspace` |
| `TOOL_ARGS` | JSON array of args | `["push", "origin", "main"]` |

Arguments are also passed as positional parameters (`$@` or `sys.argv[1:]`).

### Wrapper lookup order

1. `tools.d/{tool}/restricted.py` (tool-specific, Python)
2. `tools.d/{tool}/restricted.sh` (tool-specific, Bash)
3. `tools.d/{tool}/restricted` (tool-specific, any executable)
4. `restricted/{tool}.py` (global, Python)
5. `restricted/{tool}.sh` (global, Bash)
6. `restricted/{tool}` (global, any executable)

### Bash wrapper template

```bash
#!/bin/bash
set -e

# Check arguments
case "$1" in
    blocked-subcommand)
        echo "Error: Not allowed" >&2
        exit 1
        ;;
esac

# Pass through to real binary
exec "$TOOL_BINARY" "$@"
```

### Python wrapper template

```python
#!/usr/bin/env python3
import os
import subprocess
import sys

TOOL_BINARY = os.environ['TOOL_BINARY']
args = sys.argv[1:]

# Check arguments
if args and args[0] == 'blocked-subcommand':
    print("Error: Not allowed", file=sys.stderr)
    sys.exit(1)

# Pass through to real binary
result = subprocess.run([TOOL_BINARY] + args)
sys.exit(result.returncode)
```

## Writing Setup Scripts

Setup scripts run once at container start. Place them in `tools.d/{tool}/setup.sh`:

```bash
#!/bin/bash
# tools.d/mytool/setup.sh

# Skip if tool not installed
command -v mytool &>/dev/null || exit 0

# Configure
mytool config --global user.name "Claude"
mytool config --global some.setting value

# Create directories
mkdir -p ~/.mytool/cache
```

## Environment Variables

The tool server respects these environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `CLI_SOCKET` | `/run/plugins/cli.sock` | Socket path |
| `WORKSPACE` | `/workspace` | Default working directory |
| `TOOLS_DIR` | `/app/tools.d` | Tool definitions directory |
| `RESTRICTED_DIR` | `/app/restricted` | Global restriction wrappers directory |

## Debugging

View tool server logs:

```bash
docker compose logs -f cli-server
```

Test a tool directly in the container:

```bash
docker compose exec cli-server python3 /app/tool_caller.py git status
```

List discovered tools:

```bash
docker compose exec cli-server ls -la /app/tools.d/
```

Check which wrapper is being used for a tool:

```bash
docker compose exec cli-server ls -la /app/tools.d/git/restricted.* 2>/dev/null
docker compose exec cli-server ls -la /app/restricted/git.* 2>/dev/null
```
