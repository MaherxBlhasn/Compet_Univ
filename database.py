import sqlite3
from flask import g
from config import Config

def get_db():
    """Obtenir une connexion à la base de données"""
    if 'db' not in g:
        g.db = sqlite3.connect(Config.DB_NAME)
        g.db.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par nom
    return g.db

def close_db(e=None):
    """Fermer la connexion à la base de données"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    """Initialiser la base de données"""
    app.teardown_appcontext(close_db)
