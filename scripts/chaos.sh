#!/bin/bash
# Break things on purpose, to show the self-healing during a live demo.
# Run on the EC2 instance (ssh ec2-user@<ip>, then from a clone of the repository).
#
#   scripts/chaos.sh crash         [production|staging]  kill the app process -> Docker restarts the container
#   scripts/chaos.sh hang          [production|staging]  freeze the app -> HEALTHCHECK fails -> autoheal restarts it
#   scripts/chaos.sh cpu           [seconds]             load every CPU core (default 600 s) -> high-CPU alarm email
#   scripts/chaos.sh broken-deploy [production|staging]  redeploy with a failing /health -> health check -> rollback
#
# The environment defaults to production.
set -euo pipefail

SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)
ACTION=${1:-}

# Killing or freezing a container's processes from the host needs root.
SUDO=""
if [ "$(id -u)" -ne 0 ]; then
  SUDO=sudo
fi

load_environment() {
  # shellcheck source=scripts/common.sh
  . "$SCRIPT_DIR/common.sh" "${1:-production}"
  if ! docker inspect "$CONTAINER" > /dev/null 2>&1; then
    echo "Container $CONTAINER does not exist. Deploy it first." >&2
    exit 1
  fi
}

started_at() {
  docker inspect --format '{{ .State.StartedAt }}' "$CONTAINER"
}

# Wait until the container has been restarted (its start time changed) and
# Docker reports it healthy again, printing the state every 5 seconds.
wait_for_recovery() {
  local started_before=$1 timeout=$2 waited=0 state
  while [ "$waited" -le "$timeout" ]; do
    state=$(docker inspect --format '{{ .State.Status }} / {{ if .State.Health }}{{ .State.Health.Status }}{{ else }}no healthcheck{{ end }}' "$CONTAINER")
    echo "  ${waited}s: $state"
    if [ "$(started_at)" != "$started_before" ] && [ "$state" = "running / healthy" ]; then
      echo "Recovered after about ${waited}s"
      return 0
    fi
    sleep 5
    waited=$((waited + 5))
  done
  echo "Not recovered after ${timeout}s" >&2
  return 1
}

case "$ACTION" in
  crash)
    load_environment "${2:-}"
    started=$(started_at)
    pid=$(docker inspect --format '{{ .State.Pid }}' "$CONTAINER")
    echo "Killing the main process of $CONTAINER (host PID $pid) with SIGKILL, like a crash"
    $SUDO kill -KILL "$pid"
    wait_for_recovery "$started" 60
    echo "Docker restarted $CONTAINER (restart policy). Restart count: $(docker inspect --format '{{ .RestartCount }}' "$CONTAINER")"
    ;;

  hang)
    load_environment "${2:-}"
    started=$(started_at)
    # SIGSTOP freezes every process of the container without stopping it.
    # Docker still thinks it is running, but /health no longer answers, so the
    # HEALTHCHECK marks it unhealthy and the autoheal container restarts it.
    pids=$(docker top "$CONTAINER" -o pid | tail -n +2)
    echo "Freezing all processes of $CONTAINER (host PIDs: $(echo "$pids" | tr '\n' ' '))"
    # shellcheck disable=SC2086  # one argument per PID
    $SUDO kill -STOP $pids
    wait_for_recovery "$started" 120
    echo "autoheal restarted the hung container"
    ;;

  cpu)
    seconds=${2:-600}
    cores=$(nproc)
    echo "Loading $cores CPU cores for $seconds s. The high-CPU alarm needs 2 minutes above the threshold."
    echo "Press Ctrl+C to stop early."
    trap 'kill $(jobs -p) 2> /dev/null || true' INT TERM
    for _ in $(seq "$cores"); do
      timeout "$seconds" yes > /dev/null &
    done
    wait || true
    echo "CPU load finished"
    ;;

  broken-deploy)
    load_environment "${2:-}"
    image=$(docker inspect --format '{{ .Config.Image }}' "$CONTAINER")
    echo "Redeploying $image to $ENVIRONMENT with BREAK_HEALTH=true"
    BREAK_HEALTH=true "$SCRIPT_DIR/deploy.sh" "$ENVIRONMENT" "$image"
    if "$SCRIPT_DIR/healthcheck.sh" "http://localhost:$PORT/health"; then
      echo "Unexpected: the broken version passed the health check" >&2
      exit 1
    fi
    echo "Health check failed as expected. Rolling back."
    "$SCRIPT_DIR/rollback.sh" "$ENVIRONMENT"
    ;;

  *)
    sed -n '2,10p' "$0" >&2
    exit 2
    ;;
esac
