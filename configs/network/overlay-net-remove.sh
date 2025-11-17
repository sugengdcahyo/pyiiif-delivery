#!/bin/bash

NETWORK_NAME="swarm-net"

# Cek apakah network ada
if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
  echo "Removing overlay network '$NETWORK_NAME'..."
  docker network rm "$NETWORK_NAME"
else
  echo "Overlay network '$NETWORK_NAME' does not exist."
fi

