#!/bin/bash
# Stop on the first failure so a broken build never pushes a stale image.
set -euo pipefail

# Use the repo root as build context, regardless of where this is run from.
cd "$(dirname "${BASH_SOURCE[0]}")/.."

IMAGE="avocadomoon/event-scraper:latest"

docker build -t "$IMAGE" .
docker push "$IMAGE"
