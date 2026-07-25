#!/bin/sh
set -eu

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

# These two locations are managed by the image/Compose configuration. Do not
# chown arbitrary allow-listed paths such as /host, because /host may represent
# the host filesystem root.
for managed_directory in /data/outputs /data/custom-output; do
  if [ -e "$managed_directory" ]; then
    chown appuser:appuser "$managed_directory"
  else
    mkdir -p "$managed_directory"
    chown appuser:appuser "$managed_directory"
  fi
done

exec gosu appuser "$@"
