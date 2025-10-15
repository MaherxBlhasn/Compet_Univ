from flask import Flask, jsonify
from config import Config
from database import init_db
from routes import init_routes
import os

app = Flask(__name__)
app.config.from_object(Config)

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
            'affectations': '/api/affectations'
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
        from create_database import create_database
        create_database()
    
    print("\n" + "="*60)
    print("🚀 Démarrage de l'API Flask")
    print("="*60)
    print(f"📁 Base de données: {Config.DB_NAME}")
    print(f"🌐 URL: http://127.0.0.1:5000")
    print("="*60 + "\n")
    
    app.run(debug=True)