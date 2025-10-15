import os

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    DB_NAME = 'surveillance.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    JSON_SORT_KEYS = False
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16 MB max
    # Comma-separated list of allowed CORS origins (example: 'http://localhost:3000,http://example.com')
    # Leave empty to use a sensible localhost-only default in development.
    CORS_ALLOWED_ORIGINS = os.environ.get('CORS_ALLOWED_ORIGINS') or ''
