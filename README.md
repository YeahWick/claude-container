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

The easiest way to run Claude Code is with the launcher script:

```bash
# From your project directory
/path/to/claude-container/run.sh
```

Or create an alias:
```bash
alias claude-container='/path/to/claude-container/run.sh'
```

Then just run from any project:
```bash
cd ~/my-project
claude-container
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
./run.sh
```

### Run with a specific prompt
```bash
./run.sh -p "explain this codebase"
```

### Continue a previous session
```bash
./run.sh --continue
```

### Force rebuild project image
```bash
./run.sh --rebuild
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
/path/to/claude-container/image-name.sh

# List running containers
container ls

# List all containers
container ls -a

# List images
container images ls

# Rebuild the image
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
