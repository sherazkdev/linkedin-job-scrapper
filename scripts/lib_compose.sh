#!/usr/bin/env bash
# Source on VPS: . scripts/lib_compose.sh
set -euo pipefail
COMPOSE_FILES=(
  -f compose.yaml
  -f compose.contabo-vps.yaml
  -f compose.contabo-pilot-api.yaml
  -f compose.contabo-wave1.yaml
)
COMPOSE_PROJECT=linkedin-scraper
COMPOSE=(docker compose "${COMPOSE_FILES[@]}" -p "${COMPOSE_PROJECT}")