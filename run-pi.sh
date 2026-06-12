#!/bin/bash
# Pi Agent - Launch a containerized Pi coding agent
# Usage: ./run-pi.sh

# 1. Paths
# Use realpath to handle relative paths and symlinks correctly
PROJ_PATH=$(realpath "$(pwd)")

# Load PI_CONFIG_PATH (and any other vars) from .env next to this script
ENV_FILE="$PROJ_PATH/.env"

if [ -f "$ENV_FILE" ]; then
    set -a
    source "$ENV_FILE"
    set +a
else
    echo "Error: .env file not found at $ENV_FILE" >&2
    exit 1
fi

if [ -z "$PI_CONFIG_PATH" ]; then
    echo "Error: PI_CONFIG_PATH is not set in $ENV_FILE" >&2
    exit 1
fi

# Ensure the config path exists on the host
mkdir -p "$PI_CONFIG_PATH"

echo "--- Pi Agent Persistent Session ---"
echo "Project: $PROJ_PATH"
echo "Config:  $PI_CONFIG_PATH"
echo "-----------------------------------"

CONTAINER_NAME="pi-agent-fengwen"

podman run -it --rm \
    --name "$CONTAINER_NAME" \
    --add-host=host.containers.internal:host-gateway \
    --userns="keep-id:uid=1000,gid=1000" \
    -v "$PROJ_PATH:/workspace:Z" \
    -v "$PI_CONFIG_PATH:/home/node/.pi:Z" \
    -e PI_CODING_AGENT_DIR="/home/node/.pi/agent" \
    pi-agent:fengwen
