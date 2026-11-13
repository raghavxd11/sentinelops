// SentinelOps CI/CD pipeline for demo-app.
//
//   Checkout -> Setup -> [Lint | Unit tests | Dependency scan] -> Build -> Image scan -> Push
//   -> (main only: Approval) -> Deploy -> Health check -> latest-stable tag, or automatic rollback
//   -> report to the dashboard + email via SNS
//
// Branches: main deploys to production (port 8000) after manual approval,
// dev deploys to staging (port 8001). Other branches and pull requests run the
// checks, build and image scan, but are not pushed or deployed.
//
// Runs on the Jenkins built-in node of the EC2 instance. AWS access comes from the
// instance role. AWS_REGION, ECR_REPOSITORY_URL, SNS_TOPIC_ARN, DEMO_APP_LOG_GROUP and
// DASHBOARD_URL come from /etc/sentinelops.env, written by Terraform (user_data.sh).
// The only Jenkins credential is the dashboard API token: 'sentinelops-api-token'.

// Branch -> where it deploys. Keep in sync with scripts/common.sh.
def deployTargets() {
    return [
        main: [environment: 'production', port: '8000', stableTag: 'latest-stable'],
        dev : [environment: 'staging',    port: '8001', stableTag: 'staging-stable'],
    ]
}

// Put the last good image back, then fail the build. If rollback.sh itself
// fails, the sh step throws first and the run is reported as FAILED instead.
def rollbackAndFail(String reason) {
    echo "${reason}. Rolling back ${env.DEPLOY_ENV} to ${env.STABLE_TAG}."
    sh 'scripts/rollback.sh "$DEPLOY_ENV"'
    env.DEPLOY_STATUS = 'ROLLED_BACK'
    error("${reason}. Rolled back to ${env.STABLE_TAG}.")
}

// POST the result to the dashboard. Never fails the build.
def reportToDashboard(String status) {
    def failedStage = (status == 'SUCCESS') ? '' : (env.CURRENT_STAGE ?: '')
    withCredentials([string(credentialsId: 'sentinelops-api-token', variable: 'API_TOKEN')]) {
        withEnv(["STATUS=${status}", "FAILED_STAGE=${failedStage}", "IMAGE_TAG=${env.SHORT_SHA ?: ''}"]) {
            if (sh(script: 'scripts/report.sh', returnStatus: true) != 0) {
                echo 'WARNING: could not report this run to the dashboard'
            }
        }
    }
}

// Email through the SNS topic (the same topic the CloudWatch alarms use). Never fails the build.
def sendNotification(String status) {
    def subject = "SentinelOps ${status}: ${env.JOB_NAME} #${env.BUILD_NUMBER}"
    if (subject.length() > 100) {   // SNS limit
        subject = subject.substring(0, 100)
    }
    withEnv(["NOTIFY_STATUS=${status}", "NOTIFY_SUBJECT=${subject}"]) {
        // Values are passed as environment variables, never pasted into the
        // script text, so a commit message cannot inject shell commands.
        def rc = sh(returnStatus: true, script: '''
            message=$(printf 'Status: %s\\nBranch: %s\\nCommit: %s by %s\\n%s\\n\\nFailed stage: %s\\nBuild: %s\\n' \
              "$NOTIFY_STATUS" "$BRANCH_NAME" "${SHORT_SHA:-?}" "${COMMIT_AUTHOR:-?}" "${COMMIT_MESSAGE:-}" \
              "${CURRENT_STAGE:-none}" "$BUILD_URL")
            aws sns publish --region "$AWS_REGION" --topic-arn "$SNS_TOPIC_ARN" \
              --subject "$NOTIFY_SUBJECT" --message "$message" > /dev/null
        ''')
        if (rc != 0) {
            echo 'WARNING: could not send the SNS notification'
        }
    }
}

