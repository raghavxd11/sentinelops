"""Entry point.

Local:   python wsgi.py
Docker:  gunicorn --preload wsgi:app
"""
import os

from app import create_app
from app.extensions import db

app = create_app()

# With --preload, gunicorn builds the app once (this also creates the tables)
# and then forks the worker processes. Close the database connection used so
# far, so every worker opens its own instead of sharing this one.
with app.app_context():
    db.engine.dispose()

if __name__ == "__main__":
    debug = os.environ.get("FLASK_DEBUG") == "1"
    app.run(host="127.0.0.1", port=5000, debug=debug)
