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