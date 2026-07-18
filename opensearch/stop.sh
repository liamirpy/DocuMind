#!/usr/bin/env bash

set -Eeuo pipefail


SCRIPT_DIR="$(
  cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
  pwd
)"

cd "$SCRIPT_DIR"


if docker info >/dev/null 2>&1; then

  DOCKER=(docker)

else

  DOCKER=(sudo docker)

fi


echo "Stopping DocuMind OpenSearch..."


"${DOCKER[@]}" compose \
  down \
  --remove-orphans


echo

echo "OpenSearch stopped."

echo "Persistent data was preserved in:"

echo "$SCRIPT_DIR/data"