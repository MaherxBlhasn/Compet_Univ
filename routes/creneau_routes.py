import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db
from utils.time_utils import parse_time

creneau_bp = Blueprint('creneaux', __name__)

@creneau_bp.route('', methods=['GET'])
def get_all_creneaux():
    """GET /api/creneaux - Récupérer tous les créneaux"""
    try:
        db = get_db()
        # Paramètres de filtrage optionnels
        id_session = request.args.get('id_session', type=int)
        date_exam = request.args.get('dateExam')
        
        query = '''
            SELECT c.*, 
                   s.libelle_session,
                   e.nom_ens, e.prenom_ens
            FROM creneau c
            LEFT JOIN session s ON c.id_session = s.id_session
            LEFT JOIN enseignant e ON c.enseignant = e.code_smartex_ens
        '''
        params = []
        
        # Ajouter des filtres si spécifiés
        conditions = []
        if id_session:
            conditions.append('c.id_session = ?')
            params.append(id_session)
        if date_exam:
            conditions.append('c.dateExam = ?')
            params.append(date_exam)
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY c.dateExam, c.h_debut'
        
        cursor = db.execute(query, params)
        creneaux = [dict(row) for row in cursor.fetchall()]
        return jsonify(creneaux), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('/<int:creneau_id>', methods=['GET'])
