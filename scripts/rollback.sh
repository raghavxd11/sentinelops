#!/bin/bash
# Put the last stable demo-app image back after a failed health check.
# Usage: rollback.sh <stable_image> [container_name] [host_port] [health_url]
#   e.g. rollback.sh 567190388316.dkr.ecr.us-east-1.amazonaws.com/sentinelops/demo-app:latest-stable
# Exit code: 0 = rolled back and healthy
#            1 = rolled back, but the stable image is unhealthy too
#            2 = nothing to roll back to (no stable image yet, e.g. the first deploy)

set -euo pipefail

STABLE_IMAGE="${1:?usage: rollback.sh <stable_image> [container_name] [host_port] [health_url]}"
NAME="${2:-demo-app}"
PORT="${3:-8000}"
HEALTH_URL="${4:-http://localhost:$PORT/health}"

# Folder this script is in, so deploy.sh and healthcheck.sh are found from anywhere.
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

echo "Rolling back '$NAME' to $STABLE_IMAGE"

# 1. Is there a stable image? Images in ECR are pulled; local ones must already exist.
if [[ "$STABLE_IMAGE" == *".dkr.ecr."* ]]; then
  # Docker's own error stays visible: "not found" = no stable image yet,
  # "no basic auth credentials" = the ECR login is missing.
  FOUND=$(docker pull -q "$STABLE_IMAGE" >/dev/null && echo yes || echo no)
else
  FOUND=$(docker image inspect "$STABLE_IMAGE" >/dev/null && echo yes || echo no)
fi

if [ "$FOUND" = "no" ]; then
  echo "ROLLBACK NOT POSSIBLE: stable image $STABLE_IMAGE is not available (see the error above)."
  echo "Usually this is the first deploy: no version has passed a health check yet,"
  echo "so there is nothing to go back to. The broken container '$NAME' is left running"
  echo "so you can inspect it: docker logs $NAME"
  exit 2
fi

# 2. Version and commit of the stable image, from the labels the pipeline adds at build time.
#    Without this, the container would show the commit of the broken build.
label() {
  docker image inspect -f "{{ index .Config.Labels \"$1\" }}" "$STABLE_IMAGE" 2>/dev/null || true
}
STABLE_VERSION="$(label org.opencontainers.image.version)"
STABLE_COMMIT="$(label org.opencontainers.image.revision)"

# 3. Redeploy it. BREAK_HEALTH=false: the rollback must never inherit the "break" demo flag.
APP_VERSION="${STABLE_VERSION:-stable}" \
GIT_COMMIT="${STABLE_COMMIT:-unknown}" \
BREAK_HEALTH=false \
  bash "$SCRIPT_DIR/deploy.sh" "$STABLE_IMAGE" "$NAME" "$PORT"

# 4. Check that the stable version is really healthy again.
if bash "$SCRIPT_DIR/healthcheck.sh" "$HEALTH_URL"; then
  echo "ROLLBACK OK: '$NAME' is running $STABLE_IMAGE (commit ${STABLE_COMMIT:-unknown}) and is healthy"
  exit 0
fi

echo "ROLLBACK FAILED: $STABLE_IMAGE was redeployed but is unhealthy too. Manual fix needed."
exit 1
