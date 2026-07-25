#!/bin/sh
set -eu

mkdir -p /models /data/assets

# Named volumes are created as root. Changing the top-level model-cache owner is
# enough for a fresh volume; assets are recursively fixed because they are often
# a host bind mount created by root during deployment.
chown appuser:appuser /models
chown -R appuser:appuser /data/assets

exec gosu appuser "$@"
