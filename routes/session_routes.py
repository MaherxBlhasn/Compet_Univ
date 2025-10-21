import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db

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
    """
    POST /api/sessions - Créer une session
    
    Les dates (date_debut et date_fin) seront automatiquement calculées
    lors de l'import des créneaux :
    - date_debut = première date des créneaux (min de dateExam)
    - date_fin = dernière date des créneaux (max de dateExam)
    """
    try:
        data = request.get_json()
        if not data or 'libelle_session' not in data:
            return jsonify({'error': 'libelle_session requis'}), 400
        
        db = get_db()
        cursor = db.execute('''
            INSERT INTO session (libelle_session, date_debut, date_fin, AU, Semestre, type_session)
            VALUES (?, NULL, NULL, ?, ?, ?)
        ''', (data['libelle_session'], 
              data.get('AU'),
              data.get('Semestre'),
              data.get('type_session')))
        db.commit()
        return jsonify({
            'message': 'Session créée avec succès. Les dates seront calculées automatiquement lors de l\'import des créneaux.',
            'id_session': cursor.lastrowid
        }), 201
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
                date_fin = COALESCE(?, date_fin),
                AU = COALESCE(?, AU),
                Semestre = COALESCE(?, Semestre),
                type_session = COALESCE(?, type_session)
            WHERE id_session = ?
        ''', (data.get('libelle_session'),
              data.get('date_debut'),
              data.get('date_fin'),
              data.get('AU'),
              data.get('Semestre'),
              data.get('type_session'),
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

@session_bp.route('/max-jours', methods=['GET'])
def get_max_jours_per_session():
    """GET /api/sessions/max-jours - Récupérer le nombre maximum de jours pour chaque session"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT 
                s.id_session,
                s.libelle_session,
                s.date_debut,
                s.date_fin,
                COALESCE(MAX(js.jour_num), 0) as max_jour
            FROM session s
            LEFT JOIN jour_seance js ON s.id_session = js.id_session
            GROUP BY s.id_session, s.libelle_session, s.date_debut, s.date_fin
            ORDER BY s.date_debut DESC
        ''')
        sessions_max_jours = [dict(row) for row in cursor.fetchall()]
        return jsonify(sessions_max_jours), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@session_bp.route('/<int:id_session>/max-jours', methods=['GET'])
def get_max_jours_for_session(id_session):
    """GET /api/sessions/<id>/max-jours - Récupérer le nombre maximum de jours pour une session spécifique"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT 
                s.id_session,
                s.libelle_session,
                s.date_debut,
                s.date_fin,
                COALESCE(MAX(js.jour_num), 0) as max_jour
            FROM session s
            LEFT JOIN jour_seance js ON s.id_session = js.id_session
            WHERE s.id_session = ?
            GROUP BY s.id_session, s.libelle_session, s.date_debut, s.date_fin
        ''', (id_session,))
        session_max_jour = cursor.fetchone()
        
        if session_max_jour is None:
            return jsonify({'error': 'Session non trouvée'}), 404
        return jsonify(dict(session_max_jour)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@session_bp.route('/all', methods=['DELETE'])
def delete_all_sessions():
    """DELETE /api/sessions/all - Supprimer toutes les sessions"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM session')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} sessions supprimées avec succès',
            'count': cursor.rowcount
        }), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: certaines sessions ont des créneaux/vœux'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@session_bp.route('/batch', methods=['POST'])
