"""
routes/upload_routes.py
Upload et import des fichiers Excel/CSV vers la base de données
"""

import sqlite3
from flask import Blueprint, request, jsonify
from werkzeug.utils import secure_filename
import pandas as pd
import os
from database import get_db
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

def parse_time(time_str):
    """Extrait l'heure d'un timestamp"""
    if pd.isna(time_str):
        return None
    time_str = str(time_str)
    if ' ' in time_str:
        return time_str.split(' ')[1][:5]
    return time_str[:5]


def determine_seance_from_time(time_str):
    """Détermine S1, S2, S3 ou S4 selon l'heure"""
    if pd.isna(time_str):
        return None
    
    time_str = str(time_str)
    if ' ' in time_str:
        time_part = time_str.split(' ')[1]
    else:
        time_part = time_str
    
    try:
        hour = int(time_part.split(':')[0])
        if 8 <= hour < 10:
            return 'S1'
        elif 10 <= hour < 12:
            return 'S2'
        elif 12 <= hour < 14:
            return 'S3'
        elif 14 <= hour < 17:
            return 'S4'
    except:
        pass
    return None


def generate_jour_seance_from_creneaux(session_id):
    """Remplit automatiquement la table jour_seance"""
    try:
        conn = sqlite3.connect('surveillance.db')
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Récupère tous les créneaux
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
# UPLOAD DES FICHIERS
# ============================================================================

@upload_bp.route('/files', methods=['POST'])
def upload_files():
    """
    POST /api/upload/files
    Upload des fichiers (enseignants, creneaux, voeux)
    """
    try:
        files_uploaded = {}
        
        # Vérifier et sauvegarder le fichier des enseignants
        if 'enseignants_file' in request.files:
            enseignants_file = request.files['enseignants_file']
            if enseignants_file.filename != '' and allowed_file(enseignants_file.filename):
                filename = secure_filename(enseignants_file.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                enseignants_file.save(filepath)
                files_uploaded['enseignants'] = filepath
        
        # Vérifier et sauvegarder le fichier des créneaux
        if 'creneaux_file' in request.files:
            creneaux_file = request.files['creneaux_file']
            if creneaux_file.filename != '' and allowed_file(creneaux_file.filename):
                filename = secure_filename(creneaux_file.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                creneaux_file.save(filepath)
                files_uploaded['creneaux'] = filepath
        
        # Vérifier et sauvegarder le fichier des vœux
        if 'voeux_file' in request.files:
            voeux_file = request.files['voeux_file']
            if voeux_file.filename != '' and allowed_file(voeux_file.filename):
                filename = secure_filename(voeux_file.filename)
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                voeux_file.save(filepath)
                files_uploaded['voeux'] = filepath
        
        if not files_uploaded:
            return jsonify({'error': 'Aucun fichier valide n\'a été téléchargé'}), 400
        
        return jsonify({
            'success': True,
            'message': f'{len(files_uploaded)} fichier(s) uploadé(s) avec succès',
            'files': files_uploaded
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur upload: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# IMPORT ENSEIGNANTS
# ============================================================================

@upload_bp.route('/import/enseignants', methods=['POST'])
def import_enseignants():
    """
    POST /api/upload/import/enseignants
    Importer les enseignants depuis un fichier uploadé
    Body: {"filepath": "uploads/enseignants.xlsx"}
    """
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'Fichier non trouvé'}), 404
        
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
            return jsonify({'error': f'Colonnes manquantes: {", ".join(missing)}'}), 400
        
        # Nettoyer les données
        df['code_smartex_ens'] = df['code_smartex_ens'].apply(
            lambda x: int(float(x)) if pd.notna(x) else None
        )
        
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
        
        for _, row in df.iterrows():
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
                errors.append(f"Ligne {_}: {str(e)}")
                continue
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Import terminé',
            'inserted': inserted,
            'updated': updated,
            'errors': errors
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur import enseignants: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# IMPORT CRENEAUX
# ============================================================================

@upload_bp.route('/import/creneaux', methods=['POST'])
def import_creneaux():
    """
    POST /api/upload/import/creneaux
    Importer les créneaux depuis un fichier uploadé
    Body: {"filepath": "uploads/creneaux.xlsx", "id_session": 1}
    """
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        id_session = data.get('id_session')
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'Fichier non trouvé'}), 404
        
        if not id_session:
            return jsonify({'error': 'id_session requis'}), 400
        
        # Vérifier que la session existe
        db = get_db()
        session = db.execute('SELECT * FROM session WHERE id_session = ?', 
                            (id_session,)).fetchone()
        if not session:
            return jsonify({'error': 'Session non trouvée'}), 404
        
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
            return jsonify({'error': f'Colonnes manquantes: {", ".join(missing)}'}), 400
        
        # Nettoyer l'enseignant responsable
        if 'enseignant' in df.columns:
            df['enseignant'] = df['enseignant'].apply(
                lambda x: int(float(x)) if pd.notna(x) else None
            )
        
        # Insérer dans la base de données
        inserted = 0
        errors = []
        
        for _, row in df.iterrows():
            try:
                db.execute('''
                    INSERT INTO creneau 
                    (id_session, dateExam, h_debut, h_fin, type_ex, 
                     semestre, enseignant, cod_salle)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ''', (id_session, row['dateExam'], row['h_debut'], row['h_fin'],
                      row.get('type_ex'), row.get('semestre'), 
                      row.get('enseignant'), row.get('cod_salle')))
                inserted += 1
                
            except Exception as e:
                errors.append(f"Ligne {_}: {str(e)}")
                continue
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Import terminé',
            'inserted': inserted,
            'errors': errors
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur import créneaux: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# IMPORT VOEUX
# ============================================================================

