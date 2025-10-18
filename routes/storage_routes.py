"""
Routes pour la gestion du stockage (mémoire et suppression de fichiers)
"""

import os
import shutil
from flask import Blueprint, jsonify, request
from pathlib import Path

storage_bp = Blueprint('storage', __name__)


def get_directory_size(path):
    """
    Calculer la taille d'un dossier en bytes
    
    Args:
        path: Chemin du dossier
    
    Returns:
        int: Taille en bytes
    """
    total_size = 0
    
    if not os.path.exists(path):
        return 0
    
    try:
        for dirpath, dirnames, filenames in os.walk(path):
            for filename in filenames:
                filepath = os.path.join(dirpath, filename)
                if os.path.exists(filepath):
                    total_size += os.path.getsize(filepath)
    except Exception as e:
        print(f"Erreur lors du calcul de la taille de {path}: {e}")
    
    return total_size


def format_size(size_bytes):
    """
    Formater la taille en unité lisible (KB, MB, GB)
    
    Args:
        size_bytes: Taille en bytes
    
    Returns:
        dict: {'value': float, 'unit': str, 'formatted': str}
    """
    if size_bytes < 1024:
        return {
            'value': size_bytes,
            'unit': 'B',
            'formatted': f"{size_bytes} B"
        }
    elif size_bytes < 1024 * 1024:
        kb = size_bytes / 1024
        return {
            'value': round(kb, 2),
            'unit': 'KB',
            'formatted': f"{kb:.2f} KB"
        }
    elif size_bytes < 1024 * 1024 * 1024:
        mb = size_bytes / (1024 * 1024)
        return {
            'value': round(mb, 2),
            'unit': 'MB',
            'formatted': f"{mb:.2f} MB"
        }
    else:
        gb = size_bytes / (1024 * 1024 * 1024)
        return {
            'value': round(gb, 2),
            'unit': 'GB',
            'formatted': f"{gb:.2f} GB"
        }


def get_session_folders(base_path):
    """
    Lister tous les dossiers session_* dans un répertoire
    
    Args:
        base_path: Chemin de base
    
    Returns:
        list: Liste des dossiers session avec leur taille
    """
    sessions = []
    
    if not os.path.exists(base_path):
        return sessions
    
    try:
        for item in os.listdir(base_path):
            item_path = os.path.join(base_path, item)
            if os.path.isdir(item_path) and item.startswith('session_'):
                try:
                    session_id = int(item.split('_')[1])
                    size_bytes = get_directory_size(item_path)
                    
                    sessions.append({
                        'session_id': session_id,
                        'folder_name': item,
                        'path': item_path,
                        'size_bytes': size_bytes,
                        'size': format_size(size_bytes)
                    })
                except (ValueError, IndexError):
                    continue
    except Exception as e:
        print(f"Erreur lors du scan de {base_path}: {e}")
    
    return sorted(sessions, key=lambda x: x['session_id'])


