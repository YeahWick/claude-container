# Claude Code Container

Run Claude Code CLI in a containerized environment with secure git/gh access.

## Features

- **Isolated environment**: Claude Code runs in a container
- **Secure credentials**: GitHub token stored in locked memory, never exposed to Claude
- **Branch protection**: Block pushes to main/master (configurable)
- **Same CLI**: Use `git` and `gh` commands normally - they're proxied securely

## Requirements

- Podman or Docker
- podman-compose or docker-compose

```bash
# macOS
brew install podman podman-compose
podman machine init && podman machine start

# Fedora/RHEL
sudo dnf install podman podman-compose

# Ubuntu/Debian
sudo apt install podman
pip install podman-compose
```

## Quick Start

1. Create your API key file:
   ```bash
   echo 'your_anthropic_api_key' > ~/.anthropic_key
   ```

2. Set your GitHub token:
   ```bash
   export GITHUB_TOKEN=ghp_your_token_here
   ```

3. Run Claude Code:
   ```bash
   ./run.sh
   ```

## How It Works

```
┌─────────────────────┐     ┌──────────────────────┐
│  Claude Container   │     │   Command Agent      │
│                     │     │                      │
│  git push origin x  │────▶│  Validates branch    │
│  (CLI wrapper)      │     │  Injects credentials │
│                     │◀────│  Runs real git       │
│  Gets: output only  │     │  Returns output      │
└─────────────────────┘     └──────────────────────┘
        │                            │
        ▼                            ▼
   Your workspace              GitHub token
   (mounted)                   (locked memory)
```

The `git` and `gh` commands in the Claude container are wrappers that forward to the command-agent via Unix socket. The agent:
- Validates operations (branch protection)
- Injects credentials
- Executes the real command
- Returns output (never credentials)

## Configuration

Copy `.env.example` to `.env` and configure:

```bash
# Required
GITHUB_TOKEN=ghp_your_token

# Optional - branch protection
BLOCKED_BRANCHES=["main","master"]
ALLOWED_BRANCH_PATTERNS=["claude/*","feature/*"]
```

## Commands

```bash
./run.sh              # Start Claude Code
./run.sh --build      # Rebuild containers
./run.sh --stop       # Stop containers
./run.sh --shell      # Open shell in running container
./run.sh --logs       # View command-agent logs
./run.sh --status     # Show container status
./run.sh --help       # Show help
```

## Inside the Container

```bash
# These work normally - they're proxied to the agent
git status
git push origin my-branch
git pull
gh pr create
gh issue list

# Check agent status
agent-status
```

## Branch Protection

By default, pushes to `main` and `master` are blocked. Configure with:

```bash
# Block specific branches
BLOCKED_BRANCHES=["main","master","production"]

# Or use allowlist mode - only these patterns allowed
ALLOWED_BRANCH_PATTERNS=["claude/*","feature/*","fix/*"]
```

## Security

- **No credential exposure**: GitHub token stored in mlock'd memory, cleared from environment
- **Process isolation**: Command agent runs separately with minimal privileges
- **SO_PEERCRED**: Caller verification via kernel
- **Read-only container**: Agent container is read-only
- **No network to Claude**: Claude container can't reach the internet directly
