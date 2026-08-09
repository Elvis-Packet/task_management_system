import os
from datetime import timedelta

from dotenv import load_dotenv

load_dotenv()


BASE_DIR = os.path.abspath(os.path.dirname(__file__))

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL is not set. This application requires PostgreSQL — "
        "copy .env.example to .env and set DATABASE_URL. There is no SQLite fallback."
    )

# Some hosts (Render, old Heroku-style connection strings) hand out
# "postgres://" — SQLAlchemy 1.4+/2.0 only recognizes "postgresql://".
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)


class Config:

    SECRET_KEY = os.getenv("SECRET_KEY")

    SQLALCHEMY_DATABASE_URI = DATABASE_URL

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    JWT_SECRET_KEY = os.getenv("JWT_SECRET_KEY")

    JWT_ACCESS_TOKEN_EXPIRES = timedelta(
        minutes=int(os.getenv("JWT_ACCESS_TOKEN_EXPIRES_MINUTES", 60))
    )

    JWT_REFRESH_TOKEN_EXPIRES = timedelta(
        days=int(os.getenv("JWT_REFRESH_TOKEN_EXPIRES_DAYS", 30))
    )

    CORS_ORIGINS = [
        origin.strip()
        for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",")
        if origin.strip()
    ]

    MAIL_SERVER = os.getenv("MAIL_SERVER") or None

    MAIL_PORT = int(os.getenv("MAIL_PORT", 465))

    MAIL_USE_SSL = os.getenv("MAIL_USE_SSL", "True") == "True"

    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "False") == "True"

    MAIL_USERNAME = os.getenv("MAIL_USERNAME") or None

    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD") or None

    MAIL_DEFAULT_SENDER = os.getenv("MAIL_DEFAULT_SENDER") or None

    APP_NAME = os.getenv("APP_NAME", "Survitec Task Performance Management System")

    APP_VERSION = os.getenv("APP_VERSION", "1.0.0")

    SEED_SUPER_ADMIN_EMAIL = os.getenv("SEED_SUPER_ADMIN_EMAIL")

    SEED_SUPER_ADMIN_PASSWORD = os.getenv("SEED_SUPER_ADMIN_PASSWORD")

    SEED_MANAGER_EMAIL = os.getenv("SEED_MANAGER_EMAIL")

    SEED_MANAGER_PASSWORD = os.getenv("SEED_MANAGER_PASSWORD")