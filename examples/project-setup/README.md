# Project Setup Hook

The project setup hook allows you to automatically install project dependencies when starting Claude Container.

## Usage

1. Create a `.claude-container/config.json` file in your project root
2. Set the `setup.server` and/or `setup.client` fields to point to your setup scripts
3. Run `claude-container` - your setup scripts run automatically before Claude starts

## Config File Format

```json
{
  "setup": {
    "server": "scripts/server-setup.sh",
    "client": "scripts/client-setup.sh"
  }
}
```

- **server** - Runs in the tool-server container (has build tools: npm, pip, etc.)
- **client** - Runs in the Claude container (for client-side configuration)

Both fields are optional. Only specify what you need.

## Example

```bash
# In your project directory
mkdir -p .claude-container scripts

# Create config
cat > .claude-container/config.json << 'EOF'
{
  "setup": {
    "server": "scripts/server-setup.sh"
  }
}
EOF

# Create server setup script
cat > scripts/server-setup.sh << 'EOF'
#!/bin/bash
set -e
npm install
EOF
chmod +x scripts/server-setup.sh
```

## How It Works

When you run `claude-container` from your project directory:

1. Your project is mounted to `/workspace` in both containers
2. The tool-server starts and runs tool setup scripts (git config, etc.)
3. The tool-server reads `.claude-container/config.json`
4. **Server setup script runs** in tool-server container
5. Claude container starts and runs **client setup script** (if configured)
6. Claude starts with full access to your project and installed dependencies

## When to Use Each Container

### Server Setup (tool-server container)
Use for tasks requiring build tools:
- Installing dependencies (`npm install`, `pip install`, `cargo build`)
- Compiling code
- Running database migrations
- Any task that needs tools not available in the Claude container

### Client Setup (Claude container)
Use for lightweight configuration:
- Setting up shell aliases
- Creating workspace directories
- Configuring environment-specific settings

## Tips

- Use `set -e` to fail fast if any command fails
- Keep setup scripts idempotent (safe to run multiple times)
- Setup script paths are relative to your project root

## Caching Dependencies

For faster startup with large dependency trees:

```bash
# Node.js - use workspace-local cache
npm config set cache /workspace/.npm-cache

# Python - use workspace-local virtualenv
python -m venv /workspace/.venv
source /workspace/.venv/bin/activate
pip install -r requirements.txt
```
