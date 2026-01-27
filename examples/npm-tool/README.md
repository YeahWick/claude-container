# Example: npm Tool

This is an example tool definition for npm, showing the `tools.d/` format.

## Files

- `tool.json` - Tool manifest (binary path and timeout)
- `setup.sh` - Configures npm cache and disables update notifier
- `restricted.sh` - Blocks `npm publish` and auth commands

## Install

```bash
# Copy to tools.d (either in repo or host directory)
cp -r examples/npm-tool tools.d/npm

# Or copy to host tools directory
cp -r examples/npm-tool ~/.claude-container/tools.d/npm

# Regenerate symlinks
./scripts/install.sh

# Rebuild to install npm binary in container
docker compose build tool-server
```

No code changes needed. The server auto-discovers the tool from `tools.d/npm/`.
