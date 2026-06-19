"""
config.py — Phase 10: Configuration Management

Centralizes all environment-driven settings. Reads a local `.env` file if
python-dotenv is available (optional dependency — falls back silently if
not installed, so this never breaks existing deployments).

All values fall back to safe defaults matching the project's previous
hardcoded behaviour, so importing this module changes NOTHING unless the
corresponding environment variable is set.
"""
import os

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


class Config:
    # Flask
    SECRET_KEY: str = os.environ.get("SECRET_KEY", "appart-ai-pfe-2025-secret")
    DEBUG: bool = os.environ.get("FLASK_DEBUG", "1") == "1"
    PORT: int = int(os.environ.get("PORT", "5000"))
    HOST: str = os.environ.get("HOST", "0.0.0.0")

    # Logging
    LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO").upper()

    # Paths
    BASE_DIR: str = os.path.dirname(os.path.abspath(__file__))
    DATA_DIR: str = os.path.join(BASE_DIR, "data")
    DB_PATH: str  = os.environ.get("DB_PATH", os.path.join(DATA_DIR, "app.db"))
    HOUSING_CSV: str = os.environ.get("HOUSING_CSV", os.path.join(DATA_DIR, "housing.csv"))
    MODEL_PATH: str  = os.environ.get("MODEL_PATH", os.path.join(DATA_DIR, "price_model.pkl"))

    # ML
    ML_RETRAIN_ON_START: bool = os.environ.get("ML_RETRAIN_ON_START", "0") == "1"

    # Recommendations
    DEFAULT_TOP_N: int = int(os.environ.get("DEFAULT_TOP_N", "5"))


config = Config()
