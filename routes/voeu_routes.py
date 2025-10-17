import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db

voeu_bp = Blueprint('voeux', __name__)

@voeu_bp.route('', methods=['GET'])
def get_all_voeux():
    """GET /api/voeux - Récupérer tous les vœux"""
    try:
        db = get_db()
        # Paramètres de filtrage optionnels
        code_smartex_ens = request.args.get('code_smartex_ens', type=int)
        id_session = request.args.get('id_session', type=int)
        
        query = '''
            SELECT v.*, 
                   e.nom_ens, e.prenom_ens, e.grade_code_ens,
                   s.libelle_session
            FROM voeu v
            JOIN enseignant e ON v.code_smartex_ens = e.code_smartex_ens
            JOIN session s ON v.id_session = s.id_session
        '''
        params = []
        
        # Ajouter des filtres si spécifiés
        conditions = []
        if code_smartex_ens:
            conditions.append('v.code_smartex_ens = ?')
            params.append(code_smartex_ens)
        if id_session:
            conditions.append('v.id_session = ?')
            params.append(id_session)
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY v.jour, v.seance'
        
        cursor = db.execute(query, params)
        voeux = [dict(row) for row in cursor.fetchall()]
        return jsonify(voeux), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/<int:voeu_id>', methods=['GET'])
