# claude-container

Run Claude Code CLI in a Linux container on macOS using [Apple's container tool](https://github.com/apple/container).

## Requirements

- Mac with Apple Silicon
- macOS 26 or later
- [Apple container tool](https://github.com/apple/container/releases) installed

## Setup

1. Install the container tool and start the service:
   ```bash
   container system start
   ```

2. Create your API key file:
   ```bash
   echo 'your_anthropic_api_key' > ~/.anthropic_key
   ```

3. Build the container:
   ```bash
   container build -t claude-code .
   ```

## Quick Start

### Option 1: Source the Aliases File (Recommended)

Add this to your `~/.bashrc` or `~/.zshrc`:

```bash
source /path/to/claude-container/aliases.sh
```

Then reload your shell and use the convenient aliases from any project:

```bash
cd ~/my-project
claude              # Start Claude Code
claude-rebuild      # Force rebuild project image
claude-image        # Show current project's image name

# Or use short versions:
cc                  # Same as 'claude'
cc-rebuild          # Same as 'claude-rebuild'
cc-image            # Same as 'claude-image'
```

### Option 2: Direct Script Execution

You can also run the scripts directly:

```bash
# From your project directory
/path/to/claude-container/run.sh
```

Or create a manual alias:
```bash
alias claude-container='/path/to/claude-container/run.sh'
```

## What Gets Mounted

The launcher script automatically mounts:
- **Current directory** → `/home/claude/workspace` (your project files)
- **~/.anthropic_key** → `/home/claude/.anthropic_key` (API authentication)

## Project-Specific Setup

You can create a project-specific setup script that installs additional tooling into a cached image layer. This is useful for installing:
- Language runtimes (Python, Go, Rust, Java, etc.)
- Build tools and linters
- Project-specific dependencies

### How It Works

1. Create a `.claude-container/` directory in your project root
2. Add either `setup.sh` (simple) or `Containerfile` (advanced)
3. When you run `run.sh`, it detects this and builds a project-specific image
4. The setup runs **once** during image build, not on every container start
5. Changes to setup files or dependency manifests trigger a rebuild

### Simple Setup (setup.sh)

Create `.claude-container/setup.sh` in your project:

```bash
#!/bin/bash
# Runs as root during image build
set -e

apt-get update

# Install Python
apt-get install -y python3 python3-pip python3-venv

# Install global tools
npm install -g typescript prettier eslint

# Clean up
apt-get clean
rm -rf /var/lib/apt/lists/*

echo "Setup complete!"
```

See `examples/.claude-container/setup.sh` for a full template with more options.

### Advanced Setup (Containerfile)

For full control, create `.claude-container/Containerfile`:

```dockerfile
FROM claude-code

USER root

# Multi-stage build, custom base images, etc.
RUN apt-get update && apt-get install -y python3 python3-pip

# Copy project files during build if needed
COPY requirements.txt /tmp/
RUN pip3 install -r /tmp/requirements.txt

USER claude
WORKDIR /home/claude/workspace
ENTRYPOINT ["/home/claude/start.sh"]
```

### Automatic Rebuild Detection

The image checksum includes:
- `.claude-container/setup.sh`
- `.claude-container/Containerfile`
- `package.json`, `requirements.txt`, `Gemfile`, `go.mod`, `Cargo.toml` (if present)

Changes to any of these files trigger an automatic rebuild.

### Force Rebuild

To force a rebuild even when files haven't changed:

```bash
./run.sh --rebuild
```

### Image Naming

Project-specific images are named `claude-code-<project>-<path-hash>:<checksum>`:
- `claude-code-my-app-a1b2c3d4:e5f6g7h8i9j0` - Built from `my-app/.claude-container/`

The path hash ensures projects with the same folder name in different locations (e.g., `~/work/my-app` and `~/personal/my-app`) don't collide.

Old images are automatically cleaned up when a new version is built.

## Usage Examples

### Start interactive session
```bash
claude              # Using alias
./run.sh           # Or direct script
```

### Run with a specific prompt
```bash
claude -p "explain this codebase"
```

### Continue a previous session
```bash
claude --continue
```

### Force rebuild project image
```bash
claude-rebuild      # Using alias
claude --rebuild   # Or with flag
./run.sh --rebuild # Or direct script
```

### Show current project's image name
```bash
claude-image       # Using alias
./image-name.sh   # Or direct script
```

## Manual Usage

If you prefer to run the container directly:

```bash
container run -it \
  -v $(pwd):/home/claude/workspace \
  -v ~/.anthropic_key:/home/claude/.anthropic_key:ro \
  claude-code
```

## Container Management

```bash
# Show image name for current project
claude-image                                # Using alias
/path/to/claude-container/image-name.sh    # Or direct script

# Force rebuild project image
claude-rebuild                              # Using alias

# List running containers
container ls

# List all containers
container ls -a

# List images
container images ls

# Rebuild the base image
container build -t claude-code .
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key (can also use ~/.anthropic_key file) | Yes |

## Building for Multiple Architectures

```bash
container build --arch amd64,arm64 -t claude-code .
```

## Proxy Container (Advanced)

The proxy container provides controlled access to external services with credential management and configurable restrictions. This is useful for:

- **Branch protection**: Block pushes to main/master branches
- **Credential injection**: Automatically inject GitHub tokens
- **Access control**: Restrict which repositories can be accessed
- **Extensibility**: Add new tools with their own access controls

### Quick Start with Proxy

1. Create a `.env` file with your configuration:
   ```bash
   cp .env.example .env
   # Edit .env and add your GITHUB_TOKEN
   ```

2. Start with proxy using docker-compose:
   ```bash
   ./run-with-proxy.sh
   # Or use the alias after sourcing aliases.sh:
   claude-proxy
   ```

### Proxy CLI Tools

Inside the Claude Code container, these tools are available:

```bash
# List all available proxy tools
proxy-tools

# GitHub operations (with branch protection)
proxy-github help              # Show all commands
proxy-github status            # Git status
proxy-github push origin branch # Push (blocks protected branches)
proxy-github pull              # Pull from remote
proxy-github clone <url>       # Clone repository
proxy-github branches          # List branches
proxy-github blocked           # Show protected branches
proxy-github check <branch>    # Check if push is allowed

# General proxy CLI
proxy-cli tools                # List server-side tools
proxy-cli tool github          # Get tool details
proxy-cli health               # Check proxy health
```

### Configuration

Edit `proxy/config.yaml` or use environment variables:

```yaml
# Branches blocked from push
github_blocked_branches:
  - main
  - master

# Repository access control (optional)
github_allowed_repos: []    # Empty = all allowed
github_blocked_repos:
  - github.com/company/production
```

Environment variables (in `.env`):
```bash
GITHUB_TOKEN=your_token_here
BLOCKED_BRANCHES=["main","master","production"]
```

### Adding New Tools

Tools are Python modules in `proxy/tools/`. Each tool should:

1. Create a file in `proxy/tools/` (e.g., `mytool.py`)
2. Define a FastAPI router and `TOOL_INFO` dict
3. Optionally create a CLI wrapper in `proxy-cli/`

Example tool structure:
```python
from fastapi import APIRouter

TOOL_INFO = {
    "name": "mytool",
    "description": "My custom tool",
    "version": "1.0.0",
}

router = APIRouter()

@router.get("/")
async def info():
    return TOOL_INFO

@router.post("/action")
async def do_action(param: str):
    # Tool logic here
    return {"success": True}
```

### Docker Compose Commands

```bash
# Start both containers
./run-with-proxy.sh
# Or: docker-compose up

# Start in background
./run-with-proxy.sh --detach

# View proxy logs
./run-with-proxy.sh --logs

# Open shell in running container
./run-with-proxy.sh --shell

# Stop containers
./run-with-proxy.sh --stop
# Or: docker-compose down

# Rebuild containers
./run-with-proxy.sh --build
```

### Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Docker Network                          │
│                                                             │
│  ┌─────────────────────┐      ┌─────────────────────────┐  │
│  │   Claude Code       │      │      Proxy Container     │  │
│  │   Container         │ HTTP │                          │  │
│  │                     │─────▶│  /github/push            │  │
│  │  proxy-github push  │      │  /github/pull            │  │
│  │  proxy-cli tools    │      │  /github/clone           │  │
│  │                     │      │  /tools                  │  │
│  │  Mounts:            │      │                          │  │
│  │  - workspace        │      │  Features:               │  │
│  │  - .anthropic_key   │      │  - Branch protection     │  │
│  └─────────────────────┘      │  - Credential injection  │  │
│                               │  - Access control        │  │
│                               └─────────────────────────────┤
└─────────────────────────────────────────────────────────────┘
```
