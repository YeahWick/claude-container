# Example: Adding npm

This example shows how to add npm to the tool server.

## Files to modify

1. **cli/npm** - Symlink to cli-wrapper
2. **plugins/cli/tool-caller.py** - Register the tool
3. **plugins/cli/Containerfile** - Install the binary
4. **plugins/cli/setup.d/npm.sh** - (Optional) Setup script
5. **plugins/cli/restricted/npm.sh** - (Optional) Restriction wrapper

## Quick setup

```bash
# From repo root

# 1. Create wrapper symlink
cd cli && ln -s cli-wrapper npm && cd ..

# 2. Apply the patches (or edit manually)
# See tool-caller.patch and Containerfile.patch

# 3. Copy setup script (optional)
cp examples/add-npm/setup.d/npm.sh plugins/cli/setup.d/

# 4. Rebuild
docker compose build cli-server
./scripts/install.sh
```

## Files included

- `setup.d/npm.sh` - Configures npm cache directory
- `restricted/npm.sh` - Example: blocks `npm publish`