def get_creneau(creneau_id):
    """GET /api/creneaux/<id> - Récupérer un créneau avec ses affectations"""
    try:
        db = get_db()
        # Récupérer le créneau
        cursor = db.execute('''
            SELECT c.*, 
                   s.libelle_session,
                   e.nom_ens, e.prenom_ens
            FROM creneau c
            LEFT JOIN session s ON c.id_session = s.id_session
            LEFT JOIN enseignant e ON c.enseignant = e.code_smartex_ens
            WHERE c.creneau_id = ?
        ''', (creneau_id,))
        creneau = cursor.fetchone()
        
        if creneau is None:
            return jsonify({'error': 'Créneau non trouvé'}), 404
        
        creneau_dict = dict(creneau)
        
        # Récupérer les surveillants affectés
        cursor = db.execute('''
            SELECT a.code_smartex_ens, e.nom_ens, e.prenom_ens, 
                   e.grade_code_ens, g.quota
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
            WHERE a.creneau_id = ?
        ''', (creneau_id,))
        creneau_dict['surveillants'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(creneau_dict), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('', methods=['POST'])
def create_creneau():
    """
    POST /api/creneaux - Créer un créneau
    
    Mise à jour automatique des dates de session :
    - date_debut = min(date_debut_actuelle, dateExam)
    - date_fin = max(date_fin_actuelle, dateExam)
    """
    try:
        data = request.get_json()
        required = ['id_session', 'dateExam', 'h_debut', 'h_fin']
        
        if not data or not all(k in data for k in required):
            return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        # Normaliser les heures au format HH:MM
        h_debut_normalized = parse_time(data['h_debut'])
        h_fin_normalized = parse_time(data['h_fin'])
        
        if not h_debut_normalized or not h_fin_normalized:
            return jsonify({'error': 'Format d\'heure invalide (attendu: HH:MM)'}), 400
        
        db = get_db()
        cursor = db.execute('''
            INSERT INTO creneau (id_session, dateExam, h_debut, h_fin, 
                                type_ex, semestre, enseignant, cod_salle)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', (data['id_session'], data['dateExam'], h_debut_normalized, 
              h_fin_normalized, data.get('type_ex'), data.get('semestre'),
              data.get('enseignant'), data.get('cod_salle')))
        
        # Mettre à jour les dates de la session automatiquement
        try:
            id_session = data['id_session']
            date_exam = data['dateExam']
            
            # Récupérer les dates actuelles de la session
            session = db.execute(
                'SELECT date_debut, date_fin FROM session WHERE id_session = ?',
                (id_session,)
            ).fetchone()
            
            if session:
                date_debut_actuelle = session['date_debut']
                date_fin_actuelle = session['date_fin']
                
                # Calculer les nouvelles dates
                if date_debut_actuelle is None or date_exam < date_debut_actuelle:
                    nouvelle_date_debut = date_exam
                else:
                    nouvelle_date_debut = date_debut_actuelle
                
                if date_fin_actuelle is None or date_exam > date_fin_actuelle:
                    nouvelle_date_fin = date_exam
                else:
                    nouvelle_date_fin = date_fin_actuelle
                
                # Mettre à jour si nécessaire
                if (nouvelle_date_debut != date_debut_actuelle or 
                    nouvelle_date_fin != date_fin_actuelle):
                    db.execute('''
                        UPDATE session 
                        SET date_debut = ?, date_fin = ?
                        WHERE id_session = ?
                    ''', (nouvelle_date_debut, nouvelle_date_fin, id_session))
        except Exception as e:
            # Ne pas bloquer la création du créneau si la mise à jour échoue
            pass
        
        db.commit()
        
        return jsonify({
            'message': 'Créneau créé avec succès et dates de session mises à jour',
            'creneau_id': cursor.lastrowid
        }), 201
    except sqlite3.IntegrityError as e:
        if 'FOREIGN KEY' in str(e):
            return jsonify({'error': 'Session ou enseignant invalide'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('/<int:creneau_id>', methods=['PUT'])
def update_creneau(creneau_id):
    """PUT /api/creneaux/<id> - Modifier un créneau"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        # Normaliser les heures si elles sont fournies
        h_debut_normalized = parse_time(data['h_debut']) if 'h_debut' in data else None
        h_fin_normalized = parse_time(data['h_fin']) if 'h_fin' in data else None
        
        # Vérifier que les heures sont valides si fournies
        if 'h_debut' in data and not h_debut_normalized:
            return jsonify({'error': 'Format d\'heure de début invalide (attendu: HH:MM)'}), 400
        if 'h_fin' in data and not h_fin_normalized:
            return jsonify({'error': 'Format d\'heure de fin invalide (attendu: HH:MM)'}), 400
        
        db = get_db()
        cursor = db.execute('''
            UPDATE creneau 
            SET id_session = COALESCE(?, id_session),
                dateExam = COALESCE(?, dateExam),
                h_debut = COALESCE(?, h_debut),
                h_fin = COALESCE(?, h_fin),
                type_ex = COALESCE(?, type_ex),
                semestre = COALESCE(?, semestre),
                enseignant = COALESCE(?, enseignant),
                cod_salle = COALESCE(?, cod_salle)
            WHERE creneau_id = ?
        ''', (data.get('id_session'), data.get('dateExam'), 
              h_debut_normalized, h_fin_normalized,
              data.get('type_ex'), data.get('semestre'),
              data.get('enseignant'), data.get('cod_salle'),
              creneau_id))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Créneau non trouvé'}), 404
        return jsonify({'message': 'Créneau modifié avec succès'}), 200
    except sqlite3.IntegrityError as e:
        return jsonify({'error': 'Session ou enseignant invalide'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('/<int:creneau_id>', methods=['DELETE'])
def delete_creneau(creneau_id):
    """DELETE /api/creneaux/<id> - Supprimer un créneau"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM creneau WHERE creneau_id = ?', 
                           (creneau_id,))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Créneau non trouvé'}), 404
        return jsonify({'message': 'Créneau supprimé avec succès'}), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: des affectations sont liées à ce créneau'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('/all', methods=['DELETE'])
def delete_all_creneaux():
    """DELETE /api/creneaux/all - Supprimer tous les créneaux"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM creneau')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} créneaux supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: certains créneaux ont des affectations'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('/session/<int:id_session>', methods=['DELETE'])
def delete_creneaux_by_session(id_session):
    """DELETE /api/creneaux/session/<id> - Supprimer tous les créneaux d'une session"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM creneau WHERE id_session = ?', (id_session,))
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} créneaux supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: certains créneaux ont des affectations'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('/batch', methods=['POST'])
def create_creneaux_batch():
    """POST /api/creneaux/batch - Créer plusieurs créneaux en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'creneaux' not in data:
            return jsonify({'error': 'Liste de créneaux requise'}), 400
        
        creneaux_list = data['creneaux']
        required = ['id_session', 'dateExam', 'h_debut', 'h_fin']
        
        # Valider tous les créneaux
        for creneau in creneaux_list:
            if not all(k in creneau for k in required):
                return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        created_ids = []
        errors = []
        
        for creneau in creneaux_list:
            try:
                # Normaliser les heures au format HH:MM
                h_debut_normalized = parse_time(creneau['h_debut'])
                h_fin_normalized = parse_time(creneau['h_fin'])
                
                if not h_debut_normalized or not h_fin_normalized:
                    errors.append({
                        'creneau': creneau,
                        'error': 'Format d\'heure invalide (attendu: HH:MM)'
                    })
                    continue
                
                cursor = db.execute('''
                    INSERT INTO creneau (id_session, dateExam, h_debut, h_fin, 
                                        type_ex, semestre, enseignant, cod_salle)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (creneau['id_session'], creneau['dateExam'], h_debut_normalized, 
                      h_fin_normalized, creneau.get('type_ex'), creneau.get('semestre'),
                      creneau.get('enseignant'), creneau.get('cod_salle')))
                created_ids.append(cursor.lastrowid)
            except sqlite3.IntegrityError as e:
                errors.append({
                    'creneau': creneau,
                    'error': 'Session ou enseignant invalide'
                })
            except Exception as e:
                errors.append({
                    'creneau': creneau,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(created_ids)} créneaux créés avec succès',
            'created_ids': created_ids,
            'errors': errors
        }), 201 if created_ids else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('/batch', methods=['PUT'])
