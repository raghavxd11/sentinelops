"""All configuration comes from environment variables (see .env.example)."""
import os

from dotenv import load_dotenv

# Reads a .env file if one exists; real environment variables win.
load_dotenv()


class Config:
    # Signs the session cookie and CSRF tokens. The fallback is for local runs only.
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-change-me")

    # MySQL in Docker, SQLite file when nothing is set (quick local check).
    SQLALCHEMY_DATABASE_URI = os.environ.get("DATABASE_URL", "sqlite:///sentinelops.db")

    # Check a pooled connection is alive before using it (MySQL drops idle ones).
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True}

    # Jenkins must send this in the X-API-Token header. Empty = API writes disabled.
    API_TOKEN = os.environ.get("API_TOKEN", "")
