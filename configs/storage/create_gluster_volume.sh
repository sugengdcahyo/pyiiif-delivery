#!/bin/bash

#Define the node variable
NODE1=172.16.16.61
NODE2=172.16.16.60
NODE3=172.16.16.62
VOLUME_NAME=ozone-vol
BRICK_PATH="/gluster/brick"


echo "[INFO] Probe antar peer..."
sudo gluster peer probe $NODE2
sudo gluster peer probe $NODE3

sleep 3
echo "[INFO] Membuat volume replica 3..."
sudo gluster volume create $VOLUME_NAME replica 3 \
  $NODE1:$BRICK_PATH \
  $NODE2:$BRICK_PATH \
  $NODE3:$BRICK_PATH

echo "[INFO] Start volume..."
sudo gluster volume start $VOLUME_NAME

echo "[INFO] Volume detail:"
sudo gluster volume info $VOLUME_NAME

