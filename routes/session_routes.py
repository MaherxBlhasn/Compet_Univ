import sqlite3
from flask import Blueprint, jsonify, request
from database import get_db

session_bp = Blueprint('sessions', __name__)

@session_bp.route('', methods=['GET'])
def get_all_sessions():
    """GET /api/sessions - Récupérer toutes les sessions"""
    try:
        db = get_db()
        cursor = db.execute('SELECT * FROM session ORDER BY date_debut DESC')
        sessions = [dict(row) for row in cursor.fetchall()]
        return jsonify(sessions), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@session_bp.route('/<int:id_session>', methods=['GET'])
def get_session(id_session):
    """GET /api/sessions/<id> - Récupérer une session"""
    try:
        db = get_db()
        cursor = db.execute('SELECT * FROM session WHERE id_session = ?', (id_session,))
        session = cursor.fetchone()
        if session is None:
            return jsonify({'error': 'Session non trouvée'}), 404
        return jsonify(dict(session)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@session_bp.route('', methods=['POST'])
def create_session():
    """POST /api/sessions - Créer une session"""
    try:
        data = request.get_json()
        if not data or 'libelle_session' not in data:
            return jsonify({'error': 'libelle_session requis'}), 400
        
        db = get_db()
        cursor = db.execute('''
            INSERT INTO session (libelle_session, date_debut, date_fin)
            VALUES (?, ?, ?)
        ''', (data['libelle_session'], 
              data.get('date_debut'), 
              data.get('date_fin')))
        db.commit()
        return jsonify({'message': 'Session créée avec succès', 'id_session': cursor.lastrowid}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Une session avec ce libellé existe déjà'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@session_bp.route('/<int:id_session>', methods=['PUT'])
def update_session(id_session):
    """PUT /api/sessions/<id> - Modifier une session"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        db = get_db()
        cursor = db.execute('''
            UPDATE session 
            SET libelle_session = COALESCE(?, libelle_session),
                date_debut = COALESCE(?, date_debut),
                date_fin = COALESCE(?, date_fin)
            WHERE id_session = ?
        ''', (data.get('libelle_session'),
              data.get('date_debut'),
              data.get('date_fin'),
              id_session))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Session non trouvée'}), 404
        return jsonify({'message': 'Session modifiée avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@session_bp.route('/<int:id_session>', methods=['DELETE'])
def delete_session(id_session):
    """DELETE /api/sessions/<id> - Supprimer une session"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM session WHERE id_session = ?', (id_session,))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Session non trouvée'}), 404
        return jsonify({'message': 'Session supprimée avec succès'}), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: des créneaux/vœux sont liés à cette session'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500
