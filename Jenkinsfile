// SentinelOps pipeline for demo-app (main branch only).
//
// Checkout -> Test -> Build -> Scan -> Push -> Deploy -> Health check
// Health check passes  -> the image is also tagged latest-stable in ECR.
// Health check fails   -> scripts/rollback.sh puts latest-stable back (build = UNSTABLE, ROLLED_BACK).
// Every outcome is reported to the dashboard in post { always }.
//
// Runs on the single EC2 server: Jenkins, Docker and the dashboard share one host,
// so the dashboard and demo-app are reached on localhost.
// Setup steps: docs/jenkins-setup.md

pipeline {
    agent any

    triggers {
        githubPush()   // GitHub webhook -> build on every push to main
    }

    parameters {
        booleanParam(name: 'BREAK_HEALTH', defaultValue: false,
            description: 'Demo: deploy a version whose /health returns 500, to show the automatic rollback')
        choice(name: 'DOCKERFILE', choices: ['Dockerfile', 'Dockerfile.vulnerable'],
            description: 'Demo: Dockerfile.vulnerable uses an old base image, to show Trivy blocking the build')
    }

    options {
        timestamps()
        buildDiscarder(logRotator(numToKeepStr: '20'))
        timeout(time: 30, unit: 'MINUTES')
        skipDefaultCheckout(true)   // checkout happens in the Checkout stage, so a failure there is reported
    }

    environment {
        AWS_REGION    = 'us-east-1'
        ECR_REGISTRY  = '567190388316.dkr.ecr.us-east-1.amazonaws.com'
        ECR_REPO      = "${ECR_REGISTRY}/sentinelops/demo-app"
        STABLE_IMAGE  = "${ECR_REPO}:latest-stable"
        CONTAINER     = 'demo-app'
        APP_PORT      = '8000'
        HEALTH_URL    = 'http://localhost:8000/health'
        DASHBOARD_URL = 'http://localhost:5000'
        SERVICE_NAME  = 'demo-app'   // must exist on the dashboard's Services page
    }

    stages {
        // Stage names match the dashboard's list of stages, so the failed one can be reported.
        stage('Checkout') {
            steps {
                script {
                    env.LAST_STAGE = env.STAGE_NAME
                    def scmVars = checkout scm

                    env.COMMIT_HASH    = sh(script: 'git rev-parse HEAD', returnStdout: true).trim()
                    env.SHORT_SHA      = sh(script: 'git rev-parse --short=7 HEAD', returnStdout: true).trim()
                    env.COMMIT_AUTHOR  = sh(script: 'git log -1 --format=%an', returnStdout: true).trim()
                    env.COMMIT_MESSAGE = sh(script: 'git log -1 --format=%s', returnStdout: true).trim()
                    env.COMMITTED_AT   = sh(script: 'git log -1 --format=%cI', returnStdout: true).trim()
                    env.BRANCH         = (scmVars.GIT_BRANCH ?: 'main').replaceFirst('^origin/', '')

                    // Parameters copied into env vars for the shell steps. "params" always has the
                    // defaults, even on the job's very first run (before Jenkins knows the parameters).
                    env.DOCKERFILE_NAME   = params.DOCKERFILE ?: 'Dockerfile'
                    env.BREAK_HEALTH_FLAG = params.BREAK_HEALTH ? 'true' : 'false'

                    // A vulnerable demo build gets its own tag, so it can never replace a real one.
                    env.IMAGE_TAG = env.DOCKERFILE_NAME == 'Dockerfile' ? env.SHORT_SHA : "${env.SHORT_SHA}-vulnerable"
                    env.IMAGE     = "${env.ECR_REPO}:${env.IMAGE_TAG}"
                    echo "Commit ${env.SHORT_SHA} by ${env.COMMIT_AUTHOR}: ${env.COMMIT_MESSAGE}"
                }
            }
        }

        stage('Test') {
            steps {
                script { env.LAST_STAGE = env.STAGE_NAME }
                dir('demo-app') {
                    sh '''
                        python3.11 -m venv .venv
                        . .venv/bin/activate
                        pip install -q -r requirements-dev.txt
                        mkdir -p ../reports
                        pytest --junitxml=../reports/junit.xml \
                               --cov=app --cov-report=term --cov-report=xml:../reports/coverage.xml
                    '''
                }
            }
            post {
                always {
                    junit testResults: 'reports/junit.xml', allowEmptyResults: true
                }
            }
        }

        stage('Build') {
            steps {
                script { env.LAST_STAGE = env.STAGE_NAME }
                // Labels record where the image came from; rollback.sh reads them back.
                sh '''
                    docker build \
                      -f "demo-app/$DOCKERFILE_NAME" \
                      -t "$IMAGE" \
                      --label org.opencontainers.image.revision="$COMMIT_HASH" \
                      --label org.opencontainers.image.version="build-$BUILD_NUMBER" \
                      --label jenkins.build_number="$BUILD_NUMBER" \
                      demo-app
                '''
            }
        }

        stage('Scan') {
            steps {
                script {
                    env.LAST_STAGE = env.STAGE_NAME
                    sh 'mkdir -p reports'
                    // Fail on HIGH/CRITICAL CVEs that have a fix. --ignore-unfixed: a CVE with
                    // no fix yet can't be patched by us and would keep the pipeline red forever.
                    def trivyExit = sh(returnStatus: true, script: '''
                        trivy image --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
                          --format table --output reports/trivy-image.txt "$IMAGE"
                    ''')
                    sh 'cat reports/trivy-image.txt || true'
                    if (trivyExit != 0) {
                        error("Trivy found fixable HIGH/CRITICAL vulnerabilities in ${env.IMAGE} (see reports/trivy-image.txt). Image not pushed.")
                    }
                }
            }
        }

        stage('Push') {
            steps {
                script { env.LAST_STAGE = env.STAGE_NAME }
                // No keys: the AWS CLI gets temporary credentials from the EC2 instance profile.
                retry(2) {
                    sh '''
                        aws ecr get-login-password --region "$AWS_REGION" \
                          | docker login --username AWS --password-stdin "$ECR_REGISTRY"
                        docker push "$IMAGE"
                    '''
                }
            }
        }

        stage('Deploy') {
            steps {
                script { env.LAST_STAGE = env.STAGE_NAME }
                // BREAK_HEALTH=true only when the demo parameter is ticked.
                sh '''
                    APP_VERSION="build-$BUILD_NUMBER" GIT_COMMIT="$COMMIT_HASH" BREAK_HEALTH="$BREAK_HEALTH_FLAG" \
                      bash scripts/deploy.sh "$IMAGE" "$CONTAINER" "$APP_PORT"
                '''
            }
        }

        stage('Health check') {
            steps {
                script {
                    env.LAST_STAGE = env.STAGE_NAME
                    def healthExit = sh(returnStatus: true,
                        script: 'bash scripts/healthcheck.sh "$HEALTH_URL" 5 5')

                    if (healthExit == 0) {
                        // This version works: it becomes the one to roll back to next time.
                        sh '''
                            docker tag "$IMAGE" "$STABLE_IMAGE"
                            docker push "$STABLE_IMAGE"
                        '''
                        env.DEPLOY_STATUS = 'SUCCESS'
                    } else {
                        // If there is no latest-stable yet, or it is unhealthy too, rollback.sh
                        // exits non-zero, this sh step fails and the build is FAILED.
                        sh 'bash scripts/rollback.sh "$STABLE_IMAGE" "$CONTAINER" "$APP_PORT" "$HEALTH_URL"'
                        env.DEPLOY_STATUS = 'ROLLED_BACK'
                        currentBuild.description = "ROLLED_BACK to latest-stable (${env.IMAGE_TAG} failed /health)"
                        unstable("Health check failed for ${env.IMAGE_TAG}; rolled back to latest-stable")
                    }
                }
            }
        }
    }

    post {
        always {
            archiveArtifacts artifacts: 'reports/**', allowEmptyArchive: true
            script {
                if (currentBuild.currentResult == 'SUCCESS') {
                    reportDeployment('SUCCESS', '')
                } else if (env.DEPLOY_STATUS == 'ROLLED_BACK') {
                    reportDeployment('ROLLED_BACK', 'Health check')
                } else {
                    reportDeployment('FAILED', env.LAST_STAGE ?: 'Checkout')
                }
            }
        }
        cleanup {
            cleanWs()
        }
    }
}

// Send the result to the dashboard. Wrapped in try/catch: a missing credential or an
// unreachable dashboard prints a warning but never changes the build result.
def reportDeployment(String status, String failedStage) {
    try {
        if (!fileExists('scripts/report.sh')) {
            echo 'WARNING: scripts/report.sh not found (checkout failed?), result not reported'
            return
        }
        withCredentials([string(credentialsId: 'dashboard-api-token', variable: 'API_TOKEN')]) {
            withEnv(["DURATION_SECONDS=${currentBuild.duration.intdiv(1000)}",
                     "REPORT_STATUS=${status}", "REPORT_STAGE=${failedStage}"]) {
                sh 'bash scripts/report.sh "$REPORT_STATUS" "$REPORT_STAGE"'
            }
        }
    } catch (err) {
        echo "WARNING: could not report the deployment to the dashboard: ${err}"
    }
}
