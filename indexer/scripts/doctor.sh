#!/usr/bin/env sh
set -eu

printf '%s\n' '== Docker Compose services =='
docker compose ps -a

printf '\n%s\n' '== init-permissions logs =='
docker compose logs --no-color init-permissions || true

printf '\n%s\n' '== API readiness =='
curl --fail --show-error --silent http://localhost:"${API_PORT:-8000}"/health/ready
printf '\n'
