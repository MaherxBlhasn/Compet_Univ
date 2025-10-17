import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db

salle_par_creneau_bp = Blueprint('salles_par_creneau', __name__)

@salle_par_creneau_bp.route('', methods=['GET'])
def get_all_salles():
    """GET /api/salles-par-creneau - Récupérer toutes les salles par créneau"""
    try:
        db = get_db()
        # Paramètres de filtrage optionnels
        id_session = request.args.get('id_session', type=int)
        dateExam = request.args.get('dateExam')
        
        query = '''
            SELECT spc.*, 
                   s.libelle_session, s.date_debut, s.date_fin
            FROM salle_par_creneau spc
            JOIN session s ON spc.id_session = s.id_session
        '''
        params = []
        
        # Ajouter des filtres si spécifiés
        conditions = []
        if id_session:
            conditions.append('spc.id_session = ?')
            params.append(id_session)
        if dateExam:
            conditions.append('spc.dateExam = ?')
            params.append(dateExam)
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY spc.dateExam, spc.h_debut'
        
        cursor = db.execute(query, params)
        salles = [dict(row) for row in cursor.fetchall()]
        return jsonify(salles), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/<int:id_session>/<dateExam>/<h_debut>', methods=['GET'])
def get_salle(id_session, dateExam, h_debut):
    """GET /api/salles-par-creneau/<id_session>/<dateExam>/<h_debut> - Récupérer une salle par créneau"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT spc.*, 
                   s.libelle_session, s.date_debut, s.date_fin
            FROM salle_par_creneau spc
            JOIN session s ON spc.id_session = s.id_session
            WHERE spc.id_session = ? AND spc.dateExam = ? AND spc.h_debut = ?
        ''', (id_session, dateExam, h_debut))
        salle = cursor.fetchone()
        
        if salle is None:
            return jsonify({'error': 'Salle par créneau non trouvée'}), 404
        return jsonify(dict(salle)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('', methods=['POST'])
def create_salle():
    """POST /api/salles-par-creneau - Créer une salle par créneau"""
    try:
        data = request.get_json()
        required = ['id_session', 'dateExam', 'h_debut', 'nb_salle']
        
        if not data or not all(k in data for k in required):
            return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        db.execute('''
            INSERT INTO salle_par_creneau (id_session, dateExam, h_debut, nb_salle)
            VALUES (?, ?, ?, ?)
        ''', (data['id_session'], data['dateExam'], data['h_debut'], data['nb_salle']))
        db.commit()
        
        return jsonify({
            'message': 'Salle par créneau créée avec succès',
            'id_session': data['id_session'],
            'dateExam': data['dateExam'],
            'h_debut': data['h_debut']
        }), 201
    except sqlite3.IntegrityError as e:
        if 'PRIMARY KEY' in str(e) or 'UNIQUE' in str(e):
            return jsonify({'error': 'Une salle existe déjà pour ce créneau'}), 409
        if 'FOREIGN KEY' in str(e):
            return jsonify({'error': 'Session invalide'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/<int:id_session>/<dateExam>/<h_debut>', methods=['PUT'])
def update_salle(id_session, dateExam, h_debut):
    """PUT /api/salles-par-creneau/<id_session>/<dateExam>/<h_debut> - Modifier une salle par créneau"""
    try:
        data = request.get_json()
        if not data or 'nb_salle' not in data:
            return jsonify({'error': 'nb_salle requis'}), 400
        
        db = get_db()
        cursor = db.execute('''
            UPDATE salle_par_creneau 
            SET nb_salle = ?
            WHERE id_session = ? AND dateExam = ? AND h_debut = ?
        ''', (data['nb_salle'], id_session, dateExam, h_debut))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Salle par créneau non trouvée'}), 404
        return jsonify({'message': 'Salle par créneau modifiée avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/<int:id_session>/<dateExam>/<h_debut>', methods=['DELETE'])
def delete_salle(id_session, dateExam, h_debut):
    """DELETE /api/salles-par-creneau/<id_session>/<dateExam>/<h_debut> - Supprimer une salle par créneau"""
    try:
        db = get_db()
        cursor = db.execute('''
            DELETE FROM salle_par_creneau 
            WHERE id_session = ? AND dateExam = ? AND h_debut = ?
        ''', (id_session, dateExam, h_debut))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Salle par créneau non trouvée'}), 404
        return jsonify({'message': 'Salle par créneau supprimée avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/all', methods=['DELETE'])
def delete_all_salles():
    """DELETE /api/salles-par-creneau/all - Supprimer toutes les salles par créneau"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM salle_par_creneau')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} salles par créneau supprimées avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/session/<int:id_session>', methods=['GET'])
