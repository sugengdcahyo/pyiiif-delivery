#!/bin/bash

NETWORK_NAME="swarm-net"
SUBNET="10.10.0.0/16"
GATEWAY="10.10.0.1"

# Cek apakah network sudah ada
if docker network inspect "$NETWORK_NAME" >/dev/null 2>&1; then
  echo "Overlay network '$NETWORK_NAME' already exists."
else
  echo "Creating overlay network '$NETWORK_NAME'..."
  docker network create \
    --driver=overlay \
    --attachable \
    --subnet="$SUBNET" \
    --gateway="$GATEWAY" \
    "$NETWORK_NAME"
fi

