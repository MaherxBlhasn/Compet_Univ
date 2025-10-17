import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db

grade_bp = Blueprint('grades', __name__)

@grade_bp.route('', methods=['GET'])
def get_all_grades():
    """GET /api/grades - Récupérer tous les grades"""
    try:
        db = get_db()
        cursor = db.execute('SELECT * FROM grade')
        grades = [dict(row) for row in cursor.fetchall()]
        return jsonify(grades), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@grade_bp.route('/<code_grade>', methods=['GET'])
def get_grade(code_grade):
    """GET /api/grades/<code_grade> - Récupérer un grade"""
    try:
        db = get_db()
        cursor = db.execute('SELECT * FROM grade WHERE code_grade = ?', (code_grade,))
        grade = cursor.fetchone()
        if grade is None:
            return jsonify({'error': 'Grade non trouvé'}), 404
        return jsonify(dict(grade)), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@grade_bp.route('', methods=['POST'])
def create_grade():
    """POST /api/grades - Créer un grade"""
    try:
        data = request.get_json()
        if not data or 'code_grade' not in data or 'grade' not in data or 'quota' not in data:
            return jsonify({'error': 'code_grade, grade et quota requis'}), 400
        
        db = get_db()
        db.execute('INSERT INTO grade (code_grade, grade, quota) VALUES (?, ?, ?)',
                   (data['code_grade'], data['grade'], data['quota']))
        db.commit()
        return jsonify({'message': 'Grade créé avec succès', 'code_grade': data['code_grade']}), 201
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Ce grade existe déjà'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@grade_bp.route('/<code_grade>', methods=['PUT'])
def update_grade(code_grade):
    """PUT /api/grades/<code_grade> - Modifier un grade"""
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400
        
        # Construire dynamiquement la requête UPDATE
        fields = []
        values = []
        
        if 'grade' in data:
            fields.append('grade = ?')
            values.append(data['grade'])
        if 'quota' in data:
            fields.append('quota = ?')
            values.append(data['quota'])
        
        if not fields:
            return jsonify({'error': 'Aucun champ à mettre à jour'}), 400
        
        values.append(code_grade)
        query = f"UPDATE grade SET {', '.join(fields)} WHERE code_grade = ?"
        
        db = get_db()
        cursor = db.execute(query, values)
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Grade non trouvé'}), 404
        return jsonify({'message': 'Grade modifié avec succès'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@grade_bp.route('/<code_grade>', methods=['DELETE'])
def delete_grade(code_grade):
    """DELETE /api/grades/<code_grade> - Supprimer un grade"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM grade WHERE code_grade = ?', (code_grade,))
        db.commit()
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Grade non trouvé'}), 404
        return jsonify({'message': 'Grade supprimé avec succès'}), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: des enseignants utilisent ce grade'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@grade_bp.route('/all', methods=['DELETE'])
def delete_all_grades():
    """DELETE /api/grades/all - Supprimer tous les grades"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM grade')
        db.commit()
        
        return jsonify({
            'message': f'{cursor.rowcount} grades supprimés avec succès',
            'count': cursor.rowcount
        }), 200
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Impossible de supprimer: certains grades sont utilisés par des enseignants'}), 409
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@grade_bp.route('/batch', methods=['POST'])
def create_grades_batch():
    """POST /api/grades/batch - Créer plusieurs grades en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'grades' not in data:
            return jsonify({'error': 'Liste de grades requise'}), 400
        
        grades_list = data['grades']
        required = ['code_grade', 'grade', 'quota']
        
        # Valider tous les grades
        for grade_item in grades_list:
            if not all(k in grade_item for k in required):
                return jsonify({'error': f'Champs requis pour chaque grade: {", ".join(required)}'}), 400
        
        db = get_db()
        created = []
        errors = []
        
        for grade_item in grades_list:
            try:
                db.execute('INSERT INTO grade (code_grade, grade, quota) VALUES (?, ?, ?)',
                          (grade_item['code_grade'], grade_item['grade'], grade_item['quota']))
                created.append(grade_item['code_grade'])
            except sqlite3.IntegrityError:
                errors.append({
                    'grade': grade_item,
                    'error': 'Ce grade existe déjà'
                })
            except Exception as e:
                errors.append({
                    'grade': grade_item,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(created)} grades créés avec succès',
            'created': created,
            'errors': errors
        }), 201 if created else 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@grade_bp.route('/batch', methods=['PUT'])
def update_grades_batch():
    """PUT /api/grades/batch - Modifier plusieurs grades en une fois"""
    try:
        data = request.get_json()
        
        if not data or 'grades' not in data:
            return jsonify({'error': 'Liste de grades requise'}), 400
        
        grades_list = data['grades']
        
        db = get_db()
        updated = []
        errors = []
        
        for grade_item in grades_list:
            if 'code_grade' not in grade_item:
                errors.append({
                    'grade': grade_item,
                    'error': 'code_grade requis'
                })
                continue
            
            try:
                # Construire dynamiquement la requête UPDATE
                fields = []
                values = []
                
                if 'grade' in grade_item:
                    fields.append('grade = ?')
                    values.append(grade_item['grade'])
                if 'quota' in grade_item:
                    fields.append('quota = ?')
                    values.append(grade_item['quota'])
                
                if not fields:
                    errors.append({
                        'grade': grade_item,
                        'error': 'Aucun champ à mettre à jour'
                    })
                    continue
                
                values.append(grade_item['code_grade'])
                query = f"UPDATE grade SET {', '.join(fields)} WHERE code_grade = ?"
                
                cursor = db.execute(query, values)
                if cursor.rowcount > 0:
                    updated.append(grade_item['code_grade'])
                else:
                    errors.append({
                        'grade': grade_item,
                        'error': 'Grade non trouvé'
                    })
            except Exception as e:
                errors.append({
                    'grade': grade_item,
                    'error': str(e)
                })
        
        db.commit()
        
        return jsonify({
            'message': f'{len(updated)} grades modifiés avec succès',
            'updated': updated,
            'errors': errors
        }), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

