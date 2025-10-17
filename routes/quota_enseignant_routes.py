import sqlite3
from flask import Blueprint, jsonify, request
from database import get_db

quota_enseignant_bp = Blueprint('quota_enseignants', __name__)

@quota_enseignant_bp.route('', methods=['GET'])
def get_all_quotas():
    """GET /api/quota-enseignants - Récupérer tous les quotas d'enseignants"""
    try:
        db = get_db()
        # Paramètres de filtrage optionnels
        code_smartex_ens = request.args.get('code_smartex_ens', type=int)
        id_session = request.args.get('id_session', type=int)
        
        query = '''
            SELECT q.*, 
                   e.nom_ens, e.prenom_ens, e.email_ens,
                   s.libelle_session, s.date_debut, s.date_fin,
                   g.quota as quota_grade_reference
            FROM quota_enseignant q
            JOIN enseignant e ON q.code_smartex_ens = e.code_smartex_ens
            JOIN session s ON q.id_session = s.id_session
            LEFT JOIN grade g ON q.grade_code_ens = g.code_grade
        '''
        params = []
        
        # Ajouter des filtres si spécifiés
        conditions = []
        if code_smartex_ens:
            conditions.append('q.code_smartex_ens = ?')
            params.append(code_smartex_ens)
        if id_session:
            conditions.append('q.id_session = ?')
            params.append(id_session)
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY s.date_debut DESC, e.nom_ens, e.prenom_ens'
        
        cursor = db.execute(query, params)
        quotas = [dict(row) for row in cursor.fetchall()]
        return jsonify(quotas), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/<int:quota_id>', methods=['GET'])
