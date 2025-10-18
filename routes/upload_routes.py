"""
routes/upload_routes.py
Upload et import des fichiers Excel/CSV vers la base de données
"""

import sqlite3
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import pandas as pd
import os
from database.database import get_db
from utils.time_utils import parse_time, determine_seance_from_time
import logging

upload_bp = Blueprint('upload', __name__)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls'}

# Créer le dossier uploads s'il n'existe pas
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

logger = logging.getLogger(__name__)


def allowed_file(filename):
    """Vérifier si l'extension du fichier est autorisée"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def read_file(filepath):
    """Lire un fichier Excel ou CSV"""
    file_ext = os.path.splitext(filepath)[1].lower()
    
    try:
        if file_ext in ['.xlsx', '.xls']:
            return pd.read_excel(filepath)
        else:
            # Essayer différents encodages pour CSV
            try:
                return pd.read_csv(filepath, encoding='utf-8')
            except:
                try:
                    return pd.read_csv(filepath, encoding='latin1')
                except:
                    return pd.read_csv(filepath, sep=';')
    except Exception as e:
        logger.error(f"Erreur lecture fichier {filepath}: {str(e)}")
        raise

def generate_jour_seance_from_creneaux(session_id):
    """Remplit automatiquement les tables jour_seance et salle_par_creneau"""
    try:
        conn = sqlite3.connect('surveillance.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Générer salle_par_creneau d'abord
        print("Génération de salle_par_creneau...")
        cursor.execute("DELETE FROM salle_par_creneau WHERE id_session = ?", (session_id,))
        cursor.execute("""
            INSERT INTO salle_par_creneau (id_session, dateExam, h_debut, nb_salle)
            SELECT 
                id_session, 
                dateExam, 
                h_debut,
                COUNT(DISTINCT cod_salle) as nb_salle
            FROM creneau
            WHERE id_session = ?
            GROUP BY id_session, dateExam, h_debut
        """, (session_id,))
        
        # Récupère tous les créneaux pour jour_seance
        cursor.execute("""
            SELECT DISTINCT dateExam, h_debut, h_fin
            FROM creneau
            WHERE id_session = ?
            ORDER BY dateExam, h_debut
        """, (session_id,))
        
        creneaux = cursor.fetchall()
        if not creneaux:
            conn.close()
            return False
        
        # Extrait les dates uniques
        dates_uniques = sorted(set(row['dateExam'] for row in creneaux))
        
        # Crée la liste jour_seance
        jour_seance_list = []
        
        for jour_num, date in enumerate(dates_uniques, 1):
            creneaux_date = [c for c in creneaux if c['dateExam'] == date]
            seances_dict = {}
            
            for creneau in creneaux_date:
                h_debut = parse_time(creneau['h_debut'])
                h_fin = parse_time(creneau['h_fin'])
                seance_code = determine_seance_from_time(creneau['h_debut'])
                
                if seance_code and h_debut not in seances_dict:
                    seances_dict[h_debut] = {
                        'seance_code': seance_code,
                        'heure_debut': h_debut,
                        'heure_fin': h_fin
                    }
            
            for heure in sorted(seances_dict.keys()):
                seance_info = seances_dict[heure]
                jour_seance_list.append((
                    session_id,
                    jour_num,
                    date,
                    seance_info['seance_code'],
                    seance_info['heure_debut'],
                    seance_info['heure_fin']
                ))
        
        # Supprime l'ancien contenu
        cursor.execute("DELETE FROM jour_seance WHERE id_session = ?", (session_id,))
        
        # Ajoute les nouvelles données
        cursor.executemany("""
            INSERT INTO jour_seance 
            (id_session, jour_num, date_examen, seance_code, heure_debut, heure_fin)
            VALUES (?, ?, ?, ?, ?, ?)
        """, jour_seance_list)
        
        conn.commit()
        conn.close()
        return True
        
    except Exception as e:
        logger.error(f"Erreur jour_seance: {str(e)}")
        return False

# ============================================================================
# UPLOAD DES FICHIERS (3 MÉTHODES)
# ============================================================================

@upload_bp.route('/upload', methods=['POST'])
def upload_file():
    """
    MÉTHODE 1: Upload UN SEUL fichier + Import automatique en BD
    
    POST /api/upload/upload
    Form-data:
        - file: Le fichier (n'importe quel nom)
        - type: "enseignants" | "creneaux" | "voeux"
        - id_session: (optionnel, requis pour creneaux/voeux)
    
    Le fichier sera renommé automatiquement selon le type
    ET importé directement dans la base de données
    """
    try:
        if 'file' not in request.files:
            return jsonify({'success': False, 'error': 'Aucun fichier fourni'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'success': False, 'error': 'Fichier vide'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'success': False, 'error': 'Type de fichier non autorisé. Utilisez .csv, .xlsx ou .xls'}), 400
        
        file_type = request.form.get('type', '').lower()
        if file_type not in ['enseignants', 'creneaux', 'voeux']:
            return jsonify({'success': False, 'error': 'Type doit être: enseignants, creneaux ou voeux'}), 400
        
        id_session = request.form.get('id_session', type=int)
        
        # Vérifier id_session pour créneaux/voeux
        if file_type in ['creneaux', 'voeux'] and not id_session:
            return jsonify({'success': False, 'error': f'id_session requis pour {file_type}'}), 400
        
        # Vérifier que la session existe
        if id_session:
            db = get_db()
            session = db.execute('SELECT * FROM session WHERE id_session = ?', (id_session,)).fetchone()
            if not session:
                return jsonify({'success': False, 'error': f'Session {id_session} non trouvée'}), 404
        
        # Déterminer l'extension du fichier
        file_ext = os.path.splitext(file.filename)[1]
        
        # Renommer automatiquement selon le type
        new_filename = f"{file_type}{file_ext}"
        filepath = os.path.join(UPLOAD_FOLDER, new_filename)
        
        # Sauvegarder le fichier
        file.save(filepath)
        
        # Import automatique dans la BD
        import_result = None
        try:
            if file_type == 'enseignants':
                import_result = import_enseignants_internal(filepath)
            elif file_type == 'creneaux':
                import_result = import_creneaux_internal(filepath, id_session)
            elif file_type == 'voeux':
                import_result = import_voeux_internal(filepath, id_session)
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Fichier uploadé mais erreur import: {str(e)}',
                'filepath': filepath
            }), 500
        
        return jsonify({
            'success': True,
            'message': f'Fichier uploadé et importé avec succès',
            'upload': {
                'original_filename': file.filename,
                'saved_as': new_filename,
                'filepath': filepath,
                'type': file_type
            },
            'import': import_result
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur upload fichier: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@upload_bp.route('/upload-multiple', methods=['POST'])
def upload_multiple_files():
    """
    MÉTHODE 2: Upload PLUSIEURS fichiers + Import automatique en BD
    
    POST /api/upload/upload-multiple
    Form-data:
        - enseignants_file: Fichier des enseignants (n'importe quel nom) (optionnel)
        - creneaux_file: Fichier des créneaux (optionnel)
        - voeux_file: Fichier des vœux (optionnel)
        - id_session: ID de session (requis pour créneaux/voeux)
    
    Les fichiers seront renommés automatiquement
    ET importés directement dans la base de données
    """
    try:
        id_session = request.form.get('id_session', type=int)
        
        results = {
            'upload': {},
            'import': {}
        }
        
        db = get_db()
        
        # Vérifier la session si fournie
        if id_session:
            session = db.execute('SELECT * FROM session WHERE id_session = ?', (id_session,)).fetchone()
            if not session:
                return jsonify({'success': False, 'error': f'Session {id_session} non trouvée'}), 404
        
        # ========== ENSEIGNANTS ==========
        if 'enseignants_file' in request.files:
            file = request.files['enseignants_file']
            if file.filename != '' and allowed_file(file.filename):
                try:
                    file_ext = os.path.splitext(file.filename)[1]
                    new_filename = f"enseignants{file_ext}"
                    filepath = os.path.join(UPLOAD_FOLDER, new_filename)
                    file.save(filepath)
                    
                    results['upload']['enseignants'] = {
                        'original': file.filename,
                        'saved_as': new_filename,
                        'status': 'success'
                    }
                    
                    # Import automatique
                    import_result = import_enseignants_internal(filepath)
                    results['import']['enseignants'] = {
                        'status': 'succès',
                        'inserted': import_result['inserted'],
                        'updated': import_result['updated'],
                        'errors': import_result['errors']
                    }
                    
                except Exception as e:
                    results['upload']['enseignants'] = {'status': 'error', 'message': str(e)}
                    results['import']['enseignants'] = {'status': 'erreur', 'message': str(e)}
        
        # ========== CRÉNEAUX ==========
        if 'creneaux_file' in request.files:
            file = request.files['creneaux_file']
            if file.filename != '' and allowed_file(file.filename):
                if not id_session:
                    results['import']['creneaux'] = {
                        'status': 'erreur',
                        'message': 'id_session requis pour import créneaux'
                    }
                else:
                    try:
                        file_ext = os.path.splitext(file.filename)[1]
                        new_filename = f"creneaux{file_ext}"
                        filepath = os.path.join(UPLOAD_FOLDER, new_filename)
                        file.save(filepath)
                        
                        results['upload']['creneaux'] = {
                            'original': file.filename,
                            'saved_as': new_filename,
                            'status': 'success'
                        }
                        
                        # Import automatique
                        import_result = import_creneaux_internal(filepath, id_session)
                        results['import']['creneaux'] = {
                            'status': 'succès',
                            'inserted': import_result['inserted'],
                            'errors': import_result['errors'],
                            'jour_seance_generated': import_result.get('jour_seance_generated', False)
                        }
                        
                    except Exception as e:
                        results['upload']['creneaux'] = {'status': 'error', 'message': str(e)}
                        results['import']['creneaux'] = {'status': 'erreur', 'message': str(e)}
        
        # ========== VŒUX ==========
        if 'voeux_file' in request.files:
            file = request.files['voeux_file']
            if file.filename != '' and allowed_file(file.filename):
                if not id_session:
                    results['import']['voeux'] = {
                        'status': 'erreur',
                        'message': 'id_session requis pour import vœux'
                    }
                else:
                    try:
                        file_ext = os.path.splitext(file.filename)[1]
                        new_filename = f"voeux{file_ext}"
                        filepath = os.path.join(UPLOAD_FOLDER, new_filename)
                        file.save(filepath)
                        
                        results['upload']['voeux'] = {
                            'original': file.filename,
                            'saved_as': new_filename,
                            'status': 'success'
                        }
                        
                        # Import automatique
                        import_result = import_voeux_internal(filepath, id_session)
                        results['import']['voeux'] = {
                            'status': 'succès',
                            'inserted': import_result['inserted'],
                            'errors': import_result['errors']
                        }
                        
                    except Exception as e:
                        results['upload']['voeux'] = {'status': 'error', 'message': str(e)}
                        results['import']['voeux'] = {'status': 'erreur', 'message': str(e)}
        
        if not results['upload']:
            return jsonify({'success': False, 'error': 'Aucun fichier valide uploadé'}), 400
        
        return jsonify({
            'success': True,
            'message': f'Upload et import terminés: {len(results["upload"])} fichier(s)',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur upload multiple: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@upload_bp.route('/upload-and-import', methods=['POST'])
def upload_and_import():
    """
    MÉTHODE 3: Upload ET Import en une seule requête
    
    POST /api/upload/upload-and-import
    Form-data:
        - enseignants_file: Fichier des enseignants (n'importe quel nom)
        - creneaux_file: Fichier des créneaux (optionnel)
        - voeux_file: Fichier des vœux (optionnel)
        - id_session: ID de session (requis pour créneaux/voeux)
    
    Upload + Renommage + Import automatique en base de données
    """
    try:
        id_session = request.form.get('id_session', type=int)
        
        results = {
            'upload': {},
            'import': {
                'enseignants': {'status': 'non_demandé'},
                'creneaux': {'status': 'non_demandé'},
                'voeux': {'status': 'non_demandé'}
            }
        }
        
        db = get_db()
        
        # Vérifier la session si fournie
        if id_session:
            session = db.execute('SELECT * FROM session WHERE id_session = ?', (id_session,)).fetchone()
            if not session:
                return jsonify({'success': False, 'error': f'Session {id_session} non trouvée'}), 404
        
        # ========== ENSEIGNANTS ==========
        if 'enseignants_file' in request.files:
            file = request.files['enseignants_file']
            if file.filename != '' and allowed_file(file.filename):
                try:
                    # Upload
                    file_ext = os.path.splitext(file.filename)[1]
                    new_filename = f"enseignants{file_ext}"
                    filepath = os.path.join(UPLOAD_FOLDER, new_filename)
                    file.save(filepath)
                    
                    results['upload']['enseignants'] = {
                        'original': file.filename,
                        'saved_as': new_filename,
                        'status': 'success'
                    }
                    
                    # Import automatique
                    import_result = import_enseignants_internal(filepath)
                    results['import']['enseignants'] = {
                        'status': 'succès',
                        'inserted': import_result['inserted'],
                        'updated': import_result['updated'],
                        'errors': import_result['errors']
                    }
                    
                except Exception as e:
                    results['upload']['enseignants'] = {'status': 'error', 'message': str(e)}
                    results['import']['enseignants'] = {'status': 'erreur', 'message': str(e)}
        
        # ========== CRÉNEAUX ==========
        if 'creneaux_file' in request.files:
            file = request.files['creneaux_file']
            if file.filename != '' and allowed_file(file.filename):
                if not id_session:
                    results['import']['creneaux'] = {
                        'status': 'erreur',
                        'message': 'id_session requis pour import créneaux'
                    }
                else:
                    try:
                        # Upload
                        file_ext = os.path.splitext(file.filename)[1]
                        new_filename = f"creneaux{file_ext}"
                        filepath = os.path.join(UPLOAD_FOLDER, new_filename)
                        file.save(filepath)
                        
                        results['upload']['creneaux'] = {
                            'original': file.filename,
                            'saved_as': new_filename,
                            'status': 'success'
                        }
                        
                        # Import automatique
                        import_result = import_creneaux_internal(filepath, id_session)
                        results['import']['creneaux'] = {
                            'status': 'succès',
                            'inserted': import_result['inserted'],
                            'errors': import_result['errors'],
                            'jour_seance_generated': import_result.get('jour_seance_generated', False)
                        }
                        
                    except Exception as e:
                        results['upload']['creneaux'] = {'status': 'error', 'message': str(e)}
                        results['import']['creneaux'] = {'status': 'erreur', 'message': str(e)}
        
        # ========== VŒUX ==========
        if 'voeux_file' in request.files:
            file = request.files['voeux_file']
            if file.filename != '' and allowed_file(file.filename):
                if not id_session:
                    results['import']['voeux'] = {
                        'status': 'erreur',
                        'message': 'id_session requis pour import vœux'
                    }
                else:
                    try:
                        # Upload
                        file_ext = os.path.splitext(file.filename)[1]
                        new_filename = f"voeux{file_ext}"
                        filepath = os.path.join(UPLOAD_FOLDER, new_filename)
                        file.save(filepath)
                        
                        results['upload']['voeux'] = {
                            'original': file.filename,
                            'saved_as': new_filename,
                            'status': 'success'
                        }
                        
                        # Import automatique
                        import_result = import_voeux_internal(filepath, id_session)
                        results['import']['voeux'] = {
                            'status': 'succès',
                            'inserted': import_result['inserted'],
                            'errors': import_result['errors']
                        }
                        
                    except Exception as e:
                        results['upload']['voeux'] = {'status': 'error', 'message': str(e)}
                        results['import']['voeux'] = {'status': 'erreur', 'message': str(e)}
        
        if not results['upload']:
            return jsonify({'success': False, 'error': 'Aucun fichier valide uploadé'}), 400
        
        return jsonify({
            'success': True,
            'message': 'Upload et import terminés',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur upload et import: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# IMPORT SEULEMENT (depuis fichiers déjà uploadés)
# ============================================================================

@upload_bp.route('/import/enseignants', methods=['POST'])
def import_enseignants():
    """
    POST /api/upload/import/enseignants
    Importer les enseignants depuis un fichier déjà uploadé
    Body: {"filepath": "uploads/enseignants.xlsx"}
    """
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'Fichier non trouvé'}), 404
        
        result = import_enseignants_internal(filepath)
        
        return jsonify({
            'success': True,
            'message': 'Import terminé',
            'inserted': result['inserted'],
            'updated': result['updated'],
            'errors': result['errors']
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur import enseignants: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@upload_bp.route('/import/creneaux', methods=['POST'])
def import_creneaux():
    """
    POST /api/upload/import/creneaux
    Importer les créneaux depuis un fichier déjà uploadé
    Body: {"filepath": "uploads/creneaux.xlsx", "id_session": 1}
    """
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        id_session = data.get('id_session')
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'Fichier non trouvé'}), 404
        
        if not id_session:
            return jsonify({'success': False, 'error': 'id_session requis'}), 400
        
        # Vérifier que la session existe
        db = get_db()
        session = db.execute('SELECT * FROM session WHERE id_session = ?', (id_session,)).fetchone()
        if not session:
            return jsonify({'success': False, 'error': 'Session non trouvée'}), 404
        
        result = import_creneaux_internal(filepath, id_session)
        
        return jsonify({
            'success': True,
            'message': 'Import terminé',
            'inserted': result['inserted'],
            'errors': result['errors'],
            'jour_seance_generated': result.get('jour_seance_generated', False)
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur import créneaux: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


@upload_bp.route('/import/voeux', methods=['POST'])
def import_voeux():
    """
    POST /api/upload/import/voeux
    Importer les vœux depuis un fichier déjà uploadé
    Body: {"filepath": "uploads/voeux.xlsx", "id_session": 1}
    """
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        id_session = data.get('id_session')
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'success': False, 'error': 'Fichier non trouvé'}), 404
        
        if not id_session:
            return jsonify({'success': False, 'error': 'id_session requis'}), 400
        
        # Vérifier que la session existe
        db = get_db()
        session = db.execute('SELECT * FROM session WHERE id_session = ?', (id_session,)).fetchone()
        if not session:
            return jsonify({'success': False, 'error': 'Session non trouvée'}), 404
        
        result = import_voeux_internal(filepath, id_session)
        
        return jsonify({
            'success': True,
            'message': 'Import terminé',
            'inserted': result['inserted'],
            'errors': result['errors']
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur import vœux: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# UTILITAIRES
# ============================================================================

@upload_bp.route('/list-files', methods=['GET'])
def list_upload_files():
    """
    GET /api/upload/list-files
    Liste les fichiers Excel/CSV disponibles dans le dossier uploads
    """
    try:
        files = []
        if os.path.exists(UPLOAD_FOLDER):
            for filename in os.listdir(UPLOAD_FOLDER):
                if allowed_file(filename):
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    files.append({
                        'filename': filename,
                        'filepath': filepath,
                        'size': os.path.getsize(filepath),
                        'modified': os.path.getmtime(filepath)
                    })
        return jsonify({
            'success': True,
            'count': len(files),
            'files': sorted(files, key=lambda x: x['modified'], reverse=True)
        }), 200
    except Exception as e:
        logger.error(f"Erreur listage fichiers: {str(e)}")
        return jsonify({'success': False, 'error': str(e)}), 500


# ============================================================================
# FONCTIONS INTERNES (pas de routes Flask)
# ============================================================================
def import_enseignants_internal(filepath):
    """Importer les enseignants depuis un fichier"""
    # Lire le fichier
    df = read_file(filepath)
    
    # Mapper les colonnes
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if 'nom' in col_lower and 'prenom' not in col_lower:
            col_mapping[col] = 'nom_ens'
        elif 'prenom' in col_lower or 'prénom' in col_lower:
            col_mapping[col] = 'prenom_ens'
        elif 'email' in col_lower or 'mail' in col_lower:
            col_mapping[col] = 'email_ens'
        elif 'grade' in col_lower:
            col_mapping[col] = 'grade_code_ens'
        elif 'code' in col_lower and ('smartex' in col_lower or 'ens' in col_lower):
            col_mapping[col] = 'code_smartex_ens'
        elif 'particip' in col_lower and 'surveill' in col_lower:
            col_mapping[col] = 'participe_surveillance'
    
    df = df.rename(columns=col_mapping)
    
    # Vérifier les colonnes requises
    required = ['nom_ens', 'prenom_ens', 'grade_code_ens', 'code_smartex_ens']
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f'Colonnes manquantes: {", ".join(missing)}')
    
    # Nettoyer les données
    df['code_smartex_ens'] = df['code_smartex_ens'].apply(
        lambda x: int(float(x)) if pd.notna(x) else None
    )
    
    # Normaliser les grades (convertir en majuscules)
    df['grade_code_ens'] = df['grade_code_ens'].apply(lambda x: str(x).strip().upper() if pd.notna(x) else None)
    
    # Mapper VA vers V (fusion des grades Vacataire Assistant avec Vacataire)
    df['grade_code_ens'] = df['grade_code_ens'].apply(lambda x: 'V' if x == 'VA' else x)
    
    # Gérer participe_surveillance
    if 'participe_surveillance' in df.columns:
        df['participe_surveillance'] = df['participe_surveillance'].map({
            'TRUE': 1, 'True': 1, 'true': 1, '1': 1, 1: 1, True: 1,
            'FALSE': 0, 'False': 0, 'false': 0, '0': 0, 0: 0, False: 0
        }).fillna(1)
    else:
        df['participe_surveillance'] = 1
    
    # Insérer dans la base de données
    db = get_db()
    inserted = 0
    updated = 0
    errors = []
    
    for idx, row in df.iterrows():
        try:
            # Vérifier si l'enseignant existe déjà
            existing = db.execute(
                'SELECT code_smartex_ens FROM enseignant WHERE code_smartex_ens = ?',
                (row['code_smartex_ens'],)
            ).fetchone()
            
            if existing:
                # UPDATE
                db.execute('''
                    UPDATE enseignant 
                    SET nom_ens = ?, prenom_ens = ?, email_ens = ?,
                        grade_code_ens = ?, participe_surveillance = ?
                    WHERE code_smartex_ens = ?
                ''', (row['nom_ens'], row['prenom_ens'], row.get('email_ens'),
                      row['grade_code_ens'], row['participe_surveillance'],
                      row['code_smartex_ens']))
                updated += 1
            else:
                # INSERT
                db.execute('''
                    INSERT INTO enseignant 
                    (code_smartex_ens, nom_ens, prenom_ens, email_ens, 
                     grade_code_ens, participe_surveillance)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (row['code_smartex_ens'], row['nom_ens'], row['prenom_ens'],
                      row.get('email_ens'), row['grade_code_ens'], 
                      row['participe_surveillance']))
                inserted += 1
                
        except Exception as e:
            errors.append(f"Ligne {idx+1}: {str(e)}")
            continue
    
    db.commit()
    return {
        'inserted': inserted,
        'updated': updated,
        'errors': errors
    }

def import_creneaux_internal(filepath, id_session):
    """Importer les créneaux depuis un fichier"""
    # Lire le fichier
    df = read_file(filepath)
    
    # Mapper les colonnes
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if 'date' in col_lower and 'exam' in col_lower:
            col_mapping[col] = 'dateExam'
        elif 'debut' in col_lower and 'h' in col_lower:
            col_mapping[col] = 'h_debut'
        elif 'fin' in col_lower and 'h' in col_lower:
            col_mapping[col] = 'h_fin'
        elif 'type' in col_lower and 'ex' in col_lower:
            col_mapping[col] = 'type_ex'
        elif 'semestre' in col_lower:
            col_mapping[col] = 'semestre'
        elif 'enseignant' in col_lower or 'responsable' in col_lower:
            col_mapping[col] = 'enseignant'
        elif 'salle' in col_lower or 'cod_salle' in col_lower:
            col_mapping[col] = 'cod_salle'
    
    df = df.rename(columns=col_mapping)
    
    # Vérifier les colonnes requises
    required = ['dateExam', 'h_debut', 'h_fin']
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f'Colonnes manquantes: {", ".join(missing)}')
    
    # Nettoyer l'enseignant responsable
    if 'enseignant' in df.columns:
        df['enseignant'] = df['enseignant'].apply(
            lambda x: int(float(x)) if pd.notna(x) else None
        )
    
    # Insérer dans la base de données
    db = get_db()
    inserted = 0
    errors = []
    
    for idx, row in df.iterrows():
        try:
            # Normaliser les heures au format HH:MM
            h_debut_normalized = parse_time(row['h_debut'])
            h_fin_normalized = parse_time(row['h_fin'])
            
            db.execute('''
                INSERT INTO creneau 
                (id_session, dateExam, h_debut, h_fin, type_ex, 
                 semestre, enseignant, cod_salle)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (id_session, row['dateExam'], h_debut_normalized, h_fin_normalized,
                  row.get('type_ex'), row.get('semestre'), 
                  row.get('enseignant'), row.get('cod_salle')))
            inserted += 1
            
        except Exception as e:
            errors.append(f"Ligne {idx+1}: {str(e)}")
            continue
    
    db.commit()
     # Génère jour_seance automatiquement
    jour_seance_generated = generate_jour_seance_from_creneaux(id_session)
    return {
        'inserted': inserted,
        'errors': errors,
        'jour_seance_generated': jour_seance_generated
    }

def import_voeux_internal(filepath, id_session):
    """Importer les vœux depuis un fichier"""
    # Lire le fichier
    df = read_file(filepath)
    
    # Mapper les colonnes
    col_mapping = {}
    for col in df.columns:
        col_lower = col.lower()
        if 'nom' in col_lower and 'prenom' not in col_lower:
            col_mapping[col] = 'nom_ens'
        elif 'prenom' in col_lower:
            col_mapping[col] = 'prenom_ens'
        elif 'code' in col_lower and 'smartex' in col_lower:
            col_mapping[col] = 'code_smartex_ens'
        elif 'jour' in col_lower:
            col_mapping[col] = 'jour'
        elif 'seance' in col_lower or 'séance' in col_lower:
            col_mapping[col] = 'seance'
    
    df = df.rename(columns=col_mapping)
    
    # Si pas de code_smartex_ens, chercher par nom/prénom
    if 'code_smartex_ens' not in df.columns and 'nom_ens' in df.columns:
        # Créer mapping nom/prenom -> code
        db = get_db()
        enseignants = db.execute('SELECT code_smartex_ens, nom_ens, prenom_ens FROM enseignant').fetchall()
        nom_to_code = {(e['nom_ens'].lower(), e['prenom_ens'].lower()): e['code_smartex_ens'] 
                      for e in enseignants}
        
        df['code_smartex_ens'] = df.apply(
            lambda row: nom_to_code.get(
                (str(row.get('nom_ens', '')).lower(), 
                 str(row.get('prenom_ens', '')).lower()),
                None
            ), axis=1
        )
    
    # Vérifier les colonnes requises
    required = ['code_smartex_ens', 'jour', 'seance']
    missing = [col for col in required if col not in df.columns]
    if missing:
        raise ValueError(f'Colonnes manquantes: {", ".join(missing)}')
    
    # Nettoyer les données
    df = df.dropna(subset=['code_smartex_ens', 'jour', 'seance'])
    df['code_smartex_ens'] = df['code_smartex_ens'].apply(lambda x: int(float(x)))
    df['jour'] = df['jour'].apply(lambda x: int(float(x)))
    
    # Insérer dans la base de données
    db = get_db()
    inserted = 0
    errors = []
    
    for idx, row in df.iterrows():
        try:
            # Éviter les doublons
            existing = db.execute('''
                SELECT voeu_id FROM voeu 
                WHERE code_smartex_ens = ? AND id_session = ? 
                  AND jour = ? AND seance = ?
            ''', (row['code_smartex_ens'], id_session, 
                  row['jour'], row['seance'])).fetchone()
            
            if not existing:
                db.execute('''
                    INSERT INTO voeu (code_smartex_ens, id_session, jour, seance)
                    VALUES (?, ?, ?, ?)
                ''', (row['code_smartex_ens'], id_session, 
                      row['jour'], row['seance']))
                inserted += 1
                
        except Exception as e:
            errors.append(f"Ligne {idx+1}: {str(e)}")
            continue
    
    db.commit()
    return {
        'inserted': inserted,
        'errors': errors
    }