@upload_bp.route('/import/voeux', methods=['POST'])
def import_voeux():
    """
    POST /api/upload/import/voeux
    Importer les vœux depuis un fichier uploadé
    Body: {"filepath": "uploads/voeux.xlsx", "id_session": 1}
    """
    try:
        data = request.get_json()
        filepath = data.get('filepath')
        id_session = data.get('id_session')
        
        if not filepath or not os.path.exists(filepath):
            return jsonify({'error': 'Fichier non trouvé'}), 404
        
        if not id_session:
            return jsonify({'error': 'id_session requis'}), 400
        
        # Vérifier que la session existe
        db = get_db()
        session = db.execute('SELECT * FROM session WHERE id_session = ?', 
                            (id_session,)).fetchone()
        if not session:
            return jsonify({'error': 'Session non trouvée'}), 404
        
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
            return jsonify({'error': f'Colonnes manquantes: {", ".join(missing)}'}), 400
        
        # Nettoyer les données
        df = df.dropna(subset=['code_smartex_ens', 'jour', 'seance'])
        df['code_smartex_ens'] = df['code_smartex_ens'].apply(lambda x: int(float(x)))
        df['jour'] = df['jour'].apply(lambda x: int(float(x)))
        
        # Insérer dans la base de données
        inserted = 0
        errors = []
        
        for _, row in df.iterrows():
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
                errors.append(f"Ligne {_}: {str(e)}")
                continue
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Import terminé',
            'inserted': inserted,
            'errors': errors
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur import vœux: {str(e)}")
        return jsonify({'error': str(e)}), 500


# ============================================================================
# LISTER LES FICHIERS UPLOADÉS
# ============================================================================

