# Project Setup Hook

The project setup hook allows you to automatically install project dependencies when starting Claude Container.

## Usage

1. Create a `.claude-container/config.json` file in your project root
2. Set the `setup` field to point to your setup script (relative to project root)
3. Run `claude-container` - your setup script runs automatically before Claude starts

## Config File Format

```json
{
  "setup": "scripts/setup.sh"
}
```

The `setup` field is a path relative to your project root.

## Example

```bash
# In your project directory
mkdir -p .claude-container
echo '{"setup": "scripts/setup.sh"}' > .claude-container/config.json

# Create your setup script
mkdir -p scripts
cat > scripts/setup.sh << 'EOF'
#!/bin/bash
set -e
npm install
EOF
chmod +x scripts/setup.sh
```

## How It Works

When you run `claude-container` from your project directory:

1. Your project is mounted to `/workspace` in the containers
2. The tool-server starts and runs tool setup scripts (git config, etc.)
3. The tool-server reads `.claude-container/config.json`
4. **Your project's setup script runs** (as specified in config)
5. Claude starts with full access to your project and installed dependencies

## Tips

- The setup script runs in the **tool-server** container, which has build tools installed
- Use `set -e` to fail fast if any command fails
- Keep setup scripts idempotent (safe to run multiple times)
- The setup script path is relative to your project root
- Your setup script can live anywhere in your project (e.g., `scripts/`, `bin/`, root)

## Caching Dependencies

For faster startup with large dependency trees, you can cache to the workspace:

```bash
# Node.js - use workspace-local cache
npm config set cache /workspace/.npm-cache

# Python - use workspace-local virtualenv
python -m venv /workspace/.venv
source /workspace/.venv/bin/activate
pip install -r requirements.txt
```