def create_sessions_batch():
    """POST /api/sessions/batch - Créer plusieurs sessions en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'sessions' not in data:
            return jsonify({'error': 'Liste de sessions requise'}), 400
        
        sessions_list = data['sessions']
        
        # Valider toutes les sessions
        for session in sessions_list:
            if 'libelle_session' not in session:
                return jsonify({'error': 'libelle_session requis pour chaque session'}), 400
        
        db = get_db()
        created_ids = []
        errors = []
        
        for session in sessions_list:
            try:
                cursor = db.execute('''
                    INSERT INTO session (libelle_session, date_debut, date_fin, AU, Semestre, type_session)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (session['libelle_session'], 
                      session.get('date_debut'), 
                      session.get('date_fin'),
                      session.get('AU'),
                      session.get('Semestre'),
                      session.get('type_session')))
                created_ids.append(cursor.lastrowid)
            except sqlite3.IntegrityError:
                errors.append({
                    'session': session,
                    'error': 'Une session avec ce libellé existe déjà'
                })
            except Exception as e:
                errors.append({
                    'session': session,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(created_ids)} sessions créées avec succès',
            'created_ids': created_ids,
            'errors': errors
        }), 201 if created_ids else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@session_bp.route('/batch', methods=['PUT'])
def update_sessions_batch():
    """PUT /api/sessions/batch - Modifier plusieurs sessions en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'sessions' not in data:
            return jsonify({'error': 'Liste de sessions requise'}), 400
        
        sessions_list = data['sessions']
        
        db = get_db()
        updated = []
        errors = []
        
        for session in sessions_list:
            if 'id_session' not in session:
                errors.append({
                    'session': session,
                    'error': 'id_session requis'
                })
                continue
            
            try:
                cursor = db.execute('''
                    UPDATE session 
                    SET libelle_session = COALESCE(?, libelle_session),
                        date_debut = COALESCE(?, date_debut),
                        date_fin = COALESCE(?, date_fin),
                        AU = COALESCE(?, AU),
                        Semestre = COALESCE(?, Semestre),
                        type_session = COALESCE(?, type_session)
                    WHERE id_session = ?
                ''', (session.get('libelle_session'),
                      session.get('date_debut'),
                      session.get('date_fin'),
                      session.get('AU'),
                      session.get('Semestre'),
                      session.get('type_session'),
                      session['id_session']))
                
                if cursor.rowcount > 0:
                    updated.append(session['id_session'])
                else:
                    errors.append({
                        'session': session,
                        'error': 'Session non trouvée'
                    })
            except Exception as e:
                errors.append({
                    'session': session,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(updated)} sessions modifiées avec succès',
            'updated': updated,
            'errors': errors
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500




@session_bp.route('/<int:id_session>/check-data', methods=['GET'])
def check_session_data(id_session):
    """GET /api/sessions/<id>/check-data - Vérifier si la session a des enseignants, vœux et créneaux"""
    try:
        db = get_db()
        
        # Vérifier si la session existe
        cursor = db.execute('SELECT * FROM session WHERE id_session = ?', (id_session,))
        session = cursor.fetchone()
        
        if session is None:
            return jsonify({'error': 'Session non trouvée'}), 404
        
        # Vérifier s'il y a des enseignants (participants)
        cursor = db.execute('''
            SELECT COUNT(*) as count 
            FROM enseignant 
            WHERE participe_surveillance = 1
        ''')
        enseignants_count = cursor.fetchone()['count']
        has_enseignants = enseignants_count > 0
        
        # Vérifier s'il y a des vœux pour cette session
        cursor = db.execute('''
            SELECT COUNT(*) as count 
            FROM voeu 
            WHERE id_session = ?
        ''', (id_session,))
        voeux_count = cursor.fetchone()['count']
        has_voeux = voeux_count > 0
        
        # Vérifier s'il y a des créneaux pour cette session
        cursor = db.execute('''
            SELECT COUNT(*) as count 
            FROM creneau 
            WHERE id_session = ?
        ''', (id_session,))
        creneaux_count = cursor.fetchone()['count']
        has_creneaux = creneaux_count > 0
        
        # Déterminer si toutes les données sont présentes
        all_data_present = has_enseignants and has_voeux and has_creneaux
        
        return jsonify({
            'id_session': id_session,
            'libelle_session': session['libelle_session'],
            'has_enseignants': has_enseignants,
            'has_voeux': has_voeux,
            'has_creneaux': has_creneaux,
            'all_data_present': all_data_present,
            'status': 'yes' if all_data_present else 'no',
            'details': {
                'enseignants_count': enseignants_count,
                'voeux_count': voeux_count,
                'creneaux_count': creneaux_count
            }
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500