def update_creneaux_batch():
    """PUT /api/creneaux/batch - Modifier plusieurs créneaux en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'creneaux' not in data:
            return jsonify({'error': 'Liste de créneaux requise'}), 400
        
        creneaux_list = data['creneaux']
        
        db = get_db()
        updated = []
        errors = []
        
        for creneau in creneaux_list:
            if 'creneau_id' not in creneau:
                errors.append({
                    'creneau': creneau,
                    'error': 'creneau_id requis'
                })
                continue
            
            try:
                # Normaliser les heures si elles sont fournies
                h_debut_normalized = parse_time(creneau['h_debut']) if 'h_debut' in creneau else None
                h_fin_normalized = parse_time(creneau['h_fin']) if 'h_fin' in creneau else None
                
                # Vérifier que les heures sont valides si fournies
                if 'h_debut' in creneau and not h_debut_normalized:
                    errors.append({
                        'creneau': creneau,
                        'error': 'Format d\'heure de début invalide (attendu: HH:MM)'
                    })
                    continue
                if 'h_fin' in creneau and not h_fin_normalized:
                    errors.append({
                        'creneau': creneau,
                        'error': 'Format d\'heure de fin invalide (attendu: HH:MM)'
                    })
                    continue
                
                cursor = db.execute('''
                    UPDATE creneau 
                    SET id_session = COALESCE(?, id_session),
                        dateExam = COALESCE(?, dateExam),
                        h_debut = COALESCE(?, h_debut),
                        h_fin = COALESCE(?, h_fin),
                        type_ex = COALESCE(?, type_ex),
                        semestre = COALESCE(?, semestre),
                        enseignant = COALESCE(?, enseignant),
                        cod_salle = COALESCE(?, cod_salle)
                    WHERE creneau_id = ?
                ''', (creneau.get('id_session'), creneau.get('dateExam'), 
                      h_debut_normalized, h_fin_normalized,
                      creneau.get('type_ex'), creneau.get('semestre'),
                      creneau.get('enseignant'), creneau.get('cod_salle'),
                      creneau['creneau_id']))
                
                if cursor.rowcount > 0:
                    updated.append(creneau['creneau_id'])
                else:
                    errors.append({
                        'creneau': creneau,
                        'error': 'Créneau non trouvé'
                    })
            except Exception as e:
                errors.append({
                    'creneau': creneau,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(updated)} créneaux modifiés avec succès',
            'updated': updated,
            'errors': errors
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@creneau_bp.route('/session/<int:id_session>/statistiques', methods=['GET'])
def get_session_statistiques(id_session):
    """GET /api/creneaux/session/<id>/statistiques - Statistiques d'une session"""
    try:
        db = get_db()
        
        # Nombre total de créneaux
        cursor = db.execute('''
            SELECT COUNT(*) as total_creneaux,
                   COUNT(DISTINCT dateExam) as nb_jours
            FROM creneau
            WHERE id_session = ?
        ''', (id_session,))
        stats = dict(cursor.fetchone())
        
        # Nombre d'affectations
        cursor = db.execute('''
            SELECT COUNT(*) as total_affectations
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE c.id_session = ?
        ''', (id_session,))
        stats.update(dict(cursor.fetchone()))
        
        # Créneaux par date
        cursor = db.execute('''
            SELECT dateExam, COUNT(*) as nb_creneaux
            FROM creneau
            WHERE id_session = ?
            GROUP BY dateExam
            ORDER BY dateExam
        ''', (id_session,))
        stats['creneaux_par_jour'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500