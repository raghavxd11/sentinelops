#!/bin/bash
# Check that a URL answers with HTTP 2xx, retrying with exponential backoff.
#
# Usage:   scripts/healthcheck.sh <url> [attempts]
# Example: scripts/healthcheck.sh http://localhost:8000/health 5
#
# Waits 2, 4, 8, 16 ... seconds between attempts (30 s in total for 5 attempts),
# which gives a freshly started container time to boot.
# Exit code 0 = healthy, 1 = still failing after the last attempt.
set -euo pipefail

URL=${1:?usage: healthcheck.sh <url> [attempts]}
ATTEMPTS=${2:-5}

delay=2
for attempt in $(seq 1 "$ATTEMPTS"); do
  if body=$(curl --fail --silent --show-error --max-time 5 "$URL" 2>&1); then
    echo "Healthy on attempt $attempt/$ATTEMPTS: $body"
    exit 0
  fi
  echo "Attempt $attempt/$ATTEMPTS failed: $body"
  if [ "$attempt" -lt "$ATTEMPTS" ]; then
    echo "Retrying in $delay s"
    sleep "$delay"
    delay=$((delay * 2))
  fi
done

echo "UNHEALTHY: $URL failed $ATTEMPTS health checks" >&2
exit 1