@storage_bp.route('/', methods=['GET'])
def get_storage_info():
    """
    GET /api/storage
    
    Retourne les informations sur l'utilisation de la mémoire disque
    par les fichiers générés (PDF et CSV)
    
    Returns:
        JSON avec:
        - Taille totale par type de fichier
        - Détail par session
        - Nombre de fichiers
    """
    try:
        # Définir les chemins
        base_paths = {
            'affectations_pdf': os.path.join('results', 'affectations'),
            'affectations_csv': os.path.join('results', 'affectation_csv'),
            'convocations_pdf': os.path.join('results', 'convocations'),
            'convocations_csv': os.path.join('results', 'convocation_csv'),
            'presences_responsables_pdf': os.path.join('results', 'presences_responsables')
        }
        
        # Calculer les tailles globales
        totals = {}
        sessions_detail = {}
        file_counts = {}
        
        for category, path in base_paths.items():
            # Taille totale du dossier
            total_size = get_directory_size(path)
            totals[category] = {
                'size_bytes': total_size,
                'size': format_size(total_size),
                'path': path
            }
            
            # Détail par session
            sessions = get_session_folders(path)
            sessions_detail[category] = sessions
            
            # Compter les fichiers
            file_count = 0
            if os.path.exists(path):
                for dirpath, dirnames, filenames in os.walk(path):
                    file_count += len(filenames)
            
            file_counts[category] = file_count
        
        # Calculer les totaux combinés
        total_pdf_size = (totals['affectations_pdf']['size_bytes'] + 
                         totals['convocations_pdf']['size_bytes'] + 
                         totals['presences_responsables_pdf']['size_bytes'])
        total_csv_size = totals['affectations_csv']['size_bytes'] + totals['convocations_csv']['size_bytes']
        total_all_size = total_pdf_size + total_csv_size
        
        # Préparer le résumé par session
        all_sessions = set()
        for sessions_list in sessions_detail.values():
            for session in sessions_list:
                all_sessions.add(session['session_id'])
        
        sessions_summary = []
        for session_id in sorted(all_sessions):
            session_data = {
                'session_id': session_id,
                'affectations_pdf': None,
                'affectations_csv': None,
                'convocations_pdf': None,
                'convocations_csv': None,
                'presences_responsables_pdf': None,
                'total_bytes': 0
            }
            
            for category, sessions_list in sessions_detail.items():
                for session in sessions_list:
                    if session['session_id'] == session_id:
                        session_data[category] = session['size']
                        session_data['total_bytes'] += session['size_bytes']
            
            session_data['total'] = format_size(session_data['total_bytes'])
            del session_data['total_bytes']
            
            sessions_summary.append(session_data)
        
        return jsonify({
            'success': True,
            'totals': {
                'affectations_pdf': totals['affectations_pdf']['size'],
                'affectations_csv': totals['affectations_csv']['size'],
                'convocations_pdf': totals['convocations_pdf']['size'],
                'convocations_csv': totals['convocations_csv']['size'],
                'presences_responsables_pdf': totals['presences_responsables_pdf']['size'],
                'total_pdf': format_size(total_pdf_size),
                'total_csv': format_size(total_csv_size),
                'total_all': format_size(total_all_size)
            },
            'file_counts': file_counts,
            'total_files': sum(file_counts.values()),
            'sessions': sessions_summary,
            'total_sessions': len(all_sessions)
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': f"Erreur lors du calcul de la mémoire: {str(e)}",
            'traceback': traceback.format_exc()
        }), 500


@storage_bp.route('/delete-all', methods=['DELETE'])
def delete_all_files():
    """
    DELETE /api/storage/delete-all
    
    Supprime TOUS les fichiers PDF et CSV générés (toutes sessions)
    ⚠️ ATTENTION : Action irréversible!
    
    Query params (optionnel):
        - type: 'pdf', 'csv', ou 'all' (default: 'all')
    
    Returns:
        JSON avec le nombre de fichiers/dossiers supprimés
    """
    try:
        file_type = request.args.get('type', 'all').lower()
        
        if file_type not in ['pdf', 'csv', 'all']:
            return jsonify({
                'success': False,
                'error': "Le paramètre 'type' doit être 'pdf', 'csv' ou 'all'"
            }), 400
        
        deleted = {
            'affectations_pdf': 0,
            'affectations_csv': 0,
            'convocations_pdf': 0,
            'convocations_csv': 0,
            'presences_responsables_pdf': 0
        }
        
        base_paths = {
            'affectations_pdf': os.path.join('results', 'affectations'),
            'affectations_csv': os.path.join('results', 'affectation_csv'),
            'convocations_pdf': os.path.join('results', 'convocations'),
            'convocations_csv': os.path.join('results', 'convocation_csv'),
            'presences_responsables_pdf': os.path.join('results', 'presences_responsables')
        }
        
        for category, path in base_paths.items():
            # Vérifier si on doit supprimer ce type
            if file_type == 'pdf' and not category.endswith('_pdf'):
                continue
            if file_type == 'csv' and not category.endswith('_csv'):
                continue
            
            if os.path.exists(path):
                # Compter les fichiers avant suppression
                file_count = sum(len(files) for _, _, files in os.walk(path))
                
                # Supprimer le dossier complet
                shutil.rmtree(path)
                
                # Recréer le dossier vide
                os.makedirs(path, exist_ok=True)
                
                deleted[category] = file_count
        
        total_deleted = sum(deleted.values())
        
        return jsonify({
            'success': True,
            'message': f"{total_deleted} fichiers supprimés",
            'deleted': deleted,
            'type': file_type
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': f"Erreur lors de la suppression: {str(e)}",
            'traceback': traceback.format_exc()
        }), 500


