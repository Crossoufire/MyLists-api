import os
from dotenv import load_dotenv


load_dotenv()
basedir = os.path.abspath(os.path.dirname(__file__))


def as_bool(value: str) -> bool:
    """ Change value as boolean """

    if value:
        return value.lower() in ["true", "yes", "on", "1"]

    return False


class Config:
    """ Config class for environment variables """

    # Database option
    SQLALCHEMY_DATABASE_URI = os.environ.get("MYLISTS_DATABASE_URI") or "sqlite:///site.db"
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    # Security options
    SECRET_KEY = os.environ.get("SECRET_KEY", "top-secret!")
    ACCESS_TOKEN_MINUTES = int(os.environ.get("ACCESS_TOKEN_MINUTES") or "15")
    REFRESH_TOKEN_DAYS = int(os.environ.get("REFRESH_TOKEN_DAYS") or "7")
    REFRESH_TOKEN_IN_COOKIE = as_bool(os.environ.get("REFRESH_TOKEN_IN_COOKIE") or "yes")
    RESET_TOKEN_MINUTES = int(os.environ.get("RESET_TOKEN_MINUTES") or "15")
    MAX_CONTENT_LENGTH = 8 * 1024 * 1024

    # Email options
    MAIL_SERVER = os.environ.get("MAIL_SERVER", "localhost")
    MAIL_PORT = int(os.environ.get("MAIL_PORT") or "25")
    MAIL_USE_TLS = as_bool(os.environ.get("MAIL_USE_TLS"))
    MAIL_USE_SSL = as_bool(os.environ.get("MAIL_USE_SSL"))
    MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
    MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")

    # API keys
    THEMOVIEDB_API_KEY = os.environ.get("THEMOVIEDB_API_KEY") or None
    GOOGLE_BOOKS_API_KEY = os.environ.get("GOOGLE_BOOKS_API_KEY") or None
    CLIENT_IGDB = os.environ.get("CLIENT_IGDB") or None
    SECRET_IGDB = os.environ.get("SECRET_IGDB") or None
    IGDB_API_KEY = os.environ.get("IGDB_API_KEY") or None

    # Caching type
    CACHE_TYPE = os.environ.get("CACHE_TYPE") or "simple"

