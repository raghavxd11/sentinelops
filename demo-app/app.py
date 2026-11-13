"""demo-app: the small service the SentinelOps pipeline builds and deploys.

Endpoints
    /           HTML page showing which version is running
    /health     200 when healthy, 500 when BREAK_HEALTH=true
    /api/info   version and git commit as JSON

Environment variables (set by the pipeline when it starts the container)
    APP_VERSION    release version, e.g. 1.0.0
    GIT_COMMIT     commit the image was built from
    BREAK_HEALTH   "true" makes /health fail, to demo a failed deploy and rollback
"""
import os
import socket

from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

PAGE = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>demo-app {{ version }}</title>
  <style>
    body { margin: 0; background: #0E0F11; color: #E7E9EC;
           font: 14px/1.5 system-ui, -apple-system, "Segoe UI", sans-serif; }
    main { max-width: 560px; padding: 48px 24px; }
    h1 { font: 500 28px/1.2 ui-monospace, Consolas, monospace; margin: 0 0 4px; }
    p { color: #9BA1AB; margin: 0 0 24px; }
    dl { display: grid; grid-template-columns: 120px 1fr; margin: 0;
         border: 1px solid #2A2E35; border-radius: 6px; background: #16181C; }
    dt, dd { margin: 0; padding: 8px 14px; border-bottom: 1px solid #2A2E35; }
    dt { color: #6B717C; }
    dd { font-family: ui-monospace, Consolas, monospace; overflow-wrap: anywhere; }
    dt:last-of-type, dd:last-of-type { border-bottom: 0; }
    .ok { color: #3FB950; }
    .bad { color: #F85149; }
    a { color: #E7E9EC; }
  </style>
</head>
<body>
  <main>
    <h1>demo-app</h1>
    <p>Deployed by the SentinelOps pipeline.</p>
    <dl>
      <dt>Version</dt><dd>{{ version }}</dd>
      <dt>Git commit</dt><dd>{{ git_commit }}</dd>
      <dt>Container</dt><dd>{{ hostname }}</dd>
      <dt>Health</dt>
      <dd>
        {% if healthy %}
        <span class="ok">ok</span>
        {% else %}
        <span class="bad">failing</span>
        {% endif %}
        (<a href="/health">/health</a>)
      </dd>
      <dt>JSON</dt><dd><a href="/api/info">/api/info</a></dd>
    </dl>
  </main>
</body>
</html>
"""


def app_info():
    """Read the environment on every request, so the values always match the container."""
    return {
        "app": "demo-app",
        "version": os.environ.get("APP_VERSION", "dev"),
        "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
        "hostname": socket.gethostname(),
    }


def health_is_broken():
    return os.environ.get("BREAK_HEALTH", "").strip().lower() == "true"


@app.route("/")
def index():
    return render_template_string(PAGE, healthy=not health_is_broken(), **app_info())


@app.route("/health")
def health():
    if health_is_broken():
        return jsonify({"status": "unhealthy", "reason": "BREAK_HEALTH is set"}), 500
    return jsonify({"status": "ok"})


@app.route("/api/info")
def info():
    return jsonify(app_info())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