def get_quota(quota_id):
    """GET /api/quota-enseignants/<id> - Récupérer un quota d'enseignant"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT q.*, 
                   e.nom_ens, e.prenom_ens, e.email_ens,
                   s.libelle_session, s.date_debut, s.date_fin,
                   g.quota as quota_grade_reference
            FROM quota_enseignant q
            JOIN enseignant e ON q.code_smartex_ens = e.code_smartex_ens
            JOIN session s ON q.id_session = s.id_session
            LEFT JOIN grade g ON q.grade_code_ens = g.code_grade
            WHERE q.id = ?
        ''', (quota_id,))
        quota = cursor.fetchone()
        
        if quota is None:
            return jsonify({'error': 'Quota non trouvé'}), 404
        return jsonify(dict(quota)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/enseignant/<int:code_smartex_ens>/session/<int:id_session>', methods=['GET'])
def get_quota_by_enseignant_session(code_smartex_ens, id_session):
    """GET /api/quota-enseignants/enseignant/<code>/session/<id> - Récupérer le quota d'un enseignant pour une session"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT q.*, 
                   e.nom_ens, e.prenom_ens, e.email_ens,
                   s.libelle_session, s.date_debut, s.date_fin,
                   g.quota as quota_grade_reference
            FROM quota_enseignant q
            JOIN enseignant e ON q.code_smartex_ens = e.code_smartex_ens
            JOIN session s ON q.id_session = s.id_session
            LEFT JOIN grade g ON q.grade_code_ens = g.code_grade
            WHERE q.code_smartex_ens = ? AND q.id_session = ?
        ''', (code_smartex_ens, id_session))
        quota = cursor.fetchone()
        
        if quota is None:
            return jsonify({'error': 'Quota non trouvé'}), 404
        return jsonify(dict(quota)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('', methods=['POST'])
def create_quota():
    """POST /api/quota-enseignants - Créer un quota d'enseignant"""
    try:
        data = request.get_json()
        required = ['code_smartex_ens', 'id_session', 'grade_code_ens', 
                   'quota_grade', 'quota_realise', 'quota_majoritaire']
        
        if not data or not all(k in data for k in required):
            return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        # Calculer les différences
        diff_quota_grade = data['quota_realise'] - data['quota_grade']
        diff_quota_majoritaire = data['quota_realise'] - data['quota_majoritaire']
        
        # Calculer les quotas ajustés
        quota_ajuste = data['quota_grade'] - diff_quota_grade
        quota_ajuste_maj = data['quota_grade'] - diff_quota_majoritaire
        
        db = get_db()
        cursor = db.execute('''
            INSERT INTO quota_enseignant 
            (code_smartex_ens, id_session, grade_code_ens, quota_grade, 
             quota_realise, quota_majoritaire, diff_quota_grade, 
             diff_quota_majoritaire, quota_ajuste, quota_ajuste_maj)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['code_smartex_ens'], data['id_session'], data['grade_code_ens'],
              data['quota_grade'], data['quota_realise'], data['quota_majoritaire'],
              diff_quota_grade, diff_quota_majoritaire, data.get('quota_ajuste', quota_ajuste), 
              data.get('quota_ajuste_maj', quota_ajuste_maj)))
        db.commit()
        
        return jsonify({
            'message': 'Quota créé avec succès',
            'id': cursor.lastrowid
        }), 201
    except sqlite3.IntegrityError as e:
        if 'UNIQUE' in str(e):
            return jsonify({'error': 'Un quota existe déjà pour cet enseignant et cette session'}), 409
        if 'FOREIGN KEY' in str(e):
            return jsonify({'error': 'Enseignant ou session invalide'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/<int:quota_id>', methods=['PUT'])
def update_quota(quota_id):
    """PUT /api/quota-enseignants/<id> - Modifier un quota d'enseignant"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        db = get_db()
        
        # Récupérer les valeurs actuelles pour calculer les différences
        cursor = db.execute('SELECT * FROM quota_enseignant WHERE id = ?', (quota_id,))
        current = cursor.fetchone()
        
        if not current:
            return jsonify({'error': 'Quota non trouvé'}), 404
        
        # Utiliser les valeurs actuelles ou les nouvelles
        quota_grade = data.get('quota_grade', current['quota_grade'])
        quota_realise = data.get('quota_realise', current['quota_realise'])
        quota_majoritaire = data.get('quota_majoritaire', current['quota_majoritaire'])
        
        # Recalculer les différences
        diff_quota_grade = quota_realise - quota_grade
        diff_quota_majoritaire = quota_realise - quota_majoritaire
        
        # Calculer les quotas ajustés
        quota_ajuste = quota_grade - diff_quota_grade
        quota_ajuste_maj = quota_grade - diff_quota_majoritaire
        
        cursor = db.execute('''
            UPDATE quota_enseignant 
            SET code_smartex_ens = COALESCE(?, code_smartex_ens),
                id_session = COALESCE(?, id_session),
                grade_code_ens = COALESCE(?, grade_code_ens),
                quota_grade = ?,
                quota_realise = ?,
                quota_majoritaire = ?,
                diff_quota_grade = ?,
                diff_quota_majoritaire = ?,
                quota_ajuste = COALESCE(?, quota_ajuste),
                quota_ajuste_maj = COALESCE(?, quota_ajuste_maj)
            WHERE id = ?
        ''', (data.get('code_smartex_ens'), data.get('id_session'), 
              data.get('grade_code_ens'), quota_grade, quota_realise,
              quota_majoritaire, diff_quota_grade, diff_quota_majoritaire,
              data.get('quota_ajuste', quota_ajuste), data.get('quota_ajuste_maj', quota_ajuste_maj), quota_id))
        db.commit()
        
        return jsonify({'message': 'Quota modifié avec succès'}), 200
    except sqlite3.IntegrityError as e:
        if 'UNIQUE' in str(e):
            return jsonify({'error': 'Un quota existe déjà pour cet enseignant et cette session'}), 409
        if 'FOREIGN KEY' in str(e):
            return jsonify({'error': 'Enseignant ou session invalide'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/<int:quota_id>', methods=['DELETE'])
def delete_quota(quota_id):
    """DELETE /api/quota-enseignants/<id> - Supprimer un quota d'enseignant"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM quota_enseignant WHERE id = ?', (quota_id,))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Quota non trouvé'}), 404
        return jsonify({'message': 'Quota supprimé avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/all', methods=['DELETE'])
def delete_all_quotas():
    """DELETE /api/quota-enseignants/all - Supprimer tous les quotas"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM quota_enseignant')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} quotas supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/session/<int:id_session>', methods=['GET'])
def get_quotas_by_session(id_session):
    """GET /api/quota-enseignants/session/<id> - Récupérer tous les quotas d'une session"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT q.*, 
                   e.nom_ens, e.prenom_ens, e.email_ens,
                   s.libelle_session, s.date_debut, s.date_fin,
                   g.quota as quota_grade_reference
            FROM quota_enseignant q
            JOIN enseignant e ON q.code_smartex_ens = e.code_smartex_ens
            JOIN session s ON q.id_session = s.id_session
            LEFT JOIN grade g ON q.grade_code_ens = g.code_grade
            WHERE q.id_session = ?
            ORDER BY e.nom_ens, e.prenom_ens
        ''', (id_session,))
        quotas = [dict(row) for row in cursor.fetchall()]
        return jsonify(quotas), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/session/<int:id_session>', methods=['DELETE'])
def delete_quotas_by_session(id_session):
    """DELETE /api/quota-enseignants/session/<id> - Supprimer tous les quotas d'une session"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM quota_enseignant WHERE id_session = ?', (id_session,))
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} quotas supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/enseignant/<int:code_smartex_ens>', methods=['GET'])
def get_quotas_by_enseignant(code_smartex_ens):
    """GET /api/quota-enseignants/enseignant/<code> - Récupérer tous les quotas d'un enseignant"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT q.*, 
                   e.nom_ens, e.prenom_ens, e.email_ens,
                   s.libelle_session, s.date_debut, s.date_fin,
                   g.quota as quota_grade_reference
            FROM quota_enseignant q
            JOIN enseignant e ON q.code_smartex_ens = e.code_smartex_ens
            JOIN session s ON q.id_session = s.id_session
            LEFT JOIN grade g ON q.grade_code_ens = g.code_grade
            WHERE q.code_smartex_ens = ?
            ORDER BY s.date_debut DESC
        ''', (code_smartex_ens,))
        quotas = [dict(row) for row in cursor.fetchall()]
        return jsonify(quotas), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/enseignant/<int:code_smartex_ens>', methods=['DELETE'])
def delete_quotas_by_enseignant(code_smartex_ens):
    """DELETE /api/quota-enseignants/enseignant/<code> - Supprimer tous les quotas d'un enseignant"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM quota_enseignant WHERE code_smartex_ens = ?', (code_smartex_ens,))
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} quotas supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/batch', methods=['POST'])
def create_quotas_batch():
    """POST /api/quota-enseignants/batch - Créer plusieurs quotas en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'quotas' not in data:
            return jsonify({'error': 'Liste de quotas requise'}), 400
        
        quotas_list = data['quotas']
        required = ['code_smartex_ens', 'id_session', 'grade_code_ens', 
                   'quota_grade', 'quota_realise', 'quota_majoritaire']
        
        # Valider tous les quotas
        for quota in quotas_list:
            if not all(k in quota for k in required):
                return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        created_ids = []
        errors = []
        
        for quota in quotas_list:
            try:
                # Calculer les différences
                diff_quota_grade = quota['quota_realise'] - quota['quota_grade']
                diff_quota_majoritaire = quota['quota_realise'] - quota['quota_majoritaire']
                
                # Calculer les quotas ajustés
                quota_ajuste = quota['quota_grade'] - diff_quota_grade
                quota_ajuste_maj = quota['quota_grade'] - diff_quota_majoritaire
                
                cursor = db.execute('''
                    INSERT INTO quota_enseignant 
                    (code_smartex_ens, id_session, grade_code_ens, quota_grade, 
                     quota_realise, quota_majoritaire, diff_quota_grade, 
                     diff_quota_majoritaire, quota_ajuste, quota_ajuste_maj)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (quota['code_smartex_ens'], quota['id_session'], quota['grade_code_ens'],
                      quota['quota_grade'], quota['quota_realise'], quota['quota_majoritaire'],
                      diff_quota_grade, diff_quota_majoritaire, quota.get('quota_ajuste', quota_ajuste),
                      quota.get('quota_ajuste_maj', quota_ajuste_maj)))
                created_ids.append(cursor.lastrowid)
            except sqlite3.IntegrityError as e:
                if 'UNIQUE' in str(e):
                    errors.append({
                        'quota': quota,
                        'error': 'Un quota existe déjà pour cet enseignant et cette session'
                    })
                else:
                    errors.append({
                        'quota': quota,
                        'error': 'Enseignant ou session invalide'
                    })
            except Exception as e:
                errors.append({
                    'quota': quota,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(created_ids)} quotas créés avec succès',
            'created_ids': created_ids,
            'errors': errors
        }), 201 if created_ids else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/batch', methods=['PUT'])
def update_quotas_batch():
    """PUT /api/quota-enseignants/batch - Modifier plusieurs quotas en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'quotas' not in data:
            return jsonify({'error': 'Liste de quotas requise'}), 400
        
        quotas_list = data['quotas']
        
        db = get_db()
        updated = []
        errors = []
        
        for quota in quotas_list:
            if 'id' not in quota:
                errors.append({
                    'quota': quota,
                    'error': 'id requis'
                })
                continue
            
            try:
                # Récupérer les valeurs actuelles
                cursor = db.execute('SELECT * FROM quota_enseignant WHERE id = ?', (quota['id'],))
                current = cursor.fetchone()
                
                if not current:
                    errors.append({
                        'quota': quota,
                        'error': 'Quota non trouvé'
                    })
                    continue
                
                # Utiliser les valeurs actuelles ou les nouvelles
                quota_grade = quota.get('quota_grade', current['quota_grade'])
                quota_realise = quota.get('quota_realise', current['quota_realise'])
                quota_majoritaire = quota.get('quota_majoritaire', current['quota_majoritaire'])
                
                # Recalculer les différences
                diff_quota_grade = quota_realise - quota_grade
                diff_quota_majoritaire = quota_realise - quota_majoritaire
                
                # Calculer les quotas ajustés
                quota_ajuste = quota_grade - diff_quota_grade
                quota_ajuste_maj = quota_grade - diff_quota_majoritaire
                
                cursor = db.execute('''
                    UPDATE quota_enseignant 
                    SET code_smartex_ens = COALESCE(?, code_smartex_ens),
                        id_session = COALESCE(?, id_session),
                        grade_code_ens = COALESCE(?, grade_code_ens),
                        quota_grade = ?,
                        quota_realise = ?,
                        quota_majoritaire = ?,
                        diff_quota_grade = ?,
                        diff_quota_majoritaire = ?,
                        quota_ajuste = COALESCE(?, quota_ajuste),
                        quota_ajuste_maj = COALESCE(?, quota_ajuste_maj)
                    WHERE id = ?
                ''', (quota.get('code_smartex_ens'), quota.get('id_session'), 
                      quota.get('grade_code_ens'), quota_grade, quota_realise,
                      quota_majoritaire, diff_quota_grade, diff_quota_majoritaire,
                      quota.get('quota_ajuste', quota_ajuste), quota.get('quota_ajuste_maj', quota_ajuste_maj), quota['id']))
                
                updated.append(quota['id'])
            except Exception as e:
                errors.append({
                    'quota': quota,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(updated)} quotas modifiés avec succès',
            'updated': updated,
            'errors': errors
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/batch', methods=['DELETE'])
def delete_quotas_batch():
    """DELETE /api/quota-enseignants/batch - Supprimer plusieurs quotas par leurs IDs"""
    try:
        data = request.get_json()
        
        if not data or 'quota_ids' not in data:
            return jsonify({'error': 'Liste d\'IDs de quotas requise'}), 400
        
        quota_ids = data['quota_ids']
        
        if not isinstance(quota_ids, list) or len(quota_ids) == 0:
            return jsonify({'error': 'La liste d\'IDs doit être non vide'}), 400
        
        db = get_db()
        placeholders = ','.join(['?' for _ in quota_ids])
        cursor = db.execute(f'DELETE FROM quota_enseignant WHERE id IN ({placeholders})', quota_ids)
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} quotas supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@quota_enseignant_bp.route('/statistiques/session/<int:id_session>', methods=['GET'])
def get_statistiques_session(id_session):
    """GET /api/quota-enseignants/statistiques/session/<id> - Statistiques des quotas d'une session"""
    try:
        db = get_db()
        
        # Statistiques générales
        cursor = db.execute('''
            SELECT 
                COUNT(*) as total_enseignants,
                SUM(quota_grade) as total_quota_grade,
                SUM(quota_realise) as total_quota_realise,
                SUM(quota_majoritaire) as total_quota_majoritaire,
                AVG(diff_quota_grade) as avg_diff_quota_grade,
                AVG(diff_quota_majoritaire) as avg_diff_quota_majoritaire
            FROM quota_enseignant
            WHERE id_session = ?
        ''', (id_session,))
        stats = dict(cursor.fetchone())
        
        # Statistiques par grade
        cursor = db.execute('''
            SELECT 
                grade_code_ens,
                COUNT(*) as nb_enseignants,
                SUM(quota_grade) as total_quota_grade,
                SUM(quota_realise) as total_quota_realise,
                AVG(diff_quota_grade) as avg_diff_quota_grade
            FROM quota_enseignant
            WHERE id_session = ?
            GROUP BY grade_code_ens
        ''', (id_session,))
        stats['par_grade'] = [dict(row) for row in cursor.fetchall()]
        
        # Enseignants dépassant leur quota
        cursor = db.execute('''
            SELECT 
                e.code_smartex_ens, e.nom_ens, e.prenom_ens,
                q.quota_grade, q.quota_realise, q.diff_quota_grade
            FROM quota_enseignant q
            JOIN enseignant e ON q.code_smartex_ens = e.code_smartex_ens
            WHERE q.id_session = ? AND q.diff_quota_grade > 0
            ORDER BY q.diff_quota_grade DESC
        ''', (id_session,))
        stats['depassements'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
