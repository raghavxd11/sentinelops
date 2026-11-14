#!/bin/bash
# Replace the running demo-app container with a new image.
# Usage: deploy.sh <image> [container_name] [host_port]
# Optional env vars: APP_VERSION, GIT_COMMIT, BREAK_HEALTH

set -euo pipefail

IMAGE="${1:?usage: deploy.sh <image> [container_name] [host_port]}"
NAME="${2:-demo-app}"
PORT="${3:-8000}"

echo "Deploying $IMAGE as container '$NAME' on port $PORT"

# Images in ECR are downloaded first; local images are used as they are.
if [[ "$IMAGE" == *".dkr.ecr."* ]]; then
  docker pull "$IMAGE"
fi

# Remove the old container. "|| true" = don't fail if there isn't one.
docker rm -f "$NAME" >/dev/null 2>&1 || true

docker run -d \
  --name "$NAME" \
  --restart unless-stopped \
  --label autoheal=true \
  -p "$PORT:8000" \
  -e APP_VERSION="${APP_VERSION:-dev}" \
  -e GIT_COMMIT="${GIT_COMMIT:-unknown}" \
  -e BREAK_HEALTH="${BREAK_HEALTH:-false}" \
  "$IMAGE"

echo "Started '$NAME' from $IMAGE"