def get_voeu(voeu_id):
    """GET /api/voeux/<id> - Récupérer un vœu"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT v.*, 
                   e.nom_ens, e.prenom_ens, e.grade_code_ens,
                   s.libelle_session
            FROM voeu v
            JOIN enseignant e ON v.code_smartex_ens = e.code_smartex_ens
            JOIN session s ON v.id_session = s.id_session
            WHERE v.voeu_id = ?
        ''', (voeu_id,))
        voeu = cursor.fetchone()
        
        if voeu is None:
            return jsonify({'error': 'Vœu non trouvé'}), 404
        return jsonify(dict(voeu)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('', methods=['POST'])
def create_voeu():
    """POST /api/voeux - Créer un vœu de non-surveillance"""
    try:
        data = request.get_json()
        required = ['code_smartex_ens', 'id_session', 'jour', 'seance']
        
        if not data or not all(k in data for k in required):
            return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        
        # Vérifier si le vœu existe déjà
        cursor = db.execute('''
            SELECT voeu_id FROM voeu 
            WHERE code_smartex_ens = ? AND id_session = ? 
            AND jour = ? AND seance = ?
        ''', (data['code_smartex_ens'], data['id_session'], 
              data['jour'], data['seance']))
        
        if cursor.fetchone():
            return jsonify({'error': 'Ce vœu existe déjà'}), 409
        
        cursor = db.execute('''
            INSERT INTO voeu (code_smartex_ens, id_session, jour, seance)
            VALUES (?, ?, ?, ?)
        ''', (data['code_smartex_ens'], data['id_session'], 
              data['jour'], data['seance']))
        db.commit()
        
        return jsonify({
            'message': 'Vœu créé avec succès',
            'voeu_id': cursor.lastrowid
        }), 201
    except sqlite3.IntegrityError as e:
        if 'FOREIGN KEY' in str(e):
            return jsonify({'error': 'Enseignant ou session invalide'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/<int:voeu_id>', methods=['PUT'])
def update_voeu(voeu_id):
    """PUT /api/voeux/<id> - Modifier un vœu"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        db = get_db()
        cursor = db.execute('''
            UPDATE voeu 
            SET code_smartex_ens = COALESCE(?, code_smartex_ens),
                id_session = COALESCE(?, id_session),
                jour = COALESCE(?, jour),
                seance = COALESCE(?, seance)
            WHERE voeu_id = ?
        ''', (data.get('code_smartex_ens'), data.get('id_session'),
              data.get('jour'), data.get('seance'), voeu_id))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Vœu non trouvé'}), 404
        return jsonify({'message': 'Vœu modifié avec succès'}), 200
    except sqlite3.IntegrityError as e:
        return jsonify({'error': 'Enseignant ou session invalide'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/<int:voeu_id>', methods=['DELETE'])
def delete_voeu(voeu_id):
    """DELETE /api/voeux/<id> - Supprimer un vœu"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM voeu WHERE voeu_id = ?', (voeu_id,))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Vœu non trouvé'}), 404
        return jsonify({'message': 'Vœu supprimé avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/enseignant/<int:code_smartex_ens>/session/<int:id_session>', methods=['GET'])
def get_voeux_enseignant_session(code_smartex_ens, id_session):
    """GET /api/voeux/enseignant/<code>/session/<id> - Vœux d'un enseignant pour une session"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT v.*, s.libelle_session
            FROM voeu v
            JOIN session s ON v.id_session = s.id_session
            WHERE v.code_smartex_ens = ? AND v.id_session = ?
            ORDER BY v.jour, v.seance
        ''', (code_smartex_ens, id_session))
        voeux = [dict(row) for row in cursor.fetchall()]
        return jsonify(voeux), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/batch', methods=['POST'])
def create_voeux_batch():
    """POST /api/voeux/batch - Créer plusieurs vœux en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'voeux' not in data:
            return jsonify({'error': 'Liste de vœux requise'}), 400
        
        voeux_list = data['voeux']
        required = ['code_smartex_ens', 'id_session', 'jour', 'seance']
        
        # Valider tous les vœux
        for voeu in voeux_list:
            if not all(k in voeu for k in required):
                return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        created_ids = []
        errors = []
        
        for voeu in voeux_list:
            try:
                # Vérifier si le vœu existe déjà
                cursor = db.execute('''
                    SELECT voeu_id FROM voeu 
                    WHERE code_smartex_ens = ? AND id_session = ? 
                    AND jour = ? AND seance = ?
                ''', (voeu['code_smartex_ens'], voeu['id_session'], 
                      voeu['jour'], voeu['seance']))
                
                if cursor.fetchone():
                    errors.append({
                        'voeu': voeu,
                        'error': 'Ce vœu existe déjà'
                    })
                    continue
                
                cursor = db.execute('''
                    INSERT INTO voeu (code_smartex_ens, id_session, jour, seance)
                    VALUES (?, ?, ?, ?)
                ''', (voeu['code_smartex_ens'], voeu['id_session'], 
                      voeu['jour'], voeu['seance']))
                created_ids.append(cursor.lastrowid)
            except Exception as e:
                errors.append({
                    'voeu': voeu,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(created_ids)} vœux créés avec succès',
            'created_ids': created_ids,
            'errors': errors
        }), 201 if created_ids else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/enseignant/<int:code_smartex_ens>/session/<int:id_session>', methods=['DELETE'])
def delete_voeux_enseignant_session(code_smartex_ens, id_session):
    """DELETE /api/voeux/enseignant/<code>/session/<id> - Supprimer tous les vœux d'un enseignant pour une session"""
    try:
        db = get_db()
        cursor = db.execute('''
            DELETE FROM voeu 
            WHERE code_smartex_ens = ? AND id_session = ?
        ''', (code_smartex_ens, id_session))
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} vœux supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/all', methods=['DELETE'])
def delete_all_voeux():
    """DELETE /api/voeux/all - Supprimer tous les vœux"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM voeu')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} vœux supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/session/<int:id_session>', methods=['DELETE'])
def delete_voeux_by_session(id_session):
    """DELETE /api/voeux/session/<id> - Supprimer tous les vœux d'une session"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM voeu WHERE id_session = ?', (id_session,))
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} vœux supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@voeu_bp.route('/batch', methods=['DELETE'])
def delete_voeux_batch():
    """DELETE /api/voeux/batch - Supprimer plusieurs vœux par leurs IDs"""
    try:
        data = request.get_json()
        
        if not data or 'voeu_ids' not in data:
            return jsonify({'error': 'Liste d\'IDs de vœux requise'}), 400
        
        voeu_ids = data['voeu_ids']
        
        if not isinstance(voeu_ids, list) or len(voeu_ids) == 0:
            return jsonify({'error': 'La liste d\'IDs doit être non vide'}), 400
        
        db = get_db()
        placeholders = ','.join(['?' for _ in voeu_ids])
        cursor = db.execute(f'DELETE FROM voeu WHERE voeu_id IN ({placeholders})', voeu_ids)
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} vœux supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500