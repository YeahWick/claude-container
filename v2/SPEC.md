# Plugin Socket System v2 Specification

## Overview

This document specifies a plugin-based architecture for the Claude Container system where tools communicate via Unix domain sockets. Each tool plugin runs as an independent service that enforces its own rules and configuration.

## Architecture Goals

1. **Plugin-based extensibility** - Easy to add new tools without modifying core system
2. **Independent configuration** - Each tool manages its own rules/allowlists
3. **Security isolation** - Tools enforce their own permissions
4. **Simple protocol** - Lightweight JSON-over-socket communication
5. **Minimal Claude container** - Only wrapper scripts, no credentials or complex logic

## System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HOST SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────┐     ┌──────────────────────────────────┐  │
│  │   Claude Container   │     │      Plugin Containers           │  │
│  │                      │     │                                  │  │
│  │  ┌────────────────┐  │     │  ┌──────────┐  ┌──────────┐     │  │
│  │  │ Wrapper: git   │──┼─────┼─►│ git-tool │  │ gh-tool  │◄────┼──┤
│  │  ├────────────────┤  │     │  │ plugin   │  │ plugin   │     │  │
│  │  │ Wrapper: gh    │──┼─────┼──┴──────────┴──┴──────────┴─────┼──┤
│  │  ├────────────────┤  │     │                                  │  │
│  │  │ Wrapper: curl  │──┼─────┼─►┌──────────┐                   │  │
│  │  └────────────────┘  │     │  │curl-tool │                   │  │
│  │                      │     │  │ plugin   │                   │  │
│  │  /run/plugins/*.sock │     │  └──────────┘                   │  │
│  └──────────────────────┘     └──────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Socket Architecture Options

### Option A: Single Multiplexed Socket

All tools share one socket with command routing.

```
/run/plugins/agent.sock  (single socket)
    │
    ├── git commands  → git handler
    ├── gh commands   → gh handler
    └── curl commands → curl handler
```

**Request Format:**
```json
{
  "tool": "git",
  "action": "exec",
  "args": ["push", "origin", "main"],
  "cwd": "/workspace"
}
```

#### Pros
- **Simpler wrapper scripts** - All wrappers connect to same socket
- **Single health check** - One endpoint to monitor
- **Shared connection pool** - Less overhead for multiple rapid commands
- **Atomic configuration** - Single config file for all tools
- **Easier container setup** - One volume mount for socket

#### Cons
- **Single point of failure** - One socket crash affects all tools
- **Monolithic deployment** - Must redeploy everything for one tool change
- **Shared security context** - Harder to isolate tool permissions
- **Complex routing logic** - Central dispatcher adds complexity
- **Scaling limitations** - Can't scale tools independently

---

### Option B: One Socket Per Tool

Each tool has its own dedicated socket.

```
/run/plugins/git.sock   → git-plugin container
/run/plugins/gh.sock    → gh-plugin container
/run/plugins/curl.sock  → curl-plugin container
```

**Request Format:**
```json
{
  "action": "exec",
  "args": ["push", "origin", "main"],
  "cwd": "/workspace"
}
```

#### Pros
- **Fault isolation** - One tool crash doesn't affect others
- **Independent deployment** - Update/restart tools individually
- **Clear security boundaries** - Each tool has own config/credentials
- **Simple tool implementation** - No routing, just handle one command type
- **Easy to add new tools** - Just add new socket + container
- **Independent scaling** - Can have multiple instances of busy tools
- **Granular permissions** - Different socket permissions per tool

#### Cons
- **More socket files** - N sockets for N tools
- **Wrapper complexity** - Each wrapper needs correct socket path
- **Multiple health checks** - Must monitor each tool independently
- **More container overhead** - One container per tool (can mitigate with single multi-threaded process)
- **Configuration sprawl** - Each tool has own config file

---

### Option C: Hybrid - Category Sockets

Group related tools into category sockets.

```
/run/plugins/vcs.sock   → git, gh (version control)
/run/plugins/net.sock   → curl, wget (network)
/run/plugins/build.sock → npm, cargo, make (build tools)
```

#### Pros
- Balanced approach between A and B
- Related tools share credentials (e.g., git+gh share GITHUB_TOKEN)
- Fewer sockets than pure per-tool

#### Cons
- Arbitrary categorization decisions
- Partial fault isolation
- Still need routing within categories

---

## Recommendation: Option B (One Socket Per Tool)

For v2, we recommend **Option B** for the following reasons:

1. **Plugin philosophy** - True plugins should be independent
2. **Security** - Each tool enforces its own rules without trusting a central router
3. **Simplicity** - Each plugin is a simple, single-purpose service
4. **Extensibility** - Adding `npm`, `cargo`, etc. is trivial
5. **Failure isolation** - Critical for production reliability

The overhead of multiple sockets is minimal on modern systems, and container overhead can be eliminated by running all plugins in a single process with multiple socket listeners.

---

## Dynamic Plugin Discovery

A key feature of v2 is the ability to **add new tools to a running Claude container** without restarting it. This is achieved by using host-mounted volumes for both the CLI wrappers and socket files.

### Host Volume Architecture

```
HOST FILESYSTEM                         CONTAINERS
───────────────                         ──────────

~/.claude-container/
├── cli/                    ──────────► Claude: /home/claude/bin (in PATH)
│   ├── plugin-client                   (read-only mount)
│   ├── git
│   ├── gh
│   └── npm                 ← Add new wrappers here!
│
├── sockets/                ──────────► Claude: /run/plugins (read-only)
│   ├── git.sock                        Plugins: /run/plugins (read-write)
│   ├── gh.sock
│   └── npm.sock            ← New plugins create sockets here!
│
└── config/                 ──────────► Plugins: /etc/plugins (read-only)
    ├── git.yaml
    ├── gh.yaml
    └── npm.yaml            ← Add new configs here!
```

### Docker Compose Configuration

```yaml
volumes:
  # No named volumes - use host paths for hot-plug capability

services:
  claude:
    image: claude-code:v2
    volumes:
      # CLI wrappers - host directory mounted into PATH
      - ${CLAUDE_HOME:-~/.claude-container}/cli:/home/claude/bin:ro
      # Sockets - read-only access to plugin sockets
      - ${CLAUDE_HOME:-~/.claude-container}/sockets:/run/plugins:ro
      # Workspace
      - ${PROJECT_DIR:-.}:/workspace
    environment:
      - PATH=/home/claude/bin:/usr/local/bin:/usr/bin:/bin

  git-plugin:
    image: plugin-git:v2
    volumes:
      # Sockets - read-write to create socket file
      - ${CLAUDE_HOME:-~/.claude-container}/sockets:/run/plugins:rw
      # Config - plugin configuration
      - ${CLAUDE_HOME:-~/.claude-container}/config:/etc/plugins:ro
      # Workspace - same as claude container
      - ${PROJECT_DIR:-.}:/workspace
    environment:
      - GITHUB_TOKEN=${GITHUB_TOKEN}

  # Add more plugins as needed...
```

### Wrapper Script with Graceful Fallback

Wrappers detect if their plugin is available:

```bash
#!/bin/sh
# /home/claude/bin/git (host: ~/.claude-container/cli/git)

SOCKET="/run/plugins/git.sock"
TOOL="git"

# Check if plugin socket exists
if [ ! -S "$SOCKET" ]; then
    echo "error: $TOOL plugin not available" >&2
    echo "hint: start the $TOOL-plugin container" >&2
    exit 127
fi

# Forward to plugin
exec /home/claude/bin/plugin-client "$SOCKET" "$TOOL" "$@"
```

### Adding a New Plugin at Runtime

**Step 1: Create the wrapper script on host**
```bash
# On host machine
cat > ~/.claude-container/cli/npm << 'EOF'
#!/bin/sh
SOCKET="/run/plugins/npm.sock"
TOOL="npm"
if [ ! -S "$SOCKET" ]; then
    echo "error: $TOOL plugin not available" >&2
    exit 127
fi
exec /home/claude/bin/plugin-client "$SOCKET" "$TOOL" "$@"
EOF
chmod +x ~/.claude-container/cli/npm
```

**Step 2: Create plugin config on host**
```bash
cat > ~/.claude-container/config/npm.yaml << 'EOF'
plugin: npm
version: 1
rules:
  blocked_commands:
    - publish
    - unpublish
    - adduser
limits:
  timeout_seconds: 300
EOF
```

**Step 3: Start the plugin container**
```bash
docker compose up -d npm-plugin
# Socket appears at ~/.claude-container/sockets/npm.sock
```

**Step 4: Use immediately in Claude (no restart needed!)**
```bash
# Inside Claude container
$ npm install lodash
# Works! Plugin was added while container was running
```

### Plugin Availability Check

The `plugin-client` can list available plugins:

```bash
$ plugin-client --list
Available plugins:
  git     /run/plugins/git.sock     ✓ connected
  gh      /run/plugins/gh.sock      ✓ connected
  npm     /run/plugins/npm.sock     ✗ not available
  curl    /run/plugins/curl.sock    ✗ not available
```

### Directory Permissions

```bash
# Host setup script
mkdir -p ~/.claude-container/{cli,sockets,config}

# CLI directory - readable by container user
chmod 755 ~/.claude-container/cli

# Sockets directory - writable by plugin containers
# Use same UID/GID as container users (typically 1000)
chmod 770 ~/.claude-container/sockets
chown 1000:1000 ~/.claude-container/sockets

# Config directory - readable by plugins
chmod 755 ~/.claude-container/config
```

### Benefits of Host Volumes

| Feature | Named Volumes | Host Volumes |
|---------|---------------|--------------|
| Add new CLI wrappers at runtime | ✗ | ✓ |
| Add new plugins at runtime | ✓ | ✓ |
| Edit configs without rebuild | ✗ | ✓ |
| Inspect files from host | Difficult | Easy |
| Backup/version control | Manual export | Direct |
| Works across container restarts | ✓ | ✓ |

---

## Protocol Specification

### Transport
- Unix Domain Socket (AF_UNIX, SOCK_STREAM)
- Socket path: `/run/plugins/{tool}.sock`
- Permissions: 0660 (owner + group read/write)

### Message Format
- Length-prefixed JSON (4-byte big-endian length + JSON payload)
- Max message size: 64KB
- Encoding: UTF-8

### Request Schema
```json
{
  "action": "exec|health|capabilities",
  "args": ["arg1", "arg2"],
  "cwd": "/workspace/path",
  "env": {"KEY": "value"}
}
```

### Response Schema
```json
{
  "success": true,
  "exit_code": 0,
  "stdout": "output",
  "stderr": "errors",
  "error": "validation error message if any"
}
```

### Actions

| Action | Description |
|--------|-------------|
| `exec` | Execute the tool with given args |
| `health` | Return health status |
| `capabilities` | Return what operations are allowed |

---

## Plugin Interface

Each plugin must implement:

```python
class ToolPlugin:
    """Base interface for tool plugins."""

    def __init__(self, config_path: str):
        """Load tool-specific configuration."""
        pass

    def validate(self, args: list[str], cwd: str) -> tuple[bool, str]:
        """Validate if command is allowed. Returns (allowed, reason)."""
        pass

    def execute(self, args: list[str], cwd: str, env: dict) -> dict:
        """Execute command and return result dict."""
        pass

    def health(self) -> dict:
        """Return health status."""
        pass

    def capabilities(self) -> dict:
        """Return what this plugin allows."""
        pass
```

---

## Plugin Configuration

Each plugin has a YAML config file:

**Example: `/etc/plugins/git.yaml`**
```yaml
plugin: git
version: 1

# Credentials (loaded into secure memory)
credentials:
  GITHUB_TOKEN: ${GITHUB_TOKEN}

# Execution rules
rules:
  # Branch protection
  blocked_branches:
    - main
    - master
    - release/*

  allowed_branch_patterns:
    - claude/*
    - feature/*
    - fix/*

  # Command restrictions
  blocked_subcommands:
    - config --global
    - remote set-url

  # Allow/deny specific operations
  allow_force_push: false
  allow_delete_remote: false

# Limits
limits:
  timeout_seconds: 300
  max_output_bytes: 1048576

# Access control
access:
  allowed_uids: [1000]
  socket_permissions: 0660
```

**Example: `/etc/plugins/gh.yaml`**
```yaml
plugin: gh
version: 1

credentials:
  GH_TOKEN: ${GITHUB_TOKEN}

rules:
  blocked_subcommands:
    - auth
    - config set

  # Restrict to specific repos (optional)
  allowed_repos: []  # empty = all allowed

limits:
  timeout_seconds: 120
  max_output_bytes: 1048576

access:
  allowed_uids: [1000]
```

---

## Wrapper Script Template

Minimal shell script in Claude container:

**`/home/claude/bin/git`**
```bash
#!/bin/sh
SOCKET="/run/plugins/git.sock"
exec /usr/local/bin/plugin-client "$SOCKET" "$@"
```

**`plugin-client`** - Shared binary/script that:
1. Connects to specified socket
2. Sends JSON request with args
3. Receives JSON response
4. Outputs stdout/stderr
5. Exits with returned exit code

---

## Directory Structure

### Source Repository (v2/)

```
v2/
├── SPEC.md                    # This document
├── README.md                  # Quick start guide
├── docker-compose.yaml        # Container orchestration
│
├── claude/                    # Claude container image
│   └── Containerfile
│
├── plugins/                   # Plugin implementations
│   ├── base/                  # Shared plugin library
│   │   ├── __init__.py
│   │   ├── server.py          # Socket server base
│   │   ├── protocol.py        # Message encoding/decoding
│   │   └── security.py        # Credential handling, mlock
│   │
│   └── git/                   # Git plugin
│       ├── Containerfile
│       ├── plugin.py          # Git-specific logic
│       └── config.yaml        # Default config
│
├── cli/                       # CLI wrappers (copied to host on install)
│   ├── plugin-client          # Universal socket client
│   └── git                    # Git wrapper template
│
├── config/                    # Default configs (copied to host on install)
│   └── git.yaml
│
└── scripts/
    ├── install.sh             # First-time setup
    ├── run.sh                 # Launcher
    └── add-plugin.sh          # Helper to add new plugins
```

### Host Runtime Directory (~/.claude-container/)

Created by `install.sh`, mounted into containers:

```
~/.claude-container/
├── cli/                       # Mounted as /home/claude/bin (read-only)
│   ├── plugin-client          # Socket client binary
│   ├── git                    # git → git.sock
│   ├── gh                     # gh → gh.sock (add later)
│   └── ...                    # Add more wrappers anytime!
│
├── sockets/                   # Mounted as /run/plugins
│   ├── git.sock               # Created by git-plugin container
│   └── ...                    # New sockets appear as plugins start
│
└── config/                    # Mounted as /etc/plugins (read-only)
    ├── git.yaml               # Git plugin configuration
    └── ...                    # Add more configs anytime!
```

### Install Script

```bash
#!/bin/bash
# scripts/install.sh - First-time setup

CLAUDE_HOME="${CLAUDE_HOME:-$HOME/.claude-container}"

echo "Setting up Claude Container v2..."

# Create host directories
mkdir -p "$CLAUDE_HOME"/{cli,sockets,config}

# Set permissions (UID 1000 = container user)
chmod 755 "$CLAUDE_HOME"/cli
chmod 770 "$CLAUDE_HOME"/sockets
chmod 755 "$CLAUDE_HOME"/config

# Copy default CLI wrappers
cp -r cli/* "$CLAUDE_HOME"/cli/
chmod +x "$CLAUDE_HOME"/cli/*

# Copy default configs
cp -r config/* "$CLAUDE_HOME"/config/

echo "Installed to $CLAUDE_HOME"
echo ""
echo "To add a new tool:"
echo "  1. Add wrapper:  cp my-tool $CLAUDE_HOME/cli/"
echo "  2. Add config:   cp my-tool.yaml $CLAUDE_HOME/config/"
echo "  3. Start plugin: docker compose up -d my-tool-plugin"
```

---

## Security Model

### Credential Handling
1. Credentials loaded from environment at startup
2. Immediately locked in memory with `mlock()`
3. Environment variables cleared after loading
4. Credentials only injected into subprocess for execution
5. Never returned in responses

### Socket Security
1. Unix domain sockets (no network exposure)
2. Caller UID verified via `SO_PEERCRED`
3. Socket file permissions restrict access
4. Each plugin validates its own callers

### Command Validation
1. Each plugin enforces its own rules
2. Rules defined in config file
3. Validation happens before execution
4. Detailed error messages for blocked commands

### Container Isolation
1. Non-root users in all containers
2. Read-only root filesystems where possible
3. Minimal capabilities (only IPC_LOCK for mlock)
4. No network access for claude container
5. Shared socket volume is tmpfs (never persisted)

---

## MVP Scope

For initial implementation, focus on:

1. **Plugin base library** - Socket server, protocol, security utils
2. **Git plugin** - Full implementation with branch protection
3. **Plugin client** - Universal wrapper script
4. **Docker compose** - Two containers (claude + git-plugin)
5. **Basic config** - YAML parsing, environment variable substitution

Future additions:
- gh plugin
- curl plugin
- npm/cargo/make plugins
- Plugin hot-reload
- Metrics/logging
- Plugin marketplace/registry

---

## Next Steps

1. [ ] Create base plugin library
2. [ ] Implement git plugin
3. [ ] Create plugin-client binary
4. [ ] Write docker-compose.yaml
5. [ ] Test end-to-end flow
6. [ ] Document plugin creation process
