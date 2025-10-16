import sqlite3
from flask import Blueprint, jsonify, request
from database import get_db

affectation_bp = Blueprint('affectations', __name__)

@affectation_bp.route('', methods=['GET'])
def get_all_affectations():
    """GET /api/affectations - Récupérer toutes les affectations"""
    try:
        db = get_db()
        # Paramètres de filtrage optionnels
        code_smartex_ens = request.args.get('code_smartex_ens', type=int)
        creneau_id = request.args.get('creneau_id', type=int)
        id_session = request.args.get('id_session', type=int)
        
        query = '''
            SELECT a.*, 
                   e.nom_ens, e.prenom_ens, e.grade_code_ens,
                   c.dateExam, c.h_debut, c.h_fin, c.cod_salle, c.type_ex,
                   s.libelle_session,
                   g.quota
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            JOIN creneau c ON a.creneau_id = c.creneau_id
            JOIN session s ON c.id_session = s.id_session
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
        '''
        params = []
        
        # Ajouter des filtres si spécifiés
        conditions = []
        if code_smartex_ens:
            conditions.append('a.code_smartex_ens = ?')
            params.append(code_smartex_ens)
        if creneau_id:
            conditions.append('a.creneau_id = ?')
            params.append(creneau_id)
        if id_session:
            conditions.append('c.id_session = ?')
            params.append(id_session)
        
        if conditions:
            query += ' WHERE ' + ' AND '.join(conditions)
        
        query += ' ORDER BY c.dateExam, c.h_debut, e.nom_ens'
        
        cursor = db.execute(query, params)
        affectations = [dict(row) for row in cursor.fetchall()]
        return jsonify(affectations), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/<int:code_smartex_ens>/<int:creneau_id>', methods=['GET'])
