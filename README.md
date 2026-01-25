# Claude Container v2

A minimal container architecture for running Claude Code with controlled access to development tools.

## Architecture

Claude Container uses a simple **client-server boundary** where the CLI wrapper forwards all commands to a unified server:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        HOST SYSTEM                                   │
├─────────────────────────────────────────────────────────────────────┤
│                                                                      │
│  ┌──────────────────────┐     ┌──────────────────────────────────┐  │
│  │   Claude Container   │     │        CLI Server                │  │
│  │                      │     │                                  │  │
│  │   git push ...       │     │   Receives: {tool, args, cwd}    │  │
│  │        ↓             │     │                                  │  │
│  │   cli-wrapper  ──────┼─────┼─► Executes tool                  │  │
│  │                      │     │   Returns: {stdout, stderr, rc}  │  │
│  │   /run/plugins/      │     │                                  │  │
│  │     cli.sock         │     │   All restrictions enforced here │  │
│  └──────────────────────┘     └──────────────────────────────────┘  │
│                                                                      │
└─────────────────────────────────────────────────────────────────────┘
```

### Key Features

- **Minimal client** - Simple wrapper forwards everything to server
- **Clean boundary** - All validation/restrictions enforced server-side
- **Easy extensibility** - Add tools with symlink + config update
- **Single socket** - One server handles all tool requests

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

# Stop all containers
./scripts/run.sh stop
```

## Adding New Tools

Adding a new tool requires just two steps:

### 1. Create symlink

```bash
cd ~/.claude-container/cli
ln -s cli-wrapper npm
ln -s cli-wrapper cargo
```

### 2. Update server config

Edit `plugins/cli/server.py` and add to `ALLOWED_TOOLS`:

```python
ALLOWED_TOOLS = {
    'git': {'binary': '/usr/bin/git', 'timeout': 300},
    'npm': {'binary': '/usr/bin/npm', 'timeout': 600},
    'cargo': {'binary': '/usr/bin/cargo', 'timeout': 600},
}
```

Then rebuild the CLI server container. The new tool is immediately available.

## Directory Structure

```
claude-container/
├── docker-compose.yaml        # Container orchestration
│
├── claude/                    # Claude container
│   └── Containerfile
│
├── plugins/
│   └── cli/                   # Unified CLI server
│       ├── Containerfile
│       └── server.py          # Tool execution + restrictions
│
├── cli/                       # CLI wrappers (mounted into Claude)
│   ├── cli-wrapper            # Minimal client (~70 lines)
│   └── git -> cli-wrapper     # Symlinks for each tool
│
└── scripts/
    ├── install.sh             # First-time setup
    └── run.sh                 # Launcher
```

## Protocol

Client sends requests via Unix socket using length-prefixed JSON:

**Request**:
```json
{
  "tool": "git",
  "args": ["push", "origin", "feature/x"],
  "cwd": "/workspace"
}
```

**Response**:
```json
{
  "exit_code": 0,
  "stdout": "...",
  "stderr": ""
}
```

## Security Model

The architecture creates a clear security boundary:

- **Claude container**: Minimal, only has wrapper scripts
- **CLI server**: Handles execution with all restrictions

### Current Restrictions

The server validates:
- Tool is in `ALLOWED_TOOLS` whitelist
- Binary exists on the system

### Planned Restrictions

Additional server-side restrictions can be added:
- Command argument validation
- Branch protection for git
- Blocked subcommands per tool
- Rate limiting

## License

MIT
