#!/bin/bash
# Pi Agent - Launch a containerized Pi coding agent
# Usage: ./run-pi.sh

# Paths
PROJ_PATH=$(realpath "$(pwd)")

# Resolve the config symlink at $HOME
PI_CONFIG_PATH=$(dirname "$(readlink -f "$HOME/.pi/agent")")

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
    -v "/workspace/.venv" \
    -e PI_CODING_AGENT_DIR="/home/node/.pi/agent" \
    pi-agent:fengwen
