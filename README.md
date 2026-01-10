# claude-container

Docker container setup to run Claude Code CLI with your projects.

## Quick Start

### Build the container

```bash
docker build -t claude-code .
```

### Run interactively

```bash
docker run -it --rm \
  -e ANTHROPIC_API_KEY=your_api_key \
  -v /path/to/your/project:/home/claude/workspace \
  claude-code
```

### Using Docker Compose

1. Create a `.env` file with your API key:
   ```bash
   echo "ANTHROPIC_API_KEY=your_api_key" > .env
   ```

2. Place your project in the `workspace/` directory or modify the volume mount in `docker-compose.yml`

3. Run:
   ```bash
   docker compose run --rm claude-code
   ```

## Usage Examples

### Start interactive session
```bash
docker run -it --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $(pwd):/home/claude/workspace \
  claude-code
```

### Run with a specific prompt
```bash
docker run -it --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $(pwd):/home/claude/workspace \
  claude-code -p "explain this codebase"
```

### Continue a previous session
```bash
docker run -it --rm \
  -e ANTHROPIC_API_KEY=$ANTHROPIC_API_KEY \
  -v $(pwd):/home/claude/workspace \
  claude-code --continue
```

## Environment Variables

| Variable | Description | Required |
|----------|-------------|----------|
| `ANTHROPIC_API_KEY` | Your Anthropic API key | Yes |

## Volume Mounts

Mount your project directory to `/home/claude/workspace` for Claude Code to access your files.