@storage_bp.route('/delete/session/<int:session_id>', methods=['DELETE'])
def delete_session_files(session_id):
    """
    DELETE /api/storage/delete/session/<session_id>
    
    Supprime tous les fichiers PDF et CSV d'une session spécifique
    
    Query params (optionnel):
        - type: 'pdf', 'csv', ou 'all' (default: 'all')
    
    Args:
        session_id: ID de la session
    
    Returns:
        JSON avec le nombre de fichiers supprimés
    """
    try:
        file_type = request.args.get('type', 'all').lower()
        
        if file_type not in ['pdf', 'csv', 'all']:
            return jsonify({
                'success': False,
                'error': "Le paramètre 'type' doit être 'pdf', 'csv' ou 'all'"
            }), 400
        
        deleted = {
            'affectations_pdf': 0,
            'affectations_csv': 0,
            'convocations_pdf': 0,
            'convocations_csv': 0,
            'presences_responsables_pdf': 0
        }
        
        session_folders = {
            'affectations_pdf': os.path.join('results', 'affectations', f'session_{session_id}'),
            'affectations_csv': os.path.join('results', 'affectation_csv', f'session_{session_id}'),
            'convocations_pdf': os.path.join('results', 'convocations', f'session_{session_id}'),
            'convocations_csv': os.path.join('results', 'convocation_csv', f'session_{session_id}'),
            'presences_responsables_pdf': os.path.join('results', 'presences_responsables', f'session_{session_id}')
        }
        
        found_any = False
        
        for category, path in session_folders.items():
            # Vérifier si on doit supprimer ce type
            if file_type == 'pdf' and not category.endswith('_pdf'):
                continue
            if file_type == 'csv' and not category.endswith('_csv'):
                continue
            
            if os.path.exists(path):
                found_any = True
                
                # Compter les fichiers avant suppression
                file_count = sum(len(files) for _, _, files in os.walk(path))
                
                # Supprimer le dossier de la session
                shutil.rmtree(path)
                
                deleted[category] = file_count
        
        if not found_any:
            return jsonify({
                'success': False,
                'error': f"Aucun fichier trouvé pour la session {session_id}",
                'session_id': session_id
            }), 404
        
        total_deleted = sum(deleted.values())
        
        return jsonify({
            'success': True,
            'message': f"{total_deleted} fichiers supprimés pour la session {session_id}",
            'session_id': session_id,
            'deleted': deleted,
            'type': file_type
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': f"Erreur lors de la suppression: {str(e)}",
            'traceback': traceback.format_exc()
        }), 500


@storage_bp.route('/cleanup/empty', methods=['DELETE'])
def cleanup_empty_folders():
    """
    DELETE /api/storage/cleanup/empty
    
    Supprime tous les dossiers session_* vides
    
    Returns:
        JSON avec le nombre de dossiers supprimés
    """
    try:
        base_paths = [
            os.path.join('results', 'affectations'),
            os.path.join('results', 'affectation_csv'),
            os.path.join('results', 'convocations'),
            os.path.join('results', 'convocation_csv'),
            os.path.join('results', 'presences_responsables')
        ]
        
        deleted_folders = []
        
        for base_path in base_paths:
            if not os.path.exists(base_path):
                continue
            
            for item in os.listdir(base_path):
                item_path = os.path.join(base_path, item)
                
                if os.path.isdir(item_path) and item.startswith('session_'):
                    # Vérifier si le dossier est vide
                    if not os.listdir(item_path):
                        shutil.rmtree(item_path)
                        deleted_folders.append(item_path)
        
        return jsonify({
            'success': True,
            'message': f"{len(deleted_folders)} dossiers vides supprimés",
            'deleted_folders': deleted_folders
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            'success': False,
            'error': f"Erreur lors du nettoyage: {str(e)}",
            'traceback': traceback.format_exc()
        }), 500
