import sqlite3
from flask import Blueprint, jsonify, request
from database import get_db

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
        if not data or 'code_grade' not in data or 'quota' not in data:
            return jsonify({'error': 'code_grade et quota requis'}), 400
        
        db = get_db()
        db.execute('INSERT INTO grade (code_grade, quota) VALUES (?, ?)',
                   (data['code_grade'], data['quota']))
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
        if not data or 'quota' not in data:
            return jsonify({'error': 'quota requis'}), 400
        
        db = get_db()
        cursor = db.execute('UPDATE grade SET quota = ? WHERE code_grade = ?',
                           (data['quota'], code_grade))
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

