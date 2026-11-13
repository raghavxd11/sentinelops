#!/bin/bash
# Run a demo-app image as the production or staging container, replacing the old one.
#
# Usage:   scripts/deploy.sh <production|staging> <image>
# Example: scripts/deploy.sh staging 123456789012.dkr.ecr.ap-south-1.amazonaws.com/sentinelops/demo-app:3f2a9c1
#
# Optional environment variables:
#   BREAK_HEALTH=true    start the app with a failing /health (rollback demo)
#   DEMO_APP_LOG_GROUP   send container logs to this CloudWatch log group (set on EC2)
#
# The container gets:
#   --restart unless-stopped   Docker restarts it if it crashes (self-healing level 2)
#   --label autoheal=true      the autoheal container restarts it if its HEALTHCHECK fails
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/common.sh
. "$SCRIPT_DIR/common.sh" "${1:-}"
IMAGE=${2:?usage: deploy.sh <production|staging> <image>}

# Pull from ECR unless the image was just built on this machine.
if ! docker image inspect "$IMAGE" > /dev/null 2>&1; then
  ecr_login "$IMAGE"
  docker pull "$IMAGE"
fi

# Version and commit come from labels that Jenkins adds at build time, so a
# rolled-back image still shows the commit it was really built from.
label() {
  docker image inspect --format "{{ with index .Config.Labels \"$1\" }}{{ . }}{{ end }}" "$IMAGE"
}
APP_VERSION=$(label org.opencontainers.image.version)
GIT_COMMIT=$(label org.opencontainers.image.revision)

# The autoheal container watches Docker health status and restarts containers
# labelled autoheal=true that become unhealthy (a hung app, not just a crashed one).
if [ -z "$(docker ps --quiet --filter name=^autoheal$)" ]; then
  echo "Starting the autoheal watcher"
  docker rm --force autoheal > /dev/null 2>&1 || true
  docker run --detach --name autoheal --restart unless-stopped \
    --volume /var/run/docker.sock:/var/run/docker.sock \
    willfarrell/autoheal:1.2.0 > /dev/null
fi

# Container logs go to CloudWatch on EC2, and to the default json-file driver elsewhere.
log_options=()
if [ -n "${DEMO_APP_LOG_GROUP:-}" ]; then
  log_options=(
    --log-driver awslogs
    --log-opt "awslogs-region=${AWS_REGION:?AWS_REGION is not set}"
    --log-opt "awslogs-group=$DEMO_APP_LOG_GROUP"
    --log-opt "awslogs-stream=$CONTAINER"
    --log-opt mode=non-blocking
  )
fi

echo "Deploying $IMAGE to $ENVIRONMENT ($CONTAINER on port $PORT)"
docker rm --force "$CONTAINER" > /dev/null 2>&1 || true
docker run --detach \
  --name "$CONTAINER" \
  --restart unless-stopped \
  --publish "$PORT:8000" \
  --label autoheal=true \
  --label "sentinelops.environment=$ENVIRONMENT" \
  --env "APP_VERSION=${APP_VERSION:-unknown}" \
  --env "GIT_COMMIT=${GIT_COMMIT:-unknown}" \
  --env "BREAK_HEALTH=${BREAK_HEALTH:-false}" \
  "${log_options[@]}" \
  "$IMAGE" > /dev/null

# Remove image layers no longer used by any tag, so old builds do not fill the disk.
docker image prune --force > /dev/null

echo "Started $CONTAINER (version ${APP_VERSION:-unknown}, commit ${GIT_COMMIT:-unknown})"
