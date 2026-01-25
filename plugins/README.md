# Tool Server Plugins

This directory contains the tool server that executes commands on behalf of Claude.

## Structure

```
plugins/cli/
├── Containerfile        # Container image definition
├── server.py            # Socket server (receives requests)
├── tool-caller.py       # Tool execution (calls binaries)
├── tool-setup.sh        # Entrypoint (runs setup scripts)
├── setup.d/             # Per-tool setup scripts (run on start)
│   └── git.sh
└── restricted/          # Per-tool restriction wrappers (optional)
    ├── git.sh.example
    └── git.py.example
```

## Adding a New Tool

### Step 1: Create CLI wrapper symlink

In the `cli/` directory at the repo root:

```bash
cd cli
ln -s cli-wrapper mytool
```

### Step 2: Register the tool

Edit `plugins/cli/tool-caller.py` and add to the `tools` dict in `create_default_caller()`:

```python
def create_default_caller(...) -> ToolCaller:
    tools = {
        'git': ToolConfig(binary='/usr/bin/git', timeout=300),
        'mytool': ToolConfig(binary='/usr/bin/mytool', timeout=300),
    }
    ...
```

### Step 3: Install the binary

Edit `plugins/cli/Containerfile`:

```dockerfile
# Install tools (add more as needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    mytool \
    && rm -rf /var/lib/apt/lists/*
```

### Step 4: (Optional) Add setup script

Create `plugins/cli/setup.d/mytool.sh`:

```bash
#!/bin/bash
# mytool setup - runs at container start
command -v mytool &>/dev/null || exit 0

mytool config --global some.setting value
```

### Step 5: (Optional) Add restriction wrapper

Create `plugins/cli/restricted/mytool.sh`:

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

### Step 6: Rebuild

```bash
docker compose build cli-server
./scripts/install.sh  # Updates CLI wrappers
```

## Customization Patterns

### Pattern 1: Extend the Containerfile

For simple additions, edit `plugins/cli/Containerfile` directly.

### Pattern 2: Custom Containerfile

For more complex setups, create your own Containerfile that extends the base:

```dockerfile
# my-tools/Containerfile
FROM cli-server:v2

# Install additional tools
RUN apt-get update && apt-get install -y \
    nodejs npm cargo rustc \
    && rm -rf /var/lib/apt/lists/*

# Add custom setup scripts
COPY setup.d/ /app/setup.d/

# Add custom restrictions
COPY restricted/ /app/restricted/
```

Update `docker-compose.yaml`:

```yaml
cli-server:
  build:
    context: .
    dockerfile: my-tools/Containerfile
```

### Pattern 3: Mount custom scripts

For runtime customization without rebuilding:

```yaml
cli-server:
  volumes:
    - ./my-setup.d:/app/setup.d:ro
    - ./my-restricted:/app/restricted:ro
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

### Bash wrapper template

```bash
#!/bin/bash
set -e

# Access environment
echo "Tool: $TOOL_NAME"
echo "Binary: $TOOL_BINARY"
echo "CWD: $TOOL_CWD"

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

Setup scripts run once at container start. Use them for:

- Tool configuration (config files, environment)
- Credential setup
- Directory initialization

```bash
#!/bin/bash
# setup.d/mytool.sh

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
| `RESTRICTED_DIR` | `/app/restricted` | Restriction wrappers directory |
| `SETUP_DIR` | `/app/setup.d` | Setup scripts directory |

## Debugging

View tool server logs:

```bash
docker compose logs -f cli-server
```

Test a tool directly in the container:

```bash
docker compose exec cli-server python3 /app/tool-caller.py git status
```

Check if wrapper is being used:

```bash
docker compose exec cli-server ls -la /app/restricted/
```
