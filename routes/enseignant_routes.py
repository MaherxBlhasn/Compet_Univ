import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db

enseignant_bp = Blueprint('enseignants', __name__)


def normalize_grade(grade):
    """
    Normalise le code grade en convertissant en majuscules et en mappant VA vers V.
    VA (Vacataire Assistant) est fusionné avec V (Vacataire).
    """
    if not grade:
        return grade
    grade = str(grade).strip().upper()
    # Mapper VA vers V
    if grade == 'VA':
        return 'V'
    return grade


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
        
        # Normaliser le grade (VA -> V)
        grade = normalize_grade(data['grade_code_ens'])
        
        db = get_db()
        db.execute('''
            INSERT INTO enseignant (code_smartex_ens, nom_ens, prenom_ens, 
                                   email_ens, grade_code_ens, participe_surveillance)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (data['code_smartex_ens'], data['nom_ens'], data['prenom_ens'],
              data.get('email_ens'), grade, 
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
        
        # Normaliser le grade si fourni (VA -> V)
        grade = normalize_grade(data.get('grade_code_ens')) if 'grade_code_ens' in data else None
        
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
              grade, data.get('participe_surveillance'),
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

@enseignant_bp.route('/all', methods=['DELETE'])
def delete_all_enseignants():
    """DELETE /api/enseignants/all - Supprimer tous les enseignants"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM enseignant')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} enseignants supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: certains enseignants ont des affectations'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@enseignant_bp.route('/batch', methods=['POST'])
def create_enseignants_batch():
    """POST /api/enseignants/batch - Créer plusieurs enseignants en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'enseignants' not in data:
            return jsonify({'error': 'Liste d\'enseignants requise'}), 400
        
        enseignants_list = data['enseignants']
        required = ['code_smartex_ens', 'nom_ens', 'prenom_ens', 'grade_code_ens']
        
        # Valider tous les enseignants
        for ens in enseignants_list:
            if not all(k in ens for k in required):
                return jsonify({'error': f'Champs requis: {", ".join(required)}'}), 400
        
        db = get_db()
        created = []
        errors = []
        
        for ens in enseignants_list:
            try:
                # Normaliser le grade (VA -> V)
                grade = normalize_grade(ens['grade_code_ens'])
                
                db.execute('''
                    INSERT INTO enseignant (code_smartex_ens, nom_ens, prenom_ens, 
                                           email_ens, grade_code_ens, participe_surveillance)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (ens['code_smartex_ens'], ens['nom_ens'], ens['prenom_ens'],
                      ens.get('email_ens'), grade, 
                      ens.get('participe_surveillance', 1)))
                created.append(ens['code_smartex_ens'])
            except sqlite3.IntegrityError as e:
                if 'UNIQUE' in str(e):
                    errors.append({
                        'enseignant': ens,
                        'error': 'Cet enseignant existe déjà'
                    })
                else:
                    errors.append({
                        'enseignant': ens,
                        'error': 'Grade invalide'
                    })
            except Exception as e:
                errors.append({
                    'enseignant': ens,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(created)} enseignants créés avec succès',
            'created': created,
            'errors': errors
        }), 201 if created else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@enseignant_bp.route('/batch', methods=['PUT'])
def update_enseignants_batch():
    """PUT /api/enseignants/batch - Modifier plusieurs enseignants en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'enseignants' not in data:
            return jsonify({'error': 'Liste d\'enseignants requise'}), 400
        
        enseignants_list = data['enseignants']
        
        db = get_db()
        updated = []
        errors = []
        
        for ens in enseignants_list:
            if 'code_smartex_ens' not in ens:
                errors.append({
                    'enseignant': ens,
                    'error': 'code_smartex_ens requis'
                })
                continue
            
            try:
                # Normaliser le grade si fourni (VA -> V)
                grade = normalize_grade(ens.get('grade_code_ens')) if 'grade_code_ens' in ens else None
                
                cursor = db.execute('''
                    UPDATE enseignant 
                    SET nom_ens = COALESCE(?, nom_ens),
                        prenom_ens = COALESCE(?, prenom_ens),
                        email_ens = COALESCE(?, email_ens),
                        grade_code_ens = COALESCE(?, grade_code_ens),
                        participe_surveillance = COALESCE(?, participe_surveillance)
                    WHERE code_smartex_ens = ?
                ''', (ens.get('nom_ens'), ens.get('prenom_ens'), ens.get('email_ens'),
                      grade, ens.get('participe_surveillance'),
                      ens['code_smartex_ens']))
                
                if cursor.rowcount > 0:
                    updated.append(ens['code_smartex_ens'])
                else:
                    errors.append({
                        'enseignant': ens,
                        'error': 'Enseignant non trouvé'
                    })
            except Exception as e:
                errors.append({
                    'enseignant': ens,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(updated)} enseignants modifiés avec succès',
            'updated': updated,
            'errors': errors
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@enseignant_bp.route('/surveillance', methods=['GET'])
def get_enseignants_surveillance():
    """GET /api/enseignants/surveillance - Récupérer les enseignants qui participent à la surveillance"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT e.*, g.quota 
            FROM enseignant e
            LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
            WHERE e.participe_surveillance = 1
            ORDER BY e.nom_ens, e.prenom_ens
        ''')
        enseignants = [dict(row) for row in cursor.fetchall()]
        return jsonify(enseignants), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500