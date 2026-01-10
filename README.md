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
