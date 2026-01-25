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

```
v2/
├── SPEC.md                    # This document
├── README.md                  # Quick start guide
├── docker-compose.yaml        # Container orchestration
│
├── claude/                    # Claude container
│   ├── Containerfile
│   └── bin/
│       ├── plugin-client      # Universal socket client
│       ├── git                # Wrapper → git.sock
│       ├── gh                 # Wrapper → gh.sock
│       └── curl               # Wrapper → curl.sock
│
├── plugins/                   # Plugin implementations
│   ├── base/                  # Shared plugin library
│   │   ├── __init__.py
│   │   ├── server.py          # Socket server base
│   │   ├── protocol.py        # Message encoding/decoding
│   │   └── security.py        # Credential handling, mlock
│   │
│   ├── git/                   # Git plugin
│   │   ├── Containerfile
│   │   ├── plugin.py          # Git-specific logic
│   │   └── config.yaml        # Default config
│   │
│   ├── gh/                    # GitHub CLI plugin
│   │   ├── Containerfile
│   │   ├── plugin.py
│   │   └── config.yaml
│   │
│   └── curl/                  # Curl plugin
│       ├── Containerfile
│       ├── plugin.py
│       └── config.yaml
│
├── config/                    # User config (mounted)
│   ├── git.yaml
│   ├── gh.yaml
│   └── curl.yaml
│
└── scripts/
    ├── run.sh                 # Launcher
    └── add-plugin.sh          # Helper to add new plugins
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
