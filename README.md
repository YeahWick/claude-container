# claude-container

Run Claude Code CLI in a Linux container on macOS using [Apple's container tool](https://github.com/apple/container).

## Requirements

- Mac with Apple Silicon
- macOS 26 or later
- [Apple container tool](https://github.com/apple/container/releases) installed

## Setup

Install the container tool if you haven't already:

```bash
# Download and install from releases page, then start the service
container system start
```

## Quick Start

### Build the container

```bash
container build -t claude-code .
```

### Run interactively

```bash
container run -it \
  -e ANTHROPIC_API_KEY=your_api_key \
  -v /path/to/your/project:/home/claude/workspace \
  claude-code
```

## Usage Examples

### Start interactive session
```bash
container run -it \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $(pwd):/home/claude/workspace \
  claude-code
```

### Run with a specific prompt
```bash
container run -it \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $(pwd):/home/claude/workspace \
  claude-code -p "explain this codebase"
```

### Continue a previous session
```bash
container run -it \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $(pwd):/home/claude/workspace \
  claude-code --continue
```

## Container Management

```bash
# List running containers
container ls

# List all containers
container ls -a

# List images
container images ls
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | Yes |

## Volume Mounts

Mount your project directory to `/home/claude/workspace` for Claude Code to access your files.

## Building for Multiple Architectures

```bash
container build --arch amd64,arm64 -t claude-code .
```