def get_affectation(code_smartex_ens, creneau_id):
    """GET /api/affectations/<code_ens>/<creneau_id> - Récupérer une affectation"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT a.*, 
                   e.nom_ens, e.prenom_ens, e.grade_code_ens,
                   c.dateExam, c.h_debut, c.h_fin, c.cod_salle, c.type_ex,
                   s.libelle_session,
                   g.quota
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            JOIN creneau c ON a.creneau_id = c.creneau_id
            JOIN session s ON c.id_session = s.id_session
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
            WHERE a.code_smartex_ens = ? AND a.creneau_id = ?
        ''', (code_smartex_ens, creneau_id))
        affectation = cursor.fetchone()
        
        if affectation is None:
            return jsonify({'error': 'Affectation non trouvée'}), 404
        return jsonify(dict(affectation)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('', methods=['POST'])
def create_affectation():
    """POST /api/affectations - Créer une affectation"""
    try:
        data = request.get_json()
        required = ['code_smartex_ens', 'creneau_id']
        
        if not data or not all(k in data for k in required):
            return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        
        # Vérifier que l'enseignant participe à la surveillance
        cursor = db.execute('''
            SELECT participe_surveillance FROM enseignant 
            WHERE code_smartex_ens = ?
        ''', (data['code_smartex_ens'],))
        ens = cursor.fetchone()
        
        if not ens:
            return jsonify({'error': 'Enseignant non trouvé'}), 404
        if not ens['participe_surveillance']:
            return jsonify({'error': 'Cet enseignant ne participe pas à la surveillance'}), 400
        
        # Vérifier les conflits d'horaire
        cursor = db.execute('''
            SELECT COUNT(*) as count
            FROM affectation a1
            JOIN creneau c1 ON a1.creneau_id = c1.creneau_id
            JOIN creneau c2 ON c2.creneau_id = ?
            WHERE a1.code_smartex_ens = ?
            AND c1.dateExam = c2.dateExam
            AND (
                (c1.h_debut < c2.h_fin AND c1.h_fin > c2.h_debut)
            )
        ''', (data['creneau_id'], data['code_smartex_ens']))
        
        if cursor.fetchone()['count'] > 0:
            return jsonify({'error': 'Conflit d\'horaire: l\'enseignant est déjà affecté à un créneau qui chevauche'}), 409
        
        # Créer l'affectation
        db.execute('''
            INSERT INTO affectation (code_smartex_ens, creneau_id)
            VALUES (?, ?)
        ''', (data['code_smartex_ens'], data['creneau_id']))
        db.commit()
        
        return jsonify({
            'message': 'Affectation créée avec succès',
            'code_smartex_ens': data['code_smartex_ens'],
            'creneau_id': data['creneau_id']
        }), 201
    except sqlite3.IntegrityError as e:
        if 'UNIQUE' in str(e) or 'PRIMARY KEY' in str(e):
            return jsonify({'error': 'Cette affectation existe déjà'}), 409
        if 'FOREIGN KEY' in str(e):
            return jsonify({'error': 'Enseignant ou créneau invalide'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/<int:affectation_id>', methods=['PUT'])
def update_affectation(affectation_id):
    """PUT /api/affectations/<id> - Modifier une affectation (par ID)"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        db = get_db()
        
        # Vérifier que l'affectation existe
        cursor = db.execute('SELECT * FROM affectation WHERE affectation_id = ?', (affectation_id,))
        affectation = cursor.fetchone()
        
        if not affectation:
            return jsonify({'error': 'Affectation non trouvée'}), 404
        
        # Si on modifie l'enseignant, vérifier qu'il participe à la surveillance
        if 'code_smartex_ens' in data:
            cursor = db.execute('''
                SELECT participe_surveillance FROM enseignant 
                WHERE code_smartex_ens = ?
            ''', (data['code_smartex_ens'],))
            ens = cursor.fetchone()
            
            if not ens:
                return jsonify({'error': 'Enseignant non trouvé'}), 404
            if not ens['participe_surveillance']:
                return jsonify({'error': 'Cet enseignant ne participe pas à la surveillance'}), 400
        
        # Construire la requête UPDATE dynamiquement
        fields_to_update = []
        params = []
        
        if 'code_smartex_ens' in data:
            fields_to_update.append('code_smartex_ens = ?')
            params.append(data['code_smartex_ens'])
        if 'creneau_id' in data:
            fields_to_update.append('creneau_id = ?')
            params.append(data['creneau_id'])
        if 'jour' in data:
            fields_to_update.append('jour = ?')
            params.append(data['jour'])
        if 'seance' in data:
            fields_to_update.append('seance = ?')
            params.append(data['seance'])
        if 'date_examen' in data:
            fields_to_update.append('date_examen = ?')
            params.append(data['date_examen'])
        if 'h_debut' in data:
            fields_to_update.append('h_debut = ?')
            params.append(data['h_debut'])
        if 'h_fin' in data:
            fields_to_update.append('h_fin = ?')
            params.append(data['h_fin'])
        if 'cod_salle' in data:
            fields_to_update.append('cod_salle = ?')
            params.append(data['cod_salle'])
        if 'position' in data:
            fields_to_update.append('position = ?')
            params.append(data['position'])
        if 'id_session' in data:
            fields_to_update.append('id_session = ?')
            params.append(data['id_session'])
        
        if not fields_to_update:
            return jsonify({'error': 'Aucun champ à mettre à jour'}), 400
        
        params.append(affectation_id)
        query = f"UPDATE affectation SET {', '.join(fields_to_update)} WHERE affectation_id = ?"
        
        db.execute(query, params)
        db.commit()
        
        return jsonify({'message': 'Affectation modifiée avec succès'}), 200
    except sqlite3.IntegrityError as e:
        if 'UNIQUE' in str(e):
            return jsonify({'error': 'Cette affectation existe déjà'}), 409
        if 'FOREIGN KEY' in str(e):
            return jsonify({'error': 'Enseignant ou créneau invalide'}), 400
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/<int:code_smartex_ens>/<int:creneau_id>', methods=['DELETE'])
def delete_affectation(code_smartex_ens, creneau_id):
    """DELETE /api/affectations/<code_ens>/<creneau_id> - Supprimer une affectation"""
    try:
        db = get_db()
        cursor = db.execute('''
            DELETE FROM affectation 
            WHERE code_smartex_ens = ? AND creneau_id = ?
        ''', (code_smartex_ens, creneau_id))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Affectation non trouvée'}), 404
        return jsonify({'message': 'Affectation supprimée avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/by-id/<int:affectation_id>', methods=['DELETE'])
def delete_affectation_by_id(affectation_id):
    """DELETE /api/affectations/by-id/<id> - Supprimer une affectation par ID"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM affectation WHERE affectation_id = ?', (affectation_id,))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Affectation non trouvée'}), 404
        return jsonify({'message': 'Affectation supprimée avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/all', methods=['DELETE'])
def delete_all_affectations():
    """DELETE /api/affectations/all - Supprimer toutes les affectations"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM affectation')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} affectations supprimées avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/session/<int:id_session>', methods=['DELETE'])
def delete_affectations_by_session(id_session):
    """DELETE /api/affectations/session/<id> - Supprimer toutes les affectations d'une session"""
    try:
        db = get_db()
        cursor = db.execute('''
            DELETE FROM affectation 
            WHERE id_session = ?
        ''', (id_session,))
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} affectations supprimées avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/batch', methods=['DELETE'])
def delete_affectations_batch():
    """DELETE /api/affectations/batch - Supprimer plusieurs affectations par leurs IDs"""
    try:
        data = request.get_json()
        
        if not data or 'affectation_ids' not in data:
            return jsonify({'error': 'Liste d\'IDs d\'affectations requise'}), 400
        
        affectation_ids = data['affectation_ids']
        
        if not isinstance(affectation_ids, list) or len(affectation_ids) == 0:
            return jsonify({'error': 'La liste d\'IDs doit être non vide'}), 400
        
        db = get_db()
        placeholders = ','.join(['?' for _ in affectation_ids])
        cursor = db.execute(f'DELETE FROM affectation WHERE affectation_id IN ({placeholders})', affectation_ids)
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} affectations supprimées avec succès',
            'count': cursor.rowcount
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/batch', methods=['PUT'])
def update_affectations_batch():
    """PUT /api/affectations/batch - Modifier plusieurs affectations en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'affectations' not in data:
            return jsonify({'error': 'Liste d\'affectations requise'}), 400
        
        affectations_list = data['affectations']
        
        db = get_db()
        updated = []
        errors = []
        
        for aff in affectations_list:
            if 'affectation_id' not in aff:
                errors.append({
                    'affectation': aff,
                    'error': 'affectation_id requis'
                })
                continue
            
            try:
                # Construire la requête UPDATE dynamiquement
                fields_to_update = []
                params = []
                
                if 'code_smartex_ens' in aff:
                    fields_to_update.append('code_smartex_ens = ?')
                    params.append(aff['code_smartex_ens'])
                if 'creneau_id' in aff:
                    fields_to_update.append('creneau_id = ?')
                    params.append(aff['creneau_id'])
                if 'jour' in aff:
                    fields_to_update.append('jour = ?')
                    params.append(aff['jour'])
                if 'seance' in aff:
                    fields_to_update.append('seance = ?')
                    params.append(aff['seance'])
                if 'cod_salle' in aff:
                    fields_to_update.append('cod_salle = ?')
                    params.append(aff['cod_salle'])
                if 'position' in aff:
                    fields_to_update.append('position = ?')
                    params.append(aff['position'])
                
                if not fields_to_update:
                    errors.append({
                        'affectation': aff,
                        'error': 'Aucun champ à mettre à jour'
                    })
                    continue
                
                params.append(aff['affectation_id'])
                query = f"UPDATE affectation SET {', '.join(fields_to_update)} WHERE affectation_id = ?"
                
                cursor = db.execute(query, params)
                
                if cursor.rowcount > 0:
                    updated.append(aff['affectation_id'])
                else:
                    errors.append({
                        'affectation': aff,
                        'error': 'Affectation non trouvée'
                    })
            except Exception as e:
                errors.append({
                    'affectation': aff,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(updated)} affectations modifiées avec succès',
            'updated': updated,
            'errors': errors
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/enseignant/<int:code_smartex_ens>', methods=['GET'])
def get_affectations_enseignant(code_smartex_ens):
    """GET /api/affectations/enseignant/<code> - Toutes les affectations d'un enseignant"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT a.*, 
                   c.dateExam, c.h_debut, c.h_fin, c.cod_salle, c.type_ex,
                   s.libelle_session, s.id_session
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            JOIN session s ON c.id_session = s.id_session
            WHERE a.code_smartex_ens = ?
            ORDER BY c.dateExam, c.h_debut
        ''', (code_smartex_ens,))
        affectations = [dict(row) for row in cursor.fetchall()]
        
        # Calculer le nombre d'heures total
        total_heures = 0
        for aff in affectations:
            h_debut = aff['h_debut'].split(':')
            h_fin = aff['h_fin'].split(':')
            duree = (int(h_fin[0]) * 60 + int(h_fin[1])) - (int(h_debut[0]) * 60 + int(h_debut[1]))
            total_heures += duree / 60.0
        
        return jsonify({
            'affectations': affectations,
            'total_heures': round(total_heures, 2),
            'count': len(affectations)
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/creneau/<int:creneau_id>', methods=['GET'])
def get_affectations_creneau(creneau_id):
    """GET /api/affectations/creneau/<id> - Tous les surveillants d'un créneau"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT a.*, 
                   e.nom_ens, e.prenom_ens, e.email_ens, e.grade_code_ens,
                   g.quota
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
            WHERE a.creneau_id = ?
            ORDER BY e.nom_ens, e.prenom_ens
        ''', (creneau_id,))
        affectations = [dict(row) for row in cursor.fetchall()]
        return jsonify(affectations), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/batch', methods=['POST'])
