# This container is NOT for the product itself, but to use the Pi Coding Agent
# Build: at project root, `podman build --no-cache -t pi-agent:fengwen .`
# Clean: After rebuild, clean the dangling images with `podman image prune`

# add python
FROM docker.io/library/python:3.12-slim-bookworm AS python

# Use a slim LTS version of Node
FROM docker.io/library/node:24-bookworm-slim

# Copy Python3.12 into the node container
COPY --from=python /usr/local /usr/local

# 1. Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    git \
    ca-certificates \
    fd-find \
    ripgrep \
    && rm -rf /var/lib/apt/lists/*

# Install the agent globally using npm
# Doing this as root ensures it is placed in /usr/local/bin
RUN npm install -g --ignore-scripts @earendil-works/pi-coding-agent

# Create the workspace as root
RUN mkdir -p /workspace && chown node:node /workspace

# Install Python Dependencies
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/
RUN mkdir -p /tmp
COPY pyproject.toml /tmp/pyproject.toml
RUN uv pip install --system --no-cache-dir -r /tmp/pyproject.toml
RUN rm /tmp/pyproject.toml
RUN python -m playwright install-deps chromium && \
    python -m playwright install chromium && \
    mkdir -p /home/node/.cache && \
    cp -r /root/.cache/ms-playwright /home/node/.cache/ms-playwright && \
    chown -R node:node /home/node/.cache/ms-playwright

# Switch to the non-root user
USER node
WORKDIR /workspace

ENTRYPOINT ["pi"]
