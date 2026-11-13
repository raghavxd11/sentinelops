#!/bin/bash
# Send the result of a pipeline run to the dashboard API (POST /api/deployments).
#
# Usage: scripts/report.sh   (all input comes from environment variables)
#
# Required:
#   DASHBOARD_URL     e.g. http://localhost:5000
#   API_TOKEN         must match API_TOKEN of the dashboard (Jenkins credential)
#   STATUS            SUCCESS | FAILED | ROLLED_BACK | IN_PROGRESS
#   GIT_COMMIT        full commit hash
# Optional:
#   SERVICE_NAME (default demo-app), COMMIT_AUTHOR, COMMIT_MESSAGE, BRANCH_NAME,
#   BUILD_NUMBER, IMAGE_TAG, FAILED_STAGE, COMMITTED_AT (ISO 8601),
#   BUILD_START (unix time the build started; used to compute the duration)
#
# The JSON body is built with jq, so quotes or newlines in a commit message
# cannot break the request.
set -euo pipefail

: "${DASHBOARD_URL:?DASHBOARD_URL is not set}"
: "${API_TOKEN:?API_TOKEN is not set}"
: "${STATUS:?STATUS is not set}"
: "${GIT_COMMIT:?GIT_COMMIT is not set}"

duration=""
if [ -n "${BUILD_START:-}" ]; then
  duration=$(($(date +%s) - BUILD_START))
fi

# Empty optional values are sent as null; numbers are sent as numbers.
payload=$(jq --null-input \
  --arg service "${SERVICE_NAME:-demo-app}" \
  --arg commit_hash "$GIT_COMMIT" \
  --arg commit_author "${COMMIT_AUTHOR:-}" \
  --arg commit_message "${COMMIT_MESSAGE:-}" \
  --arg branch "${BRANCH_NAME:-}" \
  --arg build_number "${BUILD_NUMBER:-}" \
  --arg image_tag "${IMAGE_TAG:-}" \
  --arg status "$STATUS" \
  --arg failed_stage "${FAILED_STAGE:-}" \
  --arg duration_seconds "$duration" \
  --arg committed_at "${COMMITTED_AT:-}" \
  'def opt: if . == "" then null else . end;
   {
     service: $service,
     commit_hash: $commit_hash,
     commit_author: $commit_author,
     commit_message: $commit_message,
     branch: $branch,
     build_number: ($build_number | opt | if . == null then null else tonumber end),
     image_tag: ($image_tag | opt),
     status: $status,
     failed_stage: ($failed_stage | opt),
     duration_seconds: ($duration_seconds | opt | if . == null then null else tonumber end),
     committed_at: ($committed_at | opt)
   }')

echo "Reporting $STATUS for ${GIT_COMMIT:0:7} to $DASHBOARD_URL"

# The token header is passed through a file descriptor instead of the command
# line, so it does not show up in the process list.
response=$(curl --silent --show-error --max-time 10 --retry 3 --retry-delay 2 \
  --write-out '\n%{http_code}' \
  --request POST "$DASHBOARD_URL/api/deployments" \
  --header "Content-Type: application/json" \
  --header @<(printf 'X-API-Token: %s\n' "$API_TOKEN") \
  --data "$payload")

code=${response##*$'\n'}
body=${response%$'\n'*}
if [ "$code" != "200" ] && [ "$code" != "201" ]; then
  echo "Dashboard answered HTTP $code: $body" >&2
  exit 1
fi
echo "Recorded: $body"
