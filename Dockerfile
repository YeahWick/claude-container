FROM ubuntu:24.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system dependencies
RUN apt-get update && apt-get install -y \
    curl \
    git \
    ca-certificates \
    gnupg \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (LTS version)
RUN curl -fsSL https://deb.nodesource.com/setup_22.x | bash - \
    && apt-get install -y nodejs \
    && rm -rf /var/lib/apt/lists/*

# Install Claude Code globally
RUN npm install -g @anthropic-ai/claude-code

# Create a non-root user for running Claude Code
RUN useradd -m -s /bin/bash claude
USER claude
WORKDIR /home/claude

# Create workspace directory for mounting repos
RUN mkdir -p /home/claude/workspace

# Copy startup script
COPY --chown=claude:claude start.sh /home/claude/start.sh
RUN chmod +x /home/claude/start.sh

# Set the workspace as the default directory
WORKDIR /home/claude/workspace

# Default command runs the startup script
ENTRYPOINT ["/home/claude/start.sh"]
