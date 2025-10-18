from flask import Flask, jsonify
from config import Config
from database.database import init_db
from routes import init_routes
import os

from flask_cors import CORS

app = Flask(__name__)
app.config.from_object(Config)

# Configure CORS with a restricted set of allowed origins.
# The `CORS_ALLOWED_ORIGINS` can be a comma-separated env var. If empty, use localhost defaults for dev.
raw_origins = getattr(Config, 'CORS_ALLOWED_ORIGINS', '') or ''
if raw_origins.strip():
    origins = [o.strip() for o in raw_origins.split(',') if o.strip()]
else:
    # sensible default for local development
    origins = ['http://127.0.0.1:5000', 'http://localhost:5000','http://localhost:5173']

# Apply CORS only for API routes and with explicit origins list
CORS(app, resources={r"/api/*": {"origins": origins}}, supports_credentials=True)
# Initialiser la base de données
init_db(app)

# Enregistrer les routes
init_routes(app)

@app.route('/')
def index():
    """Route racine"""
    return jsonify({
        'message': 'API de Gestion des Surveillances',
        'version': '1.0',
        'endpoints': {
            'grades': '/api/grades',
            'sessions': '/api/sessions',
            'enseignants': '/api/enseignants',
            'creneaux': '/api/creneaux',
            'voeux': '/api/voeux',
            'affectations': '/api/affectations',
            'statistics': '/api/statistics/session/<id_session>',
            'statistics_all': '/api/statistics/sessions',
            'presence': '/api/presence',
            'presence_session': '/api/presence/session/<id_session>',
            'presence_enseignant': '/api/presence/enseignant/<code_smartex>',
            'generate_convocations': '/api/affectations/generate_convocations/<id_session>',
            'generate_presences_responsables': '/api/affectations/generate_presences_responsables/<id_session>'
        }
    })

@app.route('/api/health')
def health():
    """Vérifier l'état de l'API"""
    return jsonify({'status': 'ok', 'database': os.path.exists(Config.DB_NAME)})

@app.errorhandler(404)
def not_found(error):
    return jsonify({'error': 'Route non trouvée'}), 404

@app.errorhandler(500)
def internal_error(error):
    return jsonify({'error': 'Erreur serveur interne'}), 500

if __name__ == '__main__':
    # Créer la base de données si elle n'existe pas
    if not os.path.exists(Config.DB_NAME):
        print("⚠️  Base de données non trouvée, création...")
        from database.create_database import create_database
        create_database()
    
    print("\n" + "="*60)
    print("🚀 Démarrage de l'API Flask")
    print("="*60)
    print(f"📁 Base de données: {Config.DB_NAME}")
    print(f"🌐 URL: http://127.0.0.1:5000")
    print("="*60 + "\n")
    
    app.run(debug=True)