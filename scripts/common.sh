#!/bin/bash
# Shared settings for the deploy scripts. Not run directly; the other scripts load it with:
#   . "$SCRIPT_DIR/common.sh" <production|staging>
#
# Sets, for the given environment:
#   ENVIRONMENT  production | staging
#   CONTAINER    name of the demo-app container
#   PORT         host port it listens on
#   STABLE_TAG   ECR tag of the last image that passed its health check (the rollback target)
# Keep these in sync with the deploy settings at the top of the Jenkinsfile.

# shellcheck disable=SC2034  # the variables are used by the scripts that source this file

ENVIRONMENT=${1:-}
case "$ENVIRONMENT" in
  production)
    CONTAINER=demo-app-prod
    PORT=8000
    STABLE_TAG=latest-stable
    ;;
  staging)
    CONTAINER=demo-app-staging
    PORT=8001
    STABLE_TAG=staging-stable
    ;;
  *)
    echo "environment must be 'production' or 'staging' (got '$ENVIRONMENT')" >&2
    exit 2
    ;;
esac

# Log Docker in to ECR when the image comes from ECR (registry = part before the first "/").
# Uses the EC2 instance role, so no access keys are needed.
ecr_login() {
  local registry=${1%%/*}
  case "$registry" in
    *.dkr.ecr.*.amazonaws.com)
      aws ecr get-login-password --region "${AWS_REGION:?AWS_REGION is not set}" \
        | docker login --username AWS --password-stdin "$registry" > /dev/null
      ;;
  esac
}