@upload_bp.route('/list-uploads', methods=['GET'])
def list_upload_files():
    """
    GET /api/upload/list-uploads
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
            'files': sorted(files, key=lambda x: x['modified'], reverse=True)
        }), 200
    except Exception as e:
        logger.error(f"Erreur listage fichiers: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# IMPORT DEPUIS LES FICHIERS UPLOADÉS
# ============================================================================

@upload_bp.route('/import-from-uploads', methods=['POST'])
def import_from_uploads():
    """
    POST /api/upload/import-from-uploads
    Importer les données depuis les fichiers du dossier uploads
    
    Body: {
        "id_session": 1,              # Requis pour créneaux/voeux
        "imports": {
            "enseignants": "nom_fichier.xlsx",  # Fichier dans uploads/
            "creneaux": "creneaux.xlsx",        # Optionnel
            "voeux": "voeux.xlsx"               # Optionnel
        }
    }
    """
    try:
        data = request.get_json()
        if not data:
            return jsonify({'error': 'Données requises'}), 400

        id_session = data.get('id_session')
        if not id_session and ('creneaux' in data.get('imports', {}) or 'voeux' in data.get('imports', {})):
            return jsonify({'error': 'id_session requis pour import créneaux/voeux'}), 400

        imports = data.get('imports', {})
        if not imports:
            return jsonify({'error': 'Aucun fichier spécifié pour import'}), 400

        results = {
            'enseignants': {'status': 'non_demandé'},
            'creneaux': {'status': 'non_demandé'},
            'voeux': {'status': 'non_demandé'}
        }

        # 1. Import enseignants si spécifié
        if 'enseignants' in imports:
            filepath = os.path.join(UPLOAD_FOLDER, imports['enseignants'])
            if not os.path.exists(filepath):
                results['enseignants'] = {
                    'status': 'erreur',
                    'message': 'Fichier non trouvé'
                }
            else:
                try:
                    resp = import_enseignants_internal(filepath)
                    results['enseignants'] = {
                        'status': 'succès',
                        'inserted': resp['inserted'],
                        'updated': resp['updated'],
                        'errors': resp['errors']
                    }
                except Exception as e:
                    results['enseignants'] = {
                        'status': 'erreur',
                        'message': str(e)
                    }

        # 2. Import créneaux si spécifié
        if 'creneaux' in imports:
            filepath = os.path.join(UPLOAD_FOLDER, imports['creneaux'])
            if not os.path.exists(filepath):
                results['creneaux'] = {
                    'status': 'erreur',
                    'message': 'Fichier non trouvé'
                }
            else:
                try:
                    resp = import_creneaux_internal(filepath, id_session)
                    results['creneaux'] = {
                        'status': 'succès',
                        'inserted': resp['inserted'],
                        'errors': resp['errors']
                    }
                except Exception as e:
                    results['creneaux'] = {
                        'status': 'erreur',
                        'message': str(e)
                    }

        # 3. Import voeux si spécifié
        if 'voeux' in imports:
            filepath = os.path.join(UPLOAD_FOLDER, imports['voeux'])
            if not os.path.exists(filepath):
                results['voeux'] = {
                    'status': 'erreur',
                    'message': 'Fichier non trouvé'
                }
            else:
                try:
                    resp = import_voeux_internal(filepath, id_session)
                    results['voeux'] = {
                        'status': 'succès',
                        'inserted': resp['inserted'],
                        'errors': resp['errors']
                    }
                except Exception as e:
                    results['voeux'] = {
                        'status': 'erreur',
                        'message': str(e)
                    }

        return jsonify({
            'success': True,
            'message': 'Import terminé',
            'results': results
        }), 200

    except Exception as e:
        logger.error(f"Erreur import depuis uploads: {str(e)}")
        return jsonify({'error': str(e)}), 500

# ============================================================================
# IMPORT COMPLET (3 fichiers en une fois)
# ============================================================================

@upload_bp.route('/import/all', methods=['POST'])
def import_all():
    """
    POST /api/upload/import/all
    Importer tous les fichiers en une seule requête
    Body: {
        "id_session": 1,
        "enseignants_path": "uploads/enseignants.xlsx",
        "creneaux_path": "uploads/creneaux.xlsx",
        "voeux_path": "uploads/voeux.xlsx"
    }
    """
    try:
        data = request.get_json()
        id_session = data.get('id_session')
        
        results = {
            'enseignants': {'inserted': 0, 'updated': 0, 'errors': []},
            'creneaux': {'inserted': 0, 'errors': []},
            'voeux': {'inserted': 0, 'errors': []}
        }
        
        # 1. Import enseignants
        if data.get('enseignants_path'):
            resp = import_enseignants_internal(data['enseignants_path'])
            results['enseignants'] = resp
        
        # 2. Import créneaux
        if data.get('creneaux_path') and id_session:
            resp = import_creneaux_internal(data['creneaux_path'], id_session)
            results['creneaux'] = resp
        
        # 3. Import vœux
        if data.get('voeux_path') and id_session:
            resp = import_voeux_internal(data['voeux_path'], id_session)
            results['voeux'] = resp
        
        return jsonify({
            'success': True,
            'message': 'Import complet terminé',
            'results': results
        }), 200
        
    except Exception as e:
        logger.error(f"Erreur import complet: {str(e)}")
        return jsonify({'error': str(e)}), 500


# Fonctions internes pour l'import (sans retour Flask)
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
            db.execute('''
                INSERT INTO creneau 
                (id_session, dateExam, h_debut, h_fin, type_ex, 
                 semestre, enseignant, cod_salle)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ''', (id_session, row['dateExam'], row['h_debut'], row['h_fin'],
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