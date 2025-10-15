import sqlite3
from flask import Blueprint, jsonify, request
from database import get_db

enseignant_bp = Blueprint('enseignants', __name__)

@enseignant_bp.route('', methods=['GET'])
def get_all_enseignants():
    """GET /api/enseignants - Récupérer tous les enseignants"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT e.*, g.quota 
            FROM enseignant e
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
            ORDER BY e.nom_ens, e.prenom_ens
        ''')
        enseignants = [dict(row) for row in cursor.fetchall()]
        return jsonify(enseignants), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@enseignant_bp.route('/<int:code_smartex_ens>', methods=['GET'])
def get_enseignant(code_smartex_ens):
    """GET /api/enseignants/<code> - Récupérer un enseignant"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT e.*, g.quota 
            FROM enseignant e
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
            WHERE e.code_smartex_ens = ?
        ''', (code_smartex_ens,))
        enseignant = cursor.fetchone()
        if enseignant is None:
            return jsonify({'error': 'Enseignant non trouvé'}), 404
        return jsonify(dict(enseignant)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@enseignant_bp.route('', methods=['POST'])
def create_enseignant():
    """POST /api/enseignants - Créer un enseignant"""
    try:
        data = request.get_json()
        required = ['code_smartex_ens', 'nom_ens', 'prenom_ens', 'grade_code_ens']
        if not data or not all(k in data for k in required):
            return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        db.execute('''
            INSERT INTO enseignant (code_smartex_ens, nom_ens, prenom_ens, 
                                   email_ens, grade_code_ens, participe_surveillance)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['code_smartex_ens'], data['nom_ens'], data['prenom_ens'],
              data.get('email_ens'), data['grade_code_ens'], 
              data.get('participe_surveillance', 1)))
        db.commit()
        return jsonify({'message': 'Enseignant créé avec succès', 
                       'code_smartex_ens': data['code_smartex_ens']}), 201
    except sqlite3.IntegrityError as e:
        if 'UNIQUE' in str(e):
            return jsonify({'error': 'Cet enseignant existe déjà'}), 409
        return jsonify({'error': 'Grade invalide'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@enseignant_bp.route('/<int:code_smartex_ens>', methods=['PUT'])
def update_enseignant(code_smartex_ens):
    """PUT /api/enseignants/<code> - Modifier un enseignant"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        db = get_db()
        cursor = db.execute('''
            UPDATE enseignant 
            SET nom_ens = COALESCE(?, nom_ens),
                prenom_ens = COALESCE(?, prenom_ens),
                email_ens = COALESCE(?, email_ens),
                grade_code_ens = COALESCE(?, grade_code_ens),
                participe_surveillance = COALESCE(?, participe_surveillance)
            WHERE code_smartex_ens = ?
        ''', (data.get('nom_ens'), data.get('prenom_ens'), data.get('email_ens'),
              data.get('grade_code_ens'), data.get('participe_surveillance'),
              code_smartex_ens))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Enseignant non trouvé'}), 404
        return jsonify({'message': 'Enseignant modifié avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@enseignant_bp.route('/<int:code_smartex_ens>', methods=['DELETE'])
def delete_enseignant(code_smartex_ens):
    """DELETE /api/enseignants/<code> - Supprimer un enseignant"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM enseignant WHERE code_smartex_ens = ?', 
                           (code_smartex_ens,))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Enseignant non trouvé'}), 404
        return jsonify({'message': 'Enseignant supprimé avec succès'}), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: cet enseignant a des affectations'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500