# Tool Server Socket Architecture Specification

## Overview

This document specifies the client/server architecture for the Claude Container system where tools communicate via Unix domain sockets. The tool server runs as an independent service that enforces its own rules and configuration.

## Architecture Goals

1. **Extensibility** - Easy to add new tools without modifying core system
2. **Independent configuration** - Each tool manages its own rules/allowlists
3. **Security isolation** - Tools enforce their own permissions
4. **Simple protocol** - Lightweight JSON-over-socket communication
5. **Minimal client container** - Only wrapper scripts, no credentials or complex logic

## System Components

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HOST SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────┐     ┌──────────────────────────────────┐  │
│  │   Claude (Client)    │     │        Tool Server                │  │
│  │                      │     │                                  │  │
│  │  ┌────────────────┐  │     │  ┌──────────┐  ┌──────────┐     │  │
│  │  │ Wrapper: git   │──┼─────┼─►│ git tool │  │ gh tool  │◄────┼──┤
│  │  ├────────────────┤  │     │  │ handler  │  │ handler  │     │  │
│  │  │ Wrapper: gh    │──┼─────┼──┴──────────┴──┴──────────┴─────┼──┤
│  │  ├────────────────┤  │     │                                  │  │
│  │  │ Wrapper: curl  │──┼─────┼─►┌──────────┐                   │  │
│  │  └────────────────┘  │     │  │curl tool │                   │  │
│  │                      │     │  │ handler  │                   │  │
│  │  /run/sockets/*.sock │     │  └──────────┘                   │  │
│  └──────────────────────┘     └──────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Socket Architecture Options

### Option A: Single Multiplexed Socket

All tools share one socket with command routing.

```
/run/sockets/tool.sock  (single socket)
    │
    ├── git commands  → git handler
    ├── gh commands   → gh handler
    └── curl commands → curl handler
```

**Request Format:**
```json
{
  "tool": "git",
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
/run/sockets/git.sock   → git handler
/run/sockets/gh.sock    → gh handler
/run/sockets/curl.sock  → curl handler
```

**Request Format:**
```json
{
  "args": ["push", "origin", "main"],
  "cwd": "/workspace"
}
```

#### Pros
- **Fault isolation** - One tool crash doesn't affect others
- **Independent deployment** - Update/restart tools individually
- **Clear security boundaries** - Each tool has own config/credentials
- **Simple tool implementation** - No routing, just handle one command type
- **Easy to add new tools** - Just add new socket + handler
- **Independent scaling** - Can have multiple instances of busy tools
- **Granular permissions** - Different socket permissions per tool

#### Cons
- **More socket files** - N sockets for N tools
- **Wrapper complexity** - Each wrapper needs correct socket path
- **Multiple health checks** - Must monitor each tool independently
- **More overhead** - One handler per tool
- **Configuration sprawl** - Each tool has own config file

---

### Option C: Hybrid - Category Sockets

Group related tools into category sockets.

```
/run/sockets/vcs.sock   → git, gh (version control)
/run/sockets/net.sock   → curl, wget (network)
/run/sockets/build.sock → npm, cargo, make (build tools)
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

## Current Implementation: Option A (Single Multiplexed Socket)

The current implementation uses **Option A** with a single tool server that handles all tools via one multiplexed socket. This was chosen for simplicity:

1. **Simple deployment** - Two containers: Claude (client) + tool-server
2. **Auto-discovery** - Tools registered from `tools.d/` directory, no code changes
3. **Hot-loading** - New tools discovered lazily on first request
4. **Centralized restrictions** - Per-tool wrappers managed in one place
5. **Minimal overhead** - One server process handles all tools

---

## Host Volume Architecture

```
HOST FILESYSTEM                         CONTAINERS
───────────────                         ──────────

~/.config/claude-container/
├── tools/                  ──────────► Both containers: /app/tools (read-only)
│   ├── bin/                            Claude: /app/tools/bin (in PATH)
│   │   ├── tool-client
│   │   ├── git -> tool-client
│   │   ├── gh -> tool-client
│   │   └── npm -> tool-client  ← Symlinks pre-generated by install.sh
│   │
│   └── tools.d/                        Both: /app/tools/tools.d
│       ├── git/
│       │   ├── tool.json
│       │   └── setup.sh
│       └── npm/                ← Add new tools here!
│           ├── tool.json
│           └── restricted.sh
│
├── sockets/                ──────────► Claude: /run/sockets (read-only)
│   └── tool-{id}.sock                 Tool Server: /run/sockets (read-write)
│
└── config/                 ──────────► Configuration files
```

### Podman Compose Configuration

```yaml
services:
  claude:
    image: claude-code:v2
    volumes:
      # Tools directory - bin/ (client + symlinks) and tools.d/ (definitions)
      - ${CLAUDE_HOME:-~/.config/claude-container}/tools:/app/tools:ro
      # Sockets - read-only access to tool server
      - ${CLAUDE_HOME:-~/.config/claude-container}/sockets:/run/sockets:ro
      # Workspace
      - ${PROJECT_DIR:-.}:/workspace
    environment:
      - PATH=/app/tools/bin:/usr/local/bin:/usr/bin:/bin
      - TOOL_SOCKET=/run/sockets/tool-${INSTANCE_ID}.sock

  tool-server:
    image: tool-server:v2
    volumes:
      # Sockets - read-write to create socket file
      - ${CLAUDE_HOME:-~/.config/claude-container}/sockets:/run/sockets:rw
      # Tools directory - for auto-discovery and setup scripts
      - ${CLAUDE_HOME:-~/.config/claude-container}/tools:/app/tools:ro
      # Workspace - same as claude container
      - ${PROJECT_DIR:-.}:/workspace
    environment:
      - TOOL_SOCKET=/run/sockets/tool-${INSTANCE_ID}.sock
      - GITHUB_TOKEN=${GITHUB_TOKEN}
```

---

## Protocol Specification

### Transport
- Unix Domain Socket (AF_UNIX, SOCK_STREAM)
- Socket path: `/run/sockets/tool-{instance_id}.sock`
- Permissions: 0660 (owner + group read/write)

### Message Format
- Length-prefixed JSON (4-byte big-endian length + JSON payload)
- Max message size: 64KB
- Encoding: UTF-8

### Request Schema
```json
{
  "tool": "git",
  "args": ["push", "origin", "main"],
  "cwd": "/workspace"
}
```

### Response Schema
```json
{
  "exit_code": 0,
  "stdout": "output",
  "stderr": "errors",
  "error": "error message if any"
}
```

---

## Security Model

### Socket Security
1. Unix domain sockets (no network exposure)
2. Socket file permissions restrict access
3. Each tool can have its own restriction wrapper

### Command Validation
1. Per-tool restriction wrappers enforce rules
2. Wrappers defined in `tools.d/{tool}/restricted.sh` or `restricted.py`
3. Global fallback wrappers in `/app/restricted/`
4. Validation happens before execution

### Container Isolation
1. Non-root users in all containers
2. Minimal capabilities
3. Shared socket volume for IPC only
4. Shared workspace via bind mount

---

## Directory Structure

### Source Repository

```
claude-container/
├── SPEC.md                    # This document
├── README.md                  # Quick start guide
├── podman-compose.yaml        # Container orchestration
│
├── claude/                    # Claude container (client)
│   ├── Containerfile
│   └── entrypoint.sh         # Minimal entrypoint (exec only)
│
├── client/                    # Tool client (source for install)
│   └── tool-client            # Socket client script
│
├── tool-server/               # Tool execution server
│   ├── Containerfile
│   ├── server.py              # Socket server
│   ├── tool-caller.py         # Tool execution + auto-discovery
│   ├── tool-setup.sh          # Entrypoint (runs per-tool setup)
│   └── restricted/            # Global restriction wrapper examples
│
├── tools.d/                   # Tool definitions (auto-discovered)
│   └── git/
│       ├── tool.json
│       └── setup.sh
│
└── scripts/
    ├── install.sh             # First-time setup
    ├── run.sh                 # Container management
    └── check-instances.sh     # Instance status
```

### Host Runtime Directory (~/.config/claude-container/)

Created by `install.sh`, mounted into containers:

```
~/.config/claude-container/
├── tools/                     # Single mount: /app/tools (read-only)
│   ├── bin/                   # tool-client + relative symlinks
│   │   ├── tool-client        # Socket client script
│   │   ├── git -> tool-client # Auto-generated by install.sh
│   │   └── ...
│   └── tools.d/               # Tool definitions
│       ├── git/
│       └── ...
│
├── sockets/                   # Mounted as /run/sockets
│   └── tool-{id}.sock        # Created by tool server
│
├── config/                    # Configuration files
└── .env                       # API keys (loaded by CLI automatically)
```

---

## Adding a New Tool

1. Create a tool directory in `tools.d/`:
   ```bash
   mkdir -p tools.d/npm
   echo '{"binary": "/usr/bin/npm", "timeout": 600}' > tools.d/npm/tool.json
   ```

2. (Optional) Add setup and restriction scripts:
   ```bash
   # tools.d/npm/setup.sh - runs at container start
   # tools.d/npm/restricted.sh - called instead of binary
   ```

3. Install the binary in `tool-server/Containerfile`:
   ```dockerfile
   RUN apt-get update && apt-get install -y npm
   ```

4. Re-run install and rebuild:
   ```bash
   claude-container install
   claude-container build
   ```

   Or use the catalog:
   ```bash
   claude-container tools add npm
   claude-container build
   ```

The tool is auto-discovered by the server at startup. Hot-loading also works for tools added after the server is running.