pipeline {
    agent any

    options {
        buildDiscarder(logRotator(numToKeepStr: '20', artifactNumToKeepStr: '10'))
        timestamps()
        timeout(time: 60, unit: 'MINUTES')
        disableConcurrentBuilds()
        skipDefaultCheckout()
    }

    parameters {
        booleanParam(name: 'BREAK_HEALTH', defaultValue: false,
            description: 'Demo: start the new version with a failing /health, so the pipeline rolls back.')
        choice(name: 'DOCKERFILE', choices: ['Dockerfile', 'Dockerfile.vulnerable'],
            description: 'Demo: build demo-app/Dockerfile.vulnerable to show Trivy blocking an image.')
    }

    environment {
        SERVICE_NAME = 'demo-app'
        PIP_DISABLE_PIP_VERSION_CHECK = '1'
    }

    stages {
        stage('Checkout') {
            steps {
                script { env.CURRENT_STAGE = 'Checkout' }
                checkout scm
                script {
                    env.BUILD_START = sh(script: 'date +%s', returnStdout: true).trim()
                    env.GIT_COMMIT = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                    env.SHORT_SHA = env.GIT_COMMIT.substring(0, 7)
                    env.COMMIT_AUTHOR = sh(script: 'git log -1 --format=%an', returnStdout: true).trim()
                    env.COMMIT_MESSAGE = sh(script: 'git log -1 --format=%s', returnStdout: true).trim()
                    env.COMMITTED_AT = sh(script: 'git log -1 --format=%cI', returnStdout: true).trim()
                    env.APP_VERSION = sh(script: 'git describe --tags --always', returnStdout: true).trim()
                    env.IMAGE = "${env.ECR_REPOSITORY_URL}:${env.SHORT_SHA}"

                    def target = deployTargets()[env.BRANCH_NAME]
                    if (target) {
                        env.DEPLOY_ENV = target.environment
                        env.APP_PORT = target.port
                        env.STABLE_TAG = target.stableTag
                    }
                    echo "Commit ${env.SHORT_SHA} by ${env.COMMIT_AUTHOR}: ${env.COMMIT_MESSAGE}"
                    echo "Image ${env.IMAGE}, deploys to: ${env.DEPLOY_ENV ?: 'nowhere (not main or dev)'}"
                }
            }
        }

        stage('Setup') {
            steps {
                script { env.CURRENT_STAGE = 'Test' }
                timeout(time: 10, unit: 'MINUTES') {
                    retry(2) {
                        sh '''
                            python3.11 -m venv .venv
                            .venv/bin/pip install --quiet -r dashboard/requirements-dev.txt -r demo-app/requirements-dev.txt
                            mkdir -p reports
                        '''
                    }
                }
            }
        }

        stage('Quality gates') {
            parallel {
                stage('Lint') {
                    steps {
                        script { env.CURRENT_STAGE = 'Test' }
                        sh '''
                            (cd demo-app && ../.venv/bin/flake8 .)
                            (cd dashboard && ../.venv/bin/flake8 .)
                        '''
                    }
                }
                stage('Unit tests') {
                    steps {
                        script { env.CURRENT_STAGE = 'Test' }
                        sh '''
                            cd demo-app
                            ../.venv/bin/python -m pytest --junitxml=../reports/junit-demo-app.xml \
                              --cov=app --cov-report=term --cov-report=xml:../reports/coverage-demo-app.xml
                            cd ../dashboard
                            ../.venv/bin/python -m pytest --junitxml=../reports/junit-dashboard.xml \
                              --cov=app --cov-report=term --cov-report=xml:../reports/coverage-dashboard.xml
                        '''
                    }
                    post {
                        always {
                            junit testResults: 'reports/junit-*.xml', allowEmptyResults: true
                            recordCoverage tools: [[parser: 'COBERTURA', pattern: 'reports/coverage-*.xml']]
                        }
                    }
                }
                stage('Dependency scan') {
                    steps {
                        script { env.CURRENT_STAGE = 'Test' }
                        timeout(time: 10, unit: 'MINUTES') {
                            // Scans the pinned requirements*.txt files for known vulnerabilities.
                            sh '''
                                set +e
                                trivy fs --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed \
                                  --exit-code 1 --no-progress --skip-dirs .venv \
                                  --output reports/trivy-fs.txt .
                                rc=$?
                                cat reports/trivy-fs.txt
                                exit $rc
                            '''
                        }
                    }
                }
            }
        }

        stage('Build') {
            steps {
                script { env.CURRENT_STAGE = 'Build' }
                // --pull: always start from the latest (patched) base image.
                // Labels record where the image came from; deploy.sh reads them back.
                sh '''
                    docker build --pull \
                      --file "demo-app/$DOCKERFILE" \
                      --label "org.opencontainers.image.revision=$GIT_COMMIT" \
                      --label "org.opencontainers.image.version=$APP_VERSION" \
                      --label "sentinelops.build-number=$BUILD_NUMBER" \
                      --label "sentinelops.branch=$BRANCH_NAME" \
                      --tag "$IMAGE" \
                      demo-app
                '''
            }
        }

        stage('Image scan') {
            steps {
                script { env.CURRENT_STAGE = 'Scan' }
                timeout(time: 10, unit: 'MINUTES') {
                    // --ignore-unfixed: only fail on vulnerabilities that have a fix available.
                    sh '''
                        set +e
                        trivy image --scanners vuln --severity HIGH,CRITICAL --ignore-unfixed \
                          --exit-code 1 --no-progress --output reports/trivy-image.txt "$IMAGE"
                        rc=$?
                        cat reports/trivy-image.txt
                        exit $rc
                    '''
                }
            }
            post {
                failure {
                    // A rejected image never leaves this machine.
                    sh 'docker rmi "$IMAGE" || true'
                }
            }
        }

        stage('Push') {
            when { anyOf { branch 'main'; branch 'dev' } }
            steps {
                script { env.CURRENT_STAGE = 'Push' }
                retry(2) {
                    sh '''
                        aws ecr get-login-password --region "$AWS_REGION" \
                          | docker login --username AWS --password-stdin "${ECR_REPOSITORY_URL%%/*}"
                        docker push "$IMAGE"
                    '''
                }
            }
        }

        stage('Approval') {
            when { branch 'main' }
            steps {
                script { env.CURRENT_STAGE = 'Deploy' }
                timeout(time: 30, unit: 'MINUTES') {
                    input message: "Deploy ${env.SHORT_SHA} to production?", ok: 'Deploy'
                }
            }
        }

        stage('Deploy') {
            when { anyOf { branch 'main'; branch 'dev' } }
            steps {
                script {
                    env.CURRENT_STAGE = 'Deploy'
                    // BREAK_HEALTH (build parameter) is read by deploy.sh from the environment.
                    if (sh(script: 'scripts/deploy.sh "$DEPLOY_ENV" "$IMAGE"', returnStatus: true) != 0) {
                        rollbackAndFail('deploy.sh failed')
                    }
                }
            }
        }

        stage('Health check') {
            when { anyOf { branch 'main'; branch 'dev' } }
            steps {
                script {
                    env.CURRENT_STAGE = 'Health check'
                    if (sh(script: 'scripts/healthcheck.sh "http://localhost:$APP_PORT/health" 5', returnStatus: true) != 0) {
                        rollbackAndFail('Health check failed')
                    }
                }
                // Healthy: this image becomes the rollback target for the next deploy.
                retry(2) {
                    sh '''
                        docker tag "$IMAGE" "$ECR_REPOSITORY_URL:$STABLE_TAG"
                        docker push "$ECR_REPOSITORY_URL:$STABLE_TAG"
                    '''
                }
                script { env.DEPLOY_STATUS = 'SUCCESS' }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
            script {
                def result = currentBuild.currentResult
                if (result == 'ABORTED') {
                    echo 'Run was aborted (for example, production approval declined): not reported.'
                    return
                }
                if (env.DEPLOY_ENV) {
                    // main/dev: every run is a deployment attempt and is recorded.
                    def status = env.DEPLOY_STATUS ?: 'FAILED'
                    reportToDashboard(status)
                    sendNotification(status)
                } else if (result != 'SUCCESS') {
                    // Feature branches and pull requests: only email when something broke.
                    sendNotification(result)
                }
                if (!env.DEPLOY_ENV && env.IMAGE) {
                    // Not deployed, so the local image is not needed any more.
                    sh 'docker rmi "$IMAGE" > /dev/null 2>&1 || true'
                }
            }
        }
        cleanup {
            cleanWs()
        }
    }
}