def get_salles_by_session(id_session):
    """GET /api/salles-par-creneau/session/<id> - Récupérer toutes les salles d'une session"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT spc.*, 
                   s.libelle_session, s.date_debut, s.date_fin
            FROM salle_par_creneau spc
            JOIN session s ON spc.id_session = s.id_session
            WHERE spc.id_session = ?
            ORDER BY spc.dateExam, spc.h_debut
        ''', (id_session,))
        salles = [dict(row) for row in cursor.fetchall()]
        return jsonify(salles), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/session/<int:id_session>', methods=['DELETE'])
def delete_salles_by_session(id_session):
    """DELETE /api/salles-par-creneau/session/<id> - Supprimer toutes les salles d'une session"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM salle_par_creneau WHERE id_session = ?', (id_session,))
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} salles par créneau supprimées avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/date/<dateExam>', methods=['GET'])
def get_salles_by_date(dateExam):
    """GET /api/salles-par-creneau/date/<dateExam> - Récupérer toutes les salles pour une date"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT spc.*, 
                   s.libelle_session, s.date_debut, s.date_fin
            FROM salle_par_creneau spc
            JOIN session s ON spc.id_session = s.id_session
            WHERE spc.dateExam = ?
            ORDER BY spc.h_debut, spc.id_session
        ''', (dateExam,))
        salles = [dict(row) for row in cursor.fetchall()]
        return jsonify(salles), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/date/<dateExam>', methods=['DELETE'])
def delete_salles_by_date(dateExam):
    """DELETE /api/salles-par-creneau/date/<dateExam> - Supprimer toutes les salles pour une date"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM salle_par_creneau WHERE dateExam = ?', (dateExam,))
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} salles par créneau supprimées avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/batch', methods=['POST'])
def create_salles_batch():
    """POST /api/salles-par-creneau/batch - Créer plusieurs salles par créneau en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'salles' not in data:
            return jsonify({'error': 'Liste de salles requise'}), 400
        
        salles_list = data['salles']
        required = ['id_session', 'dateExam', 'h_debut', 'nb_salle']
        
        # Valider toutes les salles
        for salle in salles_list:
            if not all(k in salle for k in required):
                return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        created = []
        errors = []
        
        for salle in salles_list:
            try:
                db.execute('''
                    INSERT INTO salle_par_creneau (id_session, dateExam, h_debut, nb_salle)
                    VALUES (?, ?, ?, ?)
                ''', (salle['id_session'], salle['dateExam'], salle['h_debut'], salle['nb_salle']))
                created.append({
                    'id_session': salle['id_session'],
                    'dateExam': salle['dateExam'],
                    'h_debut': salle['h_debut']
                })
            except sqlite3.IntegrityError as e:
                if 'PRIMARY KEY' in str(e) or 'UNIQUE' in str(e):
                    errors.append({
                        'salle': salle,
                        'error': 'Une salle existe déjà pour ce créneau'
                    })
                else:
                    errors.append({
                        'salle': salle,
                        'error': 'Session invalide'
                    })
            except Exception as e:
                errors.append({
                    'salle': salle,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(created)} salles par créneau créées avec succès',
            'created': created,
            'errors': errors
        }), 201 if created else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/batch', methods=['PUT'])
def update_salles_batch():
    """PUT /api/salles-par-creneau/batch - Modifier plusieurs salles par créneau en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'salles' not in data:
            return jsonify({'error': 'Liste de salles requise'}), 400
        
        salles_list = data['salles']
        required = ['id_session', 'dateExam', 'h_debut', 'nb_salle']
        
        db = get_db()
        updated = []
        errors = []
        
        for salle in salles_list:
            if not all(k in salle for k in required):
                errors.append({
                    'salle': salle,
                    'error': f'Champs requis: {", ".join(required)}'
                })
                continue
            
            try:
                cursor = db.execute('''
                    UPDATE salle_par_creneau 
                    SET nb_salle = ?
                    WHERE id_session = ? AND dateExam = ? AND h_debut = ?
                ''', (salle['nb_salle'], salle['id_session'], salle['dateExam'], salle['h_debut']))
                
                if cursor.rowcount > 0:
                    updated.append({
                        'id_session': salle['id_session'],
                        'dateExam': salle['dateExam'],
                        'h_debut': salle['h_debut']
                    })
                else:
                    errors.append({
                        'salle': salle,
                        'error': 'Salle par créneau non trouvée'
                    })
            except Exception as e:
                errors.append({
                    'salle': salle,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(updated)} salles par créneau modifiées avec succès',
            'updated': updated,
            'errors': errors
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/batch', methods=['DELETE'])
def delete_salles_batch():
    """DELETE /api/salles-par-creneau/batch - Supprimer plusieurs salles par leurs clés"""
    try:
        data = request.get_json()
        
        if not data or 'salles' not in data:
            return jsonify({'error': 'Liste de salles requise (avec id_session, dateExam, h_debut)'}), 400
        
        salles_list = data['salles']
        required = ['id_session', 'dateExam', 'h_debut']
        
        db = get_db()
        deleted_count = 0
        errors = []
        
        for salle in salles_list:
            if not all(k in salle for k in required):
                errors.append({
                    'salle': salle,
                    'error': f'Champs requis: {", ".join(required)}'
                })
                continue
            
            try:
                cursor = db.execute('''
                    DELETE FROM salle_par_creneau 
                    WHERE id_session = ? AND dateExam = ? AND h_debut = ?
                ''', (salle['id_session'], salle['dateExam'], salle['h_debut']))
                deleted_count += cursor.rowcount
            except Exception as e:
                errors.append({
                    'salle': salle,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{deleted_count} salles par créneau supprimées avec succès',
            'count': deleted_count,
            'errors': errors
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/statistiques/session/<int:id_session>', methods=['GET'])
def get_statistiques_session(id_session):
    """GET /api/salles-par-creneau/statistiques/session/<id> - Statistiques des salles d'une session"""
    try:
        db = get_db()
        
        # Statistiques générales
        cursor = db.execute('''
            SELECT 
                COUNT(*) as total_creneaux,
                SUM(nb_salle) as total_salles,
                AVG(nb_salle) as avg_salles_par_creneau,
                MAX(nb_salle) as max_salles,
                MIN(nb_salle) as min_salles
            FROM salle_par_creneau
            WHERE id_session = ?
        ''', (id_session,))
        stats = dict(cursor.fetchone())
        
        # Statistiques par date
        cursor = db.execute('''
            SELECT 
                dateExam,
                COUNT(*) as nb_creneaux,
                SUM(nb_salle) as total_salles
            FROM salle_par_creneau
            WHERE id_session = ?
            GROUP BY dateExam
            ORDER BY dateExam
        ''', (id_session,))
        stats['par_date'] = [dict(row) for row in cursor.fetchall()]
        
        # Créneaux avec le plus de salles
        cursor = db.execute('''
            SELECT 
                dateExam, h_debut, nb_salle
            FROM salle_par_creneau
            WHERE id_session = ?
            ORDER BY nb_salle DESC
            LIMIT 10
        ''', (id_session,))
        stats['top_creneaux'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@salle_par_creneau_bp.route('/statistiques/date/<dateExam>', methods=['GET'])
def get_statistiques_date(dateExam):
    """GET /api/salles-par-creneau/statistiques/date/<dateExam> - Statistiques des salles pour une date"""
    try:
        db = get_db()
        
        # Statistiques pour la date
        cursor = db.execute('''
            SELECT 
                COUNT(*) as total_creneaux,
                SUM(nb_salle) as total_salles,
                AVG(nb_salle) as avg_salles_par_creneau,
                MAX(nb_salle) as max_salles,
                MIN(nb_salle) as min_salles
            FROM salle_par_creneau
            WHERE dateExam = ?
        ''', (dateExam,))
        stats = dict(cursor.fetchone())
        
        # Détails par créneau
        cursor = db.execute('''
            SELECT 
                spc.h_debut, spc.nb_salle, spc.id_session,
                s.libelle_session
            FROM salle_par_creneau spc
            JOIN session s ON spc.id_session = s.id_session
            WHERE spc.dateExam = ?
            ORDER BY spc.h_debut
        ''', (dateExam,))
        stats['creneaux'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
