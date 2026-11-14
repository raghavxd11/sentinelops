#!/bin/bash
# Check that a URL answers HTTP 200, retrying a few times.
# Usage: healthcheck.sh <url> [attempts] [delay_seconds]
# Exit code: 0 = healthy, 1 = unhealthy

set -euo pipefail

URL="${1:?usage: healthcheck.sh <url> [attempts] [delay_seconds]}"
ATTEMPTS="${2:-5}"
DELAY="${3:-5}"

for i in $(seq 1 "$ATTEMPTS"); do
  STATUS=$(curl -s -o /dev/null -w "%{http_code}" --max-time 3 "$URL" || true)

  if [ "$STATUS" = "200" ]; then
    echo "Health check passed: $URL returned 200 (attempt $i/$ATTEMPTS)"
    exit 0
  fi

  echo "Attempt $i/$ATTEMPTS: $URL returned $STATUS"
  if [ "$i" -lt "$ATTEMPTS" ]; then
    sleep "$DELAY"
  fi
done

echo "Health check FAILED: $URL did not return 200 after $ATTEMPTS attempts"
exit 1