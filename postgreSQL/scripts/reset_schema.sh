#!/usr/bin/env bash
set -euo pipefail

# WARNING:
# This deletes the public schema and then applies schema.sql again.
# Use this only in development.
#
# Run:
#   bash scripts/reset_schema.sh

bash scripts/drop_public_schema.sh
bash scripts/apply_schema.sh

echo "Database reset and schema reapplied successfully."