def create_affectations_batch():
    """POST /api/affectations/batch - Créer plusieurs affectations en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'affectations' not in data:
            return jsonify({'error': 'Liste d\'affectations requise'}), 400
        
        affectations_list = data['affectations']
        required = ['code_smartex_ens', 'creneau_id']
        
        # Valider toutes les affectations
        for aff in affectations_list:
            if not all(k in aff for k in required):
                return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        created = []
        errors = []
        
        for aff in affectations_list:
            try:
                # Vérifier que l'enseignant participe à la surveillance
                cursor = db.execute('''
                    SELECT participe_surveillance FROM enseignant 
                    WHERE code_smartex_ens = ?
                ''', (aff['code_smartex_ens'],))
                ens = cursor.fetchone()
                
                if not ens:
                    errors.append({
                        'affectation': aff,
                        'error': 'Enseignant non trouvé'
                    })
                    continue
                
                if not ens['participe_surveillance']:
                    errors.append({
                        'affectation': aff,
                        'error': 'Cet enseignant ne participe pas à la surveillance'
                    })
                    continue
                
                # Vérifier les conflits d'horaire
                cursor = db.execute('''
                    SELECT COUNT(*) as count
                    FROM affectation a1
                    JOIN creneau c1 ON a1.creneau_id = c1.creneau_id
                    JOIN creneau c2 ON c2.creneau_id = ?
                    WHERE a1.code_smartex_ens = ?
                    AND c1.dateExam = c2.dateExam
                    AND (
                        (c1.h_debut < c2.h_fin AND c1.h_fin > c2.h_debut)
                    )
                ''', (aff['creneau_id'], aff['code_smartex_ens']))
                
                if cursor.fetchone()['count'] > 0:
                    errors.append({
                        'affectation': aff,
                        'error': 'Conflit d\'horaire'
                    })
                    continue
                
                # Créer l'affectation
                db.execute('''
                    INSERT INTO affectation (code_smartex_ens, creneau_id)
                    VALUES (?, ?)
                ''', (aff['code_smartex_ens'], aff['creneau_id']))
                created.append(aff)
                
            except sqlite3.IntegrityError as e:
                if 'UNIQUE' in str(e) or 'PRIMARY KEY' in str(e):
                    errors.append({
                        'affectation': aff,
                        'error': 'Cette affectation existe déjà'
                    })
                else:
                    errors.append({
                        'affectation': aff,
                        'error': str(e)
                    })
            except Exception as e:
                errors.append({
                    'affectation': aff,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(created)} affectations créées avec succès',
            'created': created,
            'errors': errors
        }), 201 if created else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/statistiques/enseignant/<int:code_smartex_ens>', methods=['GET'])
def get_statistiques_enseignant(code_smartex_ens):
    """GET /api/affectations/statistiques/enseignant/<code> - Statistiques d'un enseignant"""
    try:
        db = get_db()
        
        # Informations de base
        cursor = db.execute('''
            SELECT e.*, g.quota
            FROM enseignant e
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
            WHERE e.code_smartex_ens = ?
        ''', (code_smartex_ens,))
        enseignant = cursor.fetchone()
        
        if not enseignant:
            return jsonify({'error': 'Enseignant non trouvé'}), 404
        
        stats = dict(enseignant)
        
        # Nombre total d'affectations
        cursor = db.execute('''
            SELECT COUNT(*) as total_affectations
            FROM affectation
            WHERE code_smartex_ens = ?
        ''', (code_smartex_ens,))
        stats.update(cursor.fetchone())
        
        # Nombre d'heures total
        cursor = db.execute('''
            SELECT c.h_debut, c.h_fin
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE a.code_smartex_ens = ?
        ''', (code_smartex_ens,))
        
        total_heures = 0
        for row in cursor.fetchall():
            h_debut = row['h_debut'].split(':')
            h_fin = row['h_fin'].split(':')
            duree = (int(h_fin[0]) * 60 + int(h_fin[1])) - (int(h_debut[0]) * 60 + int(h_debut[1]))
            total_heures += duree / 60.0
        
        stats['total_heures'] = round(total_heures, 2)
        stats['quota_restant'] = stats['quota'] - total_heures if stats['quota'] else None
        
        # Affectations par session
        cursor = db.execute('''
            SELECT s.libelle_session, COUNT(*) as nb_affectations
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            JOIN session s ON c.id_session = s.id_session
            WHERE a.code_smartex_ens = ?
            GROUP BY s.id_session
        ''', (code_smartex_ens,))
        stats['par_session'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/statistiques/session/<int:id_session>', methods=['GET'])
def get_statistiques_session(id_session):
    """GET /api/affectations/statistiques/session/<id> - Statistiques d'une session"""
    try:
        db = get_db()
        
        # Nombre total d'affectations
        cursor = db.execute('''
            SELECT COUNT(*) as total_affectations
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE c.id_session = ?
        ''', (id_session,))
        stats = dict(cursor.fetchone())
        
        # Nombre d'enseignants distincts affectés
        cursor = db.execute('''
            SELECT COUNT(DISTINCT a.code_smartex_ens) as nb_enseignants
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE c.id_session = ?
        ''', (id_session,))
        stats.update(cursor.fetchone())
        
        # Affectations par grade
        cursor = db.execute('''
            SELECT e.grade_code_ens, g.quota,
                   COUNT(*) as nb_affectations,
                   COUNT(DISTINCT a.code_smartex_ens) as nb_enseignants
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
            WHERE c.id_session = ?
            GROUP BY e.grade_code_ens
        ''', (id_session,))
        stats['par_grade'] = [dict(row) for row in cursor.fetchall()]
        
        # Créneaux avec nombre de surveillants
        cursor = db.execute('''
            SELECT c.creneau_id, c.dateExam, c.h_debut, c.h_fin, 
                   c.cod_salle, COUNT(a.code_smartex_ens) as nb_surveillants
            FROM creneau c
            LEFT JOIN affectation a ON c.creneau_id = a.creneau_id
            WHERE c.id_session = ?
            GROUP BY c.creneau_id
            ORDER BY c.dateExam, c.h_debut
        ''', (id_session,))
        stats['creneaux'] = [dict(row) for row in cursor.fetchall()]
        
        return jsonify(stats), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/conflits/enseignant/<int:code_smartex_ens>', methods=['GET'])
def check_conflits_enseignant(code_smartex_ens):
    """GET /api/affectations/conflits/enseignant/<code> - Vérifier les conflits d'horaire d'un enseignant"""
    try:
        db = get_db()
        
        # Trouver les créneaux qui se chevauchent
        cursor = db.execute('''
            SELECT a1.creneau_id as creneau1, a2.creneau_id as creneau2,
                   c1.dateExam, c1.h_debut as h_debut1, c1.h_fin as h_fin1,
                   c2.h_debut as h_debut2, c2.h_fin as h_fin2,
                   c1.cod_salle as salle1, c2.cod_salle as salle2
            FROM affectation a1
            JOIN affectation a2 ON a1.code_smartex_ens = a2.code_smartex_ens 
                                AND a1.creneau_id < a2.creneau_id
            JOIN creneau c1 ON a1.creneau_id = c1.creneau_id
            JOIN creneau c2 ON a2.creneau_id = c2.creneau_id
            WHERE a1.code_smartex_ens = ?
            AND c1.dateExam = c2.dateExam
            AND (c1.h_debut < c2.h_fin AND c1.h_fin > c2.h_debut)
        ''', (code_smartex_ens,))
        
        conflits = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'has_conflits': len(conflits) > 0,
            'nb_conflits': len(conflits),
            'conflits': conflits
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/permuter', methods=['POST'])
def permuter_enseignants():
    """
    POST /api/affectations/permuter - Permuter deux enseignants entre leurs créneaux
    
    Body JSON:
    {
        "affectation_id_1": 123,
        "affectation_id_2": 456
    }
    OU
    {
        "code_smartex_ens_1": 100,
        "creneau_id_1": 50,
        "code_smartex_ens_2": 200,
        "creneau_id_2": 60
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        db = get_db()
        
        # Mode 1 : Par IDs d'affectation
        if 'affectation_id_1' in data and 'affectation_id_2' in data:
            affectation_id_1 = data['affectation_id_1']
            affectation_id_2 = data['affectation_id_2']
            
            # Récupérer les affectations
            cursor = db.execute('SELECT * FROM affectation WHERE affectation_id = ?', (affectation_id_1,))
            aff1 = cursor.fetchone()
            
            cursor = db.execute('SELECT * FROM affectation WHERE affectation_id = ?', (affectation_id_2,))
            aff2 = cursor.fetchone()
            
            if not aff1:
                return jsonify({'error': f'Affectation {affectation_id_1} non trouvée'}), 404
            if not aff2:
                return jsonify({'error': f'Affectation {affectation_id_2} non trouvée'}), 404
            
            code_ens_1 = aff1['code_smartex_ens']
            creneau_id_1 = aff1['creneau_id']
            code_ens_2 = aff2['code_smartex_ens']
            creneau_id_2 = aff2['creneau_id']
        
        # Mode 2 : Par codes enseignants et créneaux
        elif all(k in data for k in ['code_smartex_ens_1', 'creneau_id_1', 'code_smartex_ens_2', 'creneau_id_2']):
            code_ens_1 = data['code_smartex_ens_1']
            creneau_id_1 = data['creneau_id_1']
            code_ens_2 = data['code_smartex_ens_2']
            creneau_id_2 = data['creneau_id_2']
            
            # Vérifier que les affectations existent
            cursor = db.execute('''
                SELECT affectation_id FROM affectation 
                WHERE code_smartex_ens = ? AND creneau_id = ?
            ''', (code_ens_1, creneau_id_1))
            if not cursor.fetchone():
                return jsonify({'error': f'Affectation (enseignant={code_ens_1}, créneau={creneau_id_1}) non trouvée'}), 404
            
            cursor = db.execute('''
                SELECT affectation_id FROM affectation 
                WHERE code_smartex_ens = ? AND creneau_id = ?
            ''', (code_ens_2, creneau_id_2))
            if not cursor.fetchone():
                return jsonify({'error': f'Affectation (enseignant={code_ens_2}, créneau={creneau_id_2}) non trouvée'}), 404
        else:
            return jsonify({
                'error': 'Paramètres invalides. Utilisez soit (affectation_id_1, affectation_id_2) soit (code_smartex_ens_1, creneau_id_1, code_smartex_ens_2, creneau_id_2)'
            }), 400
        
        # Vérifier que ce ne sont pas les mêmes enseignants
        if code_ens_1 == code_ens_2:
            return jsonify({'error': 'Impossible de permuter un enseignant avec lui-même'}), 400
        
        # Vérifier que les deux enseignants participent à la surveillance
        cursor = db.execute('''
            SELECT code_smartex_ens, participe_surveillance, nom_ens, prenom_ens
            FROM enseignant 
            WHERE code_smartex_ens IN (?, ?)
        ''', (code_ens_1, code_ens_2))
        enseignants = cursor.fetchall()
        
        if len(enseignants) != 2:
            return jsonify({'error': 'Un ou plusieurs enseignants non trouvés'}), 404
        
        for ens in enseignants:
            if not ens['participe_surveillance']:
                return jsonify({
                    'error': f"L'enseignant {ens['nom_ens']} {ens['prenom_ens']} ne participe pas à la surveillance"
                }), 400
        
        # Vérifier les conflits d'horaire après permutation
        # Pour l'enseignant 1 avec le créneau 2
        cursor = db.execute('''
            SELECT COUNT(*) as count
            FROM affectation a1
            JOIN creneau c1 ON a1.creneau_id = c1.creneau_id
            JOIN creneau c2 ON c2.creneau_id = ?
            WHERE a1.code_smartex_ens = ?
            AND a1.creneau_id != ?
            AND c1.dateExam = c2.dateExam
            AND (c1.h_debut < c2.h_fin AND c1.h_fin > c2.h_debut)
        ''', (creneau_id_2, code_ens_1, creneau_id_1))
        
        if cursor.fetchone()['count'] > 0:
            return jsonify({
                'error': 'Conflit d\'horaire: l\'enseignant 1 a déjà un créneau qui chevauche le créneau 2'
            }), 409
        
        # Pour l'enseignant 2 avec le créneau 1
        cursor = db.execute('''
            SELECT COUNT(*) as count
            FROM affectation a1
            JOIN creneau c1 ON a1.creneau_id = c1.creneau_id
            JOIN creneau c2 ON c2.creneau_id = ?
            WHERE a1.code_smartex_ens = ?
            AND a1.creneau_id != ?
            AND c1.dateExam = c2.dateExam
            AND (c1.h_debut < c2.h_fin AND c1.h_fin > c2.h_debut)
        ''', (creneau_id_1, code_ens_2, creneau_id_2))
        
        if cursor.fetchone()['count'] > 0:
            return jsonify({
                'error': 'Conflit d\'horaire: l\'enseignant 2 a déjà un créneau qui chevauche le créneau 1'
            }), 409
        
        # Effectuer la permutation
        # Étape 1: Mettre temporairement l'enseignant 1 sur un créneau fictif (-1) pour éviter la contrainte UNIQUE
        db.execute('''
            UPDATE affectation 
            SET creneau_id = -1
            WHERE code_smartex_ens = ? AND creneau_id = ?
        ''', (code_ens_1, creneau_id_1))
        
        # Étape 2: Mettre l'enseignant 2 sur le créneau 1
        db.execute('''
            UPDATE affectation 
            SET code_smartex_ens = ?
            WHERE code_smartex_ens = ? AND creneau_id = ?
        ''', (code_ens_1, code_ens_2, creneau_id_2))
        
        # Étape 3: Mettre l'enseignant 2 sur le créneau 2 (celui qui était temporairement sur -1)
        db.execute('''
            UPDATE affectation 
            SET code_smartex_ens = ?, creneau_id = ?
            WHERE code_smartex_ens = ? AND creneau_id = -1
        ''', (code_ens_2, creneau_id_2, code_ens_1))
        
        db.commit()
        
        # Récupérer les informations des enseignants pour la réponse
        cursor = db.execute('''
            SELECT code_smartex_ens, nom_ens, prenom_ens 
            FROM enseignant 
            WHERE code_smartex_ens IN (?, ?)
        ''', (code_ens_1, code_ens_2))
        enseignants_info = {row['code_smartex_ens']: dict(row) for row in cursor.fetchall()}
        
        # Récupérer les informations des créneaux
        cursor = db.execute('''
            SELECT creneau_id, dateExam, h_debut, h_fin, cod_salle 
            FROM creneau 
            WHERE creneau_id IN (?, ?)
        ''', (creneau_id_1, creneau_id_2))
        creneaux_info = {row['creneau_id']: dict(row) for row in cursor.fetchall()}
        
        return jsonify({
            'message': 'Permutation effectuée avec succès',
            'permutation': {
                'enseignant_1': {
                    **enseignants_info[code_ens_1],
                    'ancien_creneau': creneaux_info[creneau_id_1],
                    'nouveau_creneau': creneaux_info[creneau_id_2]
                },
                'enseignant_2': {
                    **enseignants_info[code_ens_2],
                    'ancien_creneau': creneaux_info[creneau_id_2],
                    'nouveau_creneau': creneaux_info[creneau_id_1]
                }
            }
        }), 200
    except Exception as e:
        db.rollback()
        return jsonify({'error': str(e)}), 500