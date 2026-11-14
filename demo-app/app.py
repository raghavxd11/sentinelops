"""demo-app: the small service the SentinelOps pipeline builds and deploys.

It is the website of Brewly, a fictional coffee shop. Every page footer shows
the version, commit and container, so each deploy visibly changes the site.

Pages (HTML, templates/ + static/style.css)
    /           Home
    /menu       Menu with prices
    /about      About and visiting info

Endpoints used by the pipeline and Docker
    /health     200 when healthy, 500 when BREAK_HEALTH=true
    /api/info   version and git commit as JSON

Environment variables (set by the pipeline when it starts the container)
    APP_VERSION    release version, e.g. build-42
    GIT_COMMIT     commit the image was built from
    BREAK_HEALTH   "true" makes /health fail, to demo a failed deploy and rollback

Breaking a container that is already running (self-healing demo)
    docker exec <container> touch /tmp/break-health
/health fails while that file exists. Docker marks the container unhealthy,
autoheal restarts it, and the app deletes the file when it starts again, so
the restart fixes the problem (like a restart clears a hung process).
"""
import os
import socket

from flask import Flask, jsonify, render_template

app = Flask(__name__)

BREAK_HEALTH_FILE = os.environ.get("BREAK_HEALTH_FILE", "/tmp/break-health")

# The menu lives here as plain data; templates/menu.html only lays it out.
# Prices are in rupees.
MENU = [
    {
        "section": "Espresso",
        "note": "Our house blend: Chikmagalur and Coorg, roasted medium.",
        "items": [
            {"name": "Espresso", "detail": "Double shot", "price": 140},
            {"name": "Cortado", "detail": "Equal parts espresso and steamed milk", "price": 170},
            {"name": "Flat white", "detail": "Double shot, thin layer of milk", "price": 190},
            {"name": "Cappuccino", "detail": "", "price": 190},
            {"name": "Iced latte", "detail": "", "price": 210},
        ],
    },
    {
        "section": "Filter and slow",
        "note": "Single-origin beans, changed every Tuesday.",
        "items": [
            {"name": "Filter coffee", "detail": "Brass dabarah, with or without chicory",
             "price": 90},
            {"name": "Pour-over", "detail": "V60, this week's single origin", "price": 220},
            {"name": "Cold brew", "detail": "Steeped for 18 hours", "price": 200},
        ],
    },
    {
        "section": "Not coffee",
        "note": "",
        "items": [
            {"name": "Masala chai", "detail": "Ginger, cardamom, a little pepper", "price": 80},
            {"name": "Hot chocolate", "detail": "70% dark, made with whole milk", "price": 180},
            {"name": "Lemon iced tea", "detail": "", "price": 150},
        ],
    },
    {
        "section": "To eat",
        "note": "Baked each morning by Anu's, two doors down.",
        "items": [
            {"name": "Butter croissant", "detail": "", "price": 160},
            {"name": "Banana walnut bread", "detail": "Toasted, with salted butter", "price": 140},
            {"name": "Egg and cheese sandwich", "detail": "On sourdough", "price": 240},
        ],
    },
]

MILK_NOTE = "Oat or almond milk on anything, add 40."


def app_info():
    """Read the environment on every request, so the values always match the container."""
    return {
        "app": "demo-app",
        "version": os.environ.get("APP_VERSION", "dev"),
        "git_commit": os.environ.get("GIT_COMMIT", "unknown"),
        "hostname": socket.gethostname(),
    }


@app.context_processor
def deploy_info():
    """Values every template can use, for the footer: version, short commit, container."""
    info = app_info()
    return {
        "version": info["version"],
        "short_commit": info["git_commit"][:7],
        "hostname": info["hostname"],
    }


def clear_break_health_file():
    """Called once at startup: a restarted container starts healthy again."""
    if os.path.exists(BREAK_HEALTH_FILE):
        os.remove(BREAK_HEALTH_FILE)


def health_is_broken():
    if os.path.exists(BREAK_HEALTH_FILE):
        return True
    return os.environ.get("BREAK_HEALTH", "").strip().lower() == "true"


clear_break_health_file()


@app.route("/")
def home():
    return render_template("home.html", page="home")


@app.route("/menu")
def menu():
    return render_template("menu.html", page="menu", menu=MENU, milk_note=MILK_NOTE)


@app.route("/about")
def about():
    return render_template("about.html", page="about")


@app.route("/health")
def health():
    if health_is_broken():
        return jsonify({"status": "unhealthy", "reason": "health check broken on purpose"}), 500
    return jsonify({"status": "ok"})


@app.route("/api/info")
def info():
    return jsonify(app_info())


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=int(os.environ.get("PORT", "8000")))
