# Claude Container v2 - Plugin Socket System

A plugin-based architecture for the Claude Container where tools communicate via Unix domain sockets. **Add new tools without restarting the container.**

## Key Features

- **Hot-pluggable tools** - Add new CLI tools while Claude is running
- **Independent plugins** - Each tool enforces its own rules
- **Host volumes** - Edit wrappers and configs without rebuilding
- **Secure by default** - Credentials never exposed to Claude container

## Key Changes from v1

| Aspect | v1 | v2 |
|--------|----|----|
| Architecture | Monolithic command-agent | Independent tool plugins |
| Sockets | Single shared socket | One socket per tool |
| Configuration | Central .env file | Per-plugin YAML configs |
| Deployment | All-or-nothing | Independent plugin updates |
| **Hot-plug tools** | ✗ Requires restart | ✓ Add anytime |
| CLI location | Baked into image | Host volume mounted |

## Quick Start

```bash
# First-time setup
./scripts/install.sh

# Start the system
./scripts/run.sh start

# Check status
./scripts/run.sh status
```

## Architecture

```
HOST (~/.claude-container/)          CONTAINERS
────────────────────────────         ──────────

cli/                          ────►  Claude: /home/claude/bin
├── plugin-client                    (read-only, in PATH)
├── git
└── npm  ← add new wrappers!

sockets/                      ────►  Claude: /run/plugins (ro)
├── git.sock                         Plugins: /run/plugins (rw)
└── npm.sock  ← plugins create these

config/                       ────►  Plugins: /etc/plugins
├── git.yaml
└── npm.yaml  ← add new configs!
```

## Adding a New Tool (No Restart!)

```bash
# 1. Create wrapper script
cat > ~/.claude-container/cli/npm << 'EOF'
#!/bin/sh
SOCKET="/run/plugins/npm.sock"
if [ ! -S "$SOCKET" ]; then
    echo "error: npm plugin not available" >&2
    exit 127
fi
exec /home/claude/bin/plugin-client "$SOCKET" npm "$@"
EOF
chmod +x ~/.claude-container/cli/npm

# 2. Add config
cat > ~/.claude-container/config/npm.yaml << 'EOF'
plugin: npm
rules:
  blocked_commands: [publish, unpublish]
EOF

# 3. Start plugin container
docker compose up -d npm-plugin

# 4. Use immediately in Claude!
$ npm install lodash  # Works!
```

## Documentation

- [SPEC.md](./SPEC.md) - Full technical specification

## Status

**MVP** - Implementing core functionality

- [ ] Base plugin library
- [ ] Git plugin
- [ ] Plugin client (socket wrapper)
- [ ] Docker compose setup
- [ ] Install script
