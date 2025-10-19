import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db

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


@quota_enseignant_bp.route('/enseignant/<int:code_smartex_ens>', methods=['PUT'])
def update_quota_by_enseignant(code_smartex_ens):
    """PUT /api/quota-enseignants/enseignant/<code> - Modifier le quota d'un enseignant (pour toutes ses sessions)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        id_session = data.get('id_session')
        if not id_session:
            return jsonify({'error': 'id_session requis'}), 400
        
        db = get_db()
        
        # Récupérer les valeurs actuelles pour calculer les différences
        cursor = db.execute('''
            SELECT * FROM quota_enseignant 
            WHERE code_smartex_ens = ? AND id_session = ?
        ''', (code_smartex_ens, id_session))
        current = cursor.fetchone()
        
        if not current:
            return jsonify({'error': 'Quota non trouvé pour cet enseignant dans cette session'}), 404
        
        # Utiliser les valeurs actuelles ou les nouvelles
        quota_grade = data.get('quota_grade', current['quota_grade'])
        quota_realise = data.get('quota_realise', current['quota_realise'])
        quota_majoritaire = data.get('quota_majoritaire', current['quota_majoritaire'])
        
        # Recalculer les différences
        diff_quota_grade = quota_realise - quota_grade
        diff_quota_majoritaire = quota_realise - quota_majoritaire
        
        # Calculer les quotas ajustés
        quota_ajuste = data.get('quota_ajuste', quota_grade)
        quota_ajuste_maj = data.get('quota_ajuste_maj', quota_grade)
        
        cursor = db.execute('''
            UPDATE quota_enseignant 
            SET grade_code_ens = COALESCE(?, grade_code_ens),
                quota_grade = ?,
                quota_realise = ?,
                quota_majoritaire = ?,
                diff_quota_grade = ?,
                diff_quota_majoritaire = ?,
                quota_ajuste = ?,
                quota_ajuste_maj = ?
            WHERE code_smartex_ens = ? AND id_session = ?
        ''', (data.get('grade_code_ens'), quota_grade, quota_realise,
              quota_majoritaire, diff_quota_grade, diff_quota_majoritaire,
              quota_ajuste, quota_ajuste_maj, code_smartex_ens, id_session))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Aucune modification effectuée'}), 404
        
        return jsonify({'message': 'Quota modifié avec succès'}), 200
    except sqlite3.IntegrityError as e:
        if 'FOREIGN KEY' in str(e):
            return jsonify({'error': 'Enseignant ou session invalide'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@quota_enseignant_bp.route('/reset/session/<int:id_session>', methods=['PUT'])
def reset_quotas_by_session(id_session):
    """PUT /api/quota-enseignants/reset/session/<id> - Réinitialiser tous les quotas d'une session (différences = 0, quota_ajuste = quota_grade)"""
    try:
        db = get_db()
        cursor = db.execute('''
            UPDATE quota_enseignant 
            SET diff_quota_grade = 0,
                diff_quota_majoritaire = 0,
                quota_ajuste = quota_grade,
                quota_ajuste_maj = quota_grade
            WHERE id_session = ?
        ''', (id_session,))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Aucun quota trouvé pour cette session'}), 404
        
        return jsonify({
            'message': f'{cursor.rowcount} quotas réinitialisés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@quota_enseignant_bp.route('/reset/all', methods=['PUT'])
def reset_all_quotas():
    """PUT /api/quota-enseignants/reset/all - Réinitialiser tous les quotas (différences = 0, quota_ajuste = quota_grade)"""
    try:
        db = get_db()
        cursor = db.execute('''
            UPDATE quota_enseignant 
            SET diff_quota_grade = 0,
                diff_quota_majoritaire = 0,
                quota_ajuste = quota_grade,
                quota_ajuste_maj = quota_grade
        ''')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} quotas réinitialisés avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
