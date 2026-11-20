import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DEV_SECRET = "dev-only-secret-change-me-in-production-0123456789"


def _database_url():
    url = os.environ.get("DATABASE_URL", f"sqlite:///{BASE / 'gariyangu.db'}")
    return "postgresql://" + url[len("postgres://"):] if url.startswith("postgres://") else url


def _origins():
    return [o.strip() for o in os.environ.get("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip()]


class Config:
    APP_ENV = os.environ.get("APP_ENV", "development")  
    SECRET_KEY = os.environ.get("SECRET_KEY", DEV_SECRET)
    JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY") or SECRET_KEY
    SQLALCHEMY_DATABASE_URI = _database_url()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    CORS_ORIGINS = _origins()
    TOKEN_HOURS = int(os.environ.get("TOKEN_HOURS", "72"))
    BCRYPT_LOG_ROUNDS = int(os.environ.get("BCRYPT_LOG_ROUNDS", "12"))
    UPLOAD_FOLDER = os.environ.get("UPLOAD_FOLDER", str(BASE / "uploads"))
    MAX_CONTENT_LENGTH = 55 * 1024 * 1024  
    JSON_SORT_KEYS = False
    OTP_TTL_MINUTES = int(os.environ.get("OTP_TTL_MINUTES", "10"))
    OTP_MAX_ATTEMPTS = int(os.environ.get("OTP_MAX_ATTEMPTS", "5"))
    OTP_RESEND_SECONDS = int(os.environ.get("OTP_RESEND_SECONDS", "30"))
    SMTP_HOST = os.environ.get("SMTP_HOST", "")
    SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
    SMTP_USER = os.environ.get("SMTP_USER", "")
    SMTP_PASSWORD = os.environ.get("SMTP_PASSWORD", "")
    SMTP_FROM = os.environ.get("SMTP_FROM", "Gari Yangu <no-reply@gariyangu.local>")
    SMTP_SSL = os.environ.get("SMTP_SSL", "0") == "1"  

def check_production(cfg):
    if cfg.get("APP_ENV") != "production":
        return
    if cfg["SECRET_KEY"] == DEV_SECRET or len(cfg["SECRET_KEY"]) < 32:
        raise RuntimeError("Set SECRET_KEY to a random value of at least 32 characters when APP_ENV=production.")
    if "*" in cfg["CORS_ORIGINS"]:
        raise RuntimeError("CORS_ORIGINS must list explicit origins in production (no '*').")
    if not cfg.get("SMTP_HOST"):
        raise RuntimeError("Set SMTP_HOST (and SMTP_USER / SMTP_PASSWORD / SMTP_FROM) so signup codes can be emailed in production.")
