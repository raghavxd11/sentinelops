#!/bin/bash
# Send one deployment result to the dashboard: POST /api/deployments.
# Usage: report.sh <status> [failed_stage]
#   status        SUCCESS | FAILED | ROLLED_BACK
#   failed_stage  Checkout | Test | Build | Scan | Push | Deploy | Health check
#
# Everything else comes from environment variables (Jenkins sets them):
#   API_TOKEN          required, sent in the X-API-Token header
#   DASHBOARD_URL      default http://localhost:5000
#   SERVICE_NAME       default demo-app (must exist on the dashboard's Services page)
#   COMMIT_HASH  COMMIT_AUTHOR  COMMIT_MESSAGE  COMMITTED_AT (ISO 8601)
#   BRANCH  BUILD_NUMBER  IMAGE_TAG  DURATION_SECONDS
#
# A report is only a record. It must NEVER fail the pipeline, so every problem
# prints a WARNING and the script still exits 0. (No "set -e" on purpose.)

set -uo pipefail

STATUS="${1:-}"
FAILED_STAGE="${2:-}"
DASHBOARD_URL="${DASHBOARD_URL:-http://localhost:5000}"

warn() {
  echo "WARNING: deployment not reported to the dashboard: $1"
  exit 0
}

[ -n "$STATUS" ] || warn "usage: report.sh <status> [failed_stage]"
[ -n "${API_TOKEN:-}" ] || warn "API_TOKEN is not set"
command -v jq >/dev/null || warn "jq is not installed"

# Build the JSON with jq, so quotes or newlines in a commit message can't break it.
# Numbers that are empty become null; an empty failed_stage / committed_at becomes null.
PAYLOAD=$(jq -n \
  --arg service "${SERVICE_NAME:-demo-app}" \
  --arg commit_hash "${COMMIT_HASH:-unknown}" \
  --arg commit_author "${COMMIT_AUTHOR:-}" \
  --arg commit_message "${COMMIT_MESSAGE:-}" \
  --arg committed_at "${COMMITTED_AT:-}" \
  --arg branch "${BRANCH:-}" \
  --arg build_number "${BUILD_NUMBER:-}" \
  --arg image_tag "${IMAGE_TAG:-}" \
  --arg status "$STATUS" \
  --arg failed_stage "$FAILED_STAGE" \
  --arg duration "${DURATION_SECONDS:-}" \
  '{
    service: $service,
    commit_hash: $commit_hash,
    commit_author: $commit_author,
    commit_message: $commit_message,
    committed_at: (if $committed_at == "" then null else $committed_at end),
    branch: $branch,
    build_number: ($build_number | tonumber? // null),
    image_tag: $image_tag,
    status: $status,
    failed_stage: (if $failed_stage == "" then null else $failed_stage end),
    duration_seconds: ($duration | tonumber? // null)
  }') || warn "could not build the JSON payload"

echo "Reporting to $DASHBOARD_URL/api/deployments:"
echo "$PAYLOAD"

# The token goes in a private temp file (mode 600) instead of on the curl
# command line, where any user on the server could see it with "ps".
HEADER_FILE=$(mktemp) || warn "could not create a temp file"
trap 'rm -f "$HEADER_FILE"' EXIT
printf 'X-API-Token: %s\n' "$API_TOKEN" > "$HEADER_FILE"

# -w adds the HTTP status code as the last line of the output.
RESPONSE=$(curl -sS --max-time 10 -w '\n%{http_code}' \
  -X POST "$DASHBOARD_URL/api/deployments" \
  -H "Content-Type: application/json" \
  -H @"$HEADER_FILE" \
  --data "$PAYLOAD") || warn "could not reach $DASHBOARD_URL"

CODE=$(echo "$RESPONSE" | tail -n 1)
BODY=$(echo "$RESPONSE" | sed '$d')

if [ "$CODE" = "200" ] || [ "$CODE" = "201" ]; then
  echo "Reported (HTTP $CODE): $BODY"
else
  warn "dashboard answered HTTP $CODE: $BODY"
fi
