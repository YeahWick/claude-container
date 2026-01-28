# Project Setup Hook

The project setup hook allows you to automatically install project dependencies when starting Claude Container.

## Usage

1. Create a `.claude-container/` directory in your project root
2. Add a `setup.sh` script with your dependency installation commands
3. Run `claude-container` - your setup script runs automatically before Claude starts

## Example

```bash
# In your project directory
mkdir -p .claude-container
cp /path/to/examples/project-setup/setup.sh .claude-container/setup.sh
# Edit as needed for your project
```

## How It Works

When you run `scripts/run.sh` from your project directory:

1. Your project is mounted to `/workspace` in the containers
2. The tool-server starts and runs tool setup scripts (git config, etc.)
3. **Your project's `.claude-container/setup.sh` runs** (if it exists)
4. Claude starts with full access to your project and installed dependencies

## Tips

- The setup script runs in the **tool-server** container, which has build tools installed
- Use `set -e` to fail fast if any command fails
- Keep setup scripts idempotent (safe to run multiple times)
- Dependencies are installed fresh each container start (consider caching strategies for large projects)

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
