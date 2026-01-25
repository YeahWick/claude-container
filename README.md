# Claude Container v2

A secure, plugin-based container architecture for running Claude Code with controlled access to development tools.

## Architecture

Claude Container v2 uses a **socket-based plugin system** where each tool runs as an independent service:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HOST SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────┐     ┌──────────────────────────────────┐  │
│  │   Claude Container   │     │      Plugin Containers           │  │
│  │                      │     │                                  │  │
│  │  ┌────────────────┐  │     │  ┌──────────┐                   │  │
│  │  │ Wrapper: git   │──┼─────┼─►│ git-tool │                   │  │
│  │  └────────────────┘  │     │  │ plugin   │                   │  │
│  │                      │     │  └──────────┘                   │  │
│  │  /run/plugins/*.sock │     │                                  │  │
│  └──────────────────────┘     └──────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Features

- **One socket per tool** - Each plugin has its own Unix socket for isolation
- **Plugin-based extensibility** - Easy to add new tools without modifying core system
- **Git hook enforcement** - Branch protection enforced by git itself via hooks
- **Secure credential handling** - Credentials locked in memory, never exposed
- **Hot-pluggable** - Add new plugins without restarting Claude

## Quick Start

### Prerequisites

- Docker or Podman with Docker Compose
- GitHub token (optional, for authenticated git operations)

### Installation

```bash
# Clone the repository
git clone https://github.com/YeahWick/claude-container.git
cd claude-container

# Install (creates ~/.claude-container directory)
./scripts/install.sh

# Set your API keys
export ANTHROPIC_API_KEY=your_key
export GITHUB_TOKEN=your_github_token

# Build containers
docker compose build

# Run Claude
./scripts/run.sh
```

### Usage

```bash
# Start Claude interactively
./scripts/run.sh

# Start all containers in background
./scripts/run.sh start

# Check status
./scripts/run.sh status

# View logs
./scripts/run.sh logs git-plugin

# Stop all containers
./scripts/run.sh stop
```

## Git Plugin

The git plugin provides controlled git access with:

### Branch Protection

Protected branches cannot be pushed to directly:
- `main`, `master`
- `release/*`, `production`

Claude must create feature branches matching allowed patterns:
- `claude/*`
- `feature/*`, `fix/*`, `bugfix/*`, `hotfix/*`

### Git Hook Enforcement

The plugin uses **git hooks** for defense-in-depth enforcement:

1. **pre-push hook** - Blocks pushes to protected branches
2. **pre-commit hook** - Placeholder for future checks
3. **commit-msg hook** - Placeholder for message validation

Hooks are automatically installed when repositories are cloned or initialized.

### Blocked Operations

- Force push (`git push -f`)
- Remote branch deletion (`git push -d`)
- Global config changes (`git config --global`)
- Remote URL modification

### Configuration

Edit `~/.claude-container/config/git.yaml`:

```yaml
rules:
  blocked_branches:
    - main
    - master
  allowed_branch_patterns:
    - claude/*
    - feature/*
  allow_force_push: false
  allow_delete_remote: false
```

## Adding New Plugins

1. **Create wrapper script**:
```bash
cat > ~/.claude-container/cli/npm << 'EOF'
#!/bin/sh
SOCKET="/run/plugins/npm.sock"
if [ ! -S "$SOCKET" ]; then
    echo "error: npm plugin not available" >&2
    exit 127
fi
exec plugin-client "$SOCKET" "$@"
EOF
chmod +x ~/.claude-container/cli/npm
```

2. **Create plugin configuration**:
```bash
cat > ~/.claude-container/config/npm.yaml << 'EOF'
plugin: npm
version: 1
rules:
  blocked_subcommands:
    - publish
    - unpublish
EOF
```

3. **Add service to docker-compose.yaml**

4. **Start the plugin**:
```bash
docker compose up -d npm-plugin
```

The plugin is immediately available - no restart needed!

## Directory Structure

```
claude-container/
├── SPEC.md                    # Full specification
├── docker-compose.yaml        # Container orchestration
│
├── claude/                    # Claude container
│   └── Containerfile
│
├── plugins/                   # Plugin implementations
│   ├── base/                  # Shared plugin library
│   │   ├── protocol.py        # Socket protocol
│   │   ├── server.py          # Plugin server base
│   │   └── security.py        # Credential handling
│   │
│   └── git/                   # Git plugin
│       ├── Containerfile
│       ├── plugin.py          # Git-specific logic
│       └── main.py            # Entry point
│
├── cli/                       # CLI wrappers
│   ├── plugin-client          # Universal socket client
│   └── git                    # Git wrapper
│
├── config/                    # Default configurations
│   └── git.yaml
│
└── scripts/
    ├── install.sh             # First-time setup
    └── run.sh                 # Launcher
```

## Security Model

### Credential Protection
- Loaded from environment at startup
- Locked in memory with `mlock()` to prevent swapping
- Environment variables cleared after loading
- Never included in responses

### Socket Security
- Unix domain sockets (no network exposure)
- File permissions restrict access
- Peer credentials verified via `SO_PEERCRED`

### Command Validation
- Pre-execution validation in plugin
- Git hooks for defense-in-depth
- Detailed error messages for blocked operations

## Protocol

Plugins communicate via length-prefixed JSON over Unix sockets:

**Request**:
```json
{
  "action": "exec",
  "args": ["push", "origin", "claude/feature"],
  "cwd": "/workspace",
  "env": {}
}
```

**Response**:
```json
{
  "success": true,
  "exit_code": 0,
  "stdout": "...",
  "stderr": "",
  "error": null
}
```

## License

MIT
