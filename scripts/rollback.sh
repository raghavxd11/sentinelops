#!/bin/bash
# Redeploy the last image that passed its health check, then verify it is healthy.
# Self-healing level 1: Jenkins runs this when a new version fails after deploy.
#
# Usage:   scripts/rollback.sh <production|staging>
#
# The rollback target is the stable tag in ECR (latest-stable for production,
# staging-stable for staging). Jenkins only moves that tag after a deploy passes
# its health check, so it always points at the last good version.
# Needs ECR_REPOSITORY_URL (set on EC2 from /etc/sentinelops.env).
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
# shellcheck source=scripts/common.sh
. "$SCRIPT_DIR/common.sh" "${1:-}"
STABLE_IMAGE="${ECR_REPOSITORY_URL:?ECR_REPOSITORY_URL is not set}:$STABLE_TAG"

echo "Rolling back $ENVIRONMENT to $STABLE_IMAGE"

# Always pull: a local copy of the tag may be older than the one in ECR.
ecr_login "$STABLE_IMAGE"
if ! docker pull "$STABLE_IMAGE"; then
  echo "ROLLBACK FAILED: no $STABLE_TAG image in the registry yet (no deploy has passed before)" >&2
  exit 1
fi

BREAK_HEALTH=false "$SCRIPT_DIR/deploy.sh" "$ENVIRONMENT" "$STABLE_IMAGE"

if ! "$SCRIPT_DIR/healthcheck.sh" "http://localhost:$PORT/health"; then
  echo "ROLLBACK FAILED: the stable image is not healthy either" >&2
  exit 1
fi
echo "Rollback complete: $ENVIRONMENT is healthy on $STABLE_TAG"
