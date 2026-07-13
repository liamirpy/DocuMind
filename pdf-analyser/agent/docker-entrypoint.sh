#!/bin/sh
set -eu

mkdir -p /data/outputs

TARGET_UID="${HOST_UID:-10002}"
TARGET_GID="${HOST_GID:-10002}"

case "$TARGET_UID:$TARGET_GID" in
  *[!0-9:]*|:*|*:) 
    echo "HOST_UID and HOST_GID must be numeric; using image defaults." >&2
    TARGET_UID=10002
    TARGET_GID=10002
    ;;
esac

CURRENT_UID="$(id -u appuser)"
CURRENT_GID="$(id -g appuser)"

if [ "$TARGET_GID" != "$CURRENT_GID" ]; then
  groupmod -o -g "$TARGET_GID" appuser
fi

if [ "$TARGET_UID" != "$CURRENT_UID" ]; then
  usermod -o -u "$TARGET_UID" appuser
fi

chown appuser:appuser /data/outputs

exec gosu appuser "$@"
