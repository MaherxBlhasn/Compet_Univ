import sqlite3
from flask import Blueprint, jsonify, request,send_file
from database.database import get_db, remplir_responsables_absents
import os
import pandas as pd
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
from reportlab.lib.units import cm
from reportlab.platypus import Image as RLImage
from reportlab.lib.styles import ParagraphStyle
from io import BytesIO
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.pdfbase import pdfmetrics
import zipfile
from datetime import datetime


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
                   c.dateExam, c.h_debut, c.h_fin, c.cod_salle, c.type_ex, c.enseignant,
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
                   c.dateExam, c.h_debut, c.h_fin, c.cod_salle, c.type_ex, c.enseignant,
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
        # Récupérer l'id_session du créneau
        cursor = db.execute('SELECT id_session FROM creneau WHERE creneau_id = ?', (data['creneau_id'],))
        creneau = cursor.fetchone()
        if creneau:
            remplir_responsables_absents(creneau['id_session'])
        
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


@affectation_bp.route('/delete-all', methods=['DELETE'])
def delete_all_affectations():
    """DELETE /api/affectations/delete-all - Supprimer toutes les affectations"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM affectation')
        db.commit()
        return jsonify({'message': 'Toutes les affectations ont été supprimées.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    
@affectation_bp.route('/delete-by-session/<int:id_session>', methods=['DELETE'])
def delete_affectations_by_session(id_session):
    """DELETE /api/affectations/delete-by-session/<id_session> - Supprimer toutes les affectations d'une session donnée"""
    try:
        db = get_db()
        cursor = db.execute('DELETE FROM affectation WHERE id_session = ?', (id_session,))
        db.commit()

        if cursor.rowcount > 0:
            return jsonify({'message': f'Toutes les affectations de la session {id_session} ont été supprimées.'}), 200
        else:
            return jsonify({'message': f'Aucune affectation trouvée pour la session {id_session}.'}), 404

    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/enseignant/<int:code_smartex_ens>', methods=['GET'])
def get_affectations_enseignant(code_smartex_ens):
    """GET /api/affectations/enseignant/<code> - Toutes les affectations d'un enseignant"""
    try:
        db = get_db()
        cursor = db.execute('''
            SELECT a.*, 
                   c.dateExam, c.h_debut, c.h_fin, c.cod_salle, c.type_ex, c.enseignant,
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
                   c.enseignant,
                   g.quota
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            JOIN creneau c ON a.creneau_id = c.creneau_id
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
    
    
    
    

PDF_DIR = os.path.join("results", "convocations")

def add_footer(canvas, doc, footer_image_path):
    """Fonction pour ajouter le footer en bas de page"""
    canvas.saveState()
    # Positionner l'image en bas de la page
    footer = RLImage(footer_image_path, width=18*cm, height=1.5*cm)
    footer.drawOn(canvas, 1.5*cm, 1*cm)  # Position x, y depuis le bas
    canvas.restoreState()

@affectation_bp.route("/generate_convocations/<int:id_session>", methods=["GET"])
def generate_convocations(id_session):
    try:
        # Créer le dossier convocations pour cette session s'il n'existe pas
        session_pdf_dir = os.path.join(PDF_DIR, f"session_{id_session}")
        os.makedirs(session_pdf_dir, exist_ok=True)
        
        db = get_db()

        # Récupérer les enseignants distincts avec leurs noms
        cursor = db.execute("""
            SELECT DISTINCT a.code_smartex_ens, e.nom_ens, e.prenom_ens
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            WHERE a.id_session = ?
        """, (id_session,))
        enseignants = cursor.fetchall()

        if not enseignants:
            return jsonify({"message": f"Aucune affectation trouvée pour la session {id_session}"}), 404

        for ens in enseignants:
            code = ens["code_smartex_ens"]
            nom = ens["nom_ens"]
            prenom = ens["prenom_ens"]

            # Récupérer les lignes d'affectation de cet enseignant
            cursor.execute("""
                SELECT date_examen, h_debut, h_fin 
                FROM affectation 
                WHERE id_session = ? AND code_smartex_ens = ?
                ORDER BY date_examen, h_debut
            """, (id_session, code))
            rows = cursor.fetchall()

            # Créer le PDF dans le dossier de la session
            pdf_path = os.path.join(session_pdf_dir, f"convocation_{code}_{nom}_{prenom}_{id_session}.pdf")
            doc = SimpleDocTemplate(pdf_path, pagesize=A4, 
                                   leftMargin=50, rightMargin=50,
                                   topMargin=100, bottomMargin=80)
            styles = getSampleStyleSheet()
            elements = []
            logo_path="assets/logo.png"
            # Créer l'image du logo en gardant le ratio
            from PIL import Image as PILImage
            img = PILImage.open(logo_path)
            img_width, img_height = img.size
            aspect_ratio = img_height / img_width
            
            desired_width = 3*cm
            logo = RLImage(logo_path, width=desired_width, height=desired_width * aspect_ratio)
            
            from datetime import datetime
            date_approbation = datetime.now().strftime("%d%m-%y")
            
            header_data = [
                [logo, "GESTION DES EXAMENS ET\n\n DÉLIBÉRATIONS\n", "EXD-FR-08-01"],
                ["", "Procédure d'exécution des épreuves", f"Date d'approbation\n{date_approbation}"],
                ["", "Liste d'affectation des surveillants", "Page 1/1"]
            ]
            
            header_table = Table(header_data, colWidths=[4*cm, 12*cm, 4*cm])
            header_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("ALIGN", (2, 0), (2, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (1, 0), (1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (1, 0), (1, 0), 16),
                ("FONTSIZE", (1, 1), (1, 2), 12),
                ("FONTSIZE", (2, 0), (2, -1), 10),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#003366")),
                ("SPAN", (0, 0), (0, 2)),  # Le logo prend les 3 lignes
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(header_table)
            elements.append(Spacer(1, 30))


            # --- Nom enseignant ---
            elements.append(Paragraph(f"<b>Notes à</b>", ParagraphStyle(name="centered", parent=styles["Normal"], alignment=TA_CENTER)))
            elements.append(Spacer(1, 5))
            elements.append(Paragraph(f"<b>Mr/Mme {prenom} {nom}</b>", ParagraphStyle(name="centered", parent=styles["Heading2"], alignment=TA_CENTER)))
            elements.append(Spacer(1, 20))
            # --- Texte d'intro ---
            intro = ("Cher(e) collègue,<br/>"
                     "Vous êtes prié(e) d'assurer la surveillance et (ou) la responsabilité des examens selon le calendrier ci-joint.")
            elements.append(Paragraph(intro, styles["Normal"]))
            elements.append(Spacer(1, 20))

            # --- Tableau ---
            data = [["Date", "Heure", "Durée"]]
            for row in rows:
                h_debut = row["h_debut"]
                h_fin = row["h_fin"]

                # Calculer la durée
                from datetime import datetime
                fmt = "%H:%M"
                try:
                    h1 = datetime.strptime(h_debut, fmt)
                    h2 = datetime.strptime(h_fin, fmt)
                    duration = round((h2 - h1).seconds / 3600, 1)
                except Exception:
                    duration = "—"

                data.append([row["date_examen"], h_debut, f"{duration} H"])

            table = Table(data, colWidths=[120, 120, 120])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 30))

            footer_text = Paragraph("Merci de votre collaboration.", styles["Italic"])
            elements.append(footer_text)
            
           
            # Construire le PDF avec le footer
            doc.build(elements, onFirstPage=lambda c, d: add_footer(c, d, "assets/footer.png"),
                                onLaterPages=lambda c, d: add_footer(c, d, "assets/footer.png"))

        cursor.close()
        return jsonify({
            "message": f"Convocations générées avec succès pour la session {id_session}",
            "nombre_enseignants": len(enseignants)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@affectation_bp.route('/convocations/list/<int:id_session>', methods=['GET'])
def list_convocations_pdfs(id_session):
    """
    GET /api/affectations/convocations/list/<id_session> - Liste les convocations PDF pour une session
    
    Args:
        id_session: ID de la session
    
    Returns:
        JSON avec la liste des fichiers PDF de convocations disponibles
    """
    try:
        session_pdf_dir = os.path.join(PDF_DIR, f"session_{id_session}")
        
        if not os.path.exists(session_pdf_dir):
            return jsonify({
                "success": False,
                "message": f"Aucune convocation trouvée pour la session {id_session}",
                "files": []
            }), 404

        files = []
        from datetime import datetime
        
        for fname in sorted(os.listdir(session_pdf_dir)):
            if fname.lower().endswith('.pdf'):
                filepath = os.path.join(session_pdf_dir, fname)
                files.append({
                    "filename": fname,
                    "size": os.path.getsize(filepath),
                    "size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(os.path.getctime(filepath)).strftime('%Y-%m-%d %H:%M:%S'),
                    "download_url": f"/api/affectations/convocations/download/{id_session}/{fname}"
                })

        return jsonify({
            "success": True,
            "session_id": id_session,
            "count": len(files),
            "files": files
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@affectation_bp.route('/convocations/download/<int:id_session>/<path:filename>', methods=['GET'])
def download_convocation_pdf(id_session, filename):
    """
    GET /api/affectations/convocations/download/<id_session>/<filename> - Télécharge une convocation PDF
    
    Args:
        id_session: ID de la session
        filename: Nom du fichier PDF à télécharger
    
    Returns:
        Fichier PDF en téléchargement
    """
    try:
        # Sécurité : utiliser basename pour éviter les attaques path traversal
        safe_filename = os.path.basename(filename)
        filepath = os.path.join(PDF_DIR, f"session_{id_session}", safe_filename)
        
        if not os.path.exists(filepath):
            return jsonify({
                "success": False,
                "error": "Fichier non trouvé",
                "filepath": filepath
            }), 404
        
        return send_file(
            filepath,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=safe_filename
        )
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


# ========== ENDPOINTS PDF PRÉSENCE RESPONSABLES ==========

PRESENCE_PDF_DIR = os.path.join("results", "presences_responsables")

@affectation_bp.route("/generate_presences_responsables/<int:id_session>", methods=["GET"])
def generate_presences_responsables(id_session):
    """
    GET /api/affectations/generate_presences_responsables/<id_session>
    Génère les PDF de présence pour les responsables absents d'une session
    
    Ce endpoint génère un PDF pour chaque enseignant dans la table responsable_absent_jour_examen,
    listant les créneaux où il est responsable.
    """
    try:
        # Créer le dossier presences_responsables pour cette session s'il n'existe pas
        session_pdf_dir = os.path.join(PRESENCE_PDF_DIR, f"session_{id_session}")
        os.makedirs(session_pdf_dir, exist_ok=True)
        
        db = get_db()

        # Récupérer les responsables depuis la table responsable_absent_jour_examen
        cursor = db.execute("""
            SELECT DISTINCT code_smartex_ens, nom, prenom
            FROM responsable_absent_jour_examen
            WHERE id_session = ?
        """, (id_session,))
        responsables = cursor.fetchall()

        if not responsables:
            return jsonify({
                "message": f"Aucun responsable absent trouvé dans la table pour la session {id_session}"
            }), 404

        for resp in responsables:
            code = resp["code_smartex_ens"]
            nom = resp["nom"]
            prenom = resp["prenom"]

            # Récupérer tous les créneaux où cet enseignant est responsable
            cursor.execute("""
                SELECT dateExam, h_debut, h_fin, cod_salle, type_ex
                FROM creneau 
                WHERE id_session = ? AND enseignant = ?
                ORDER BY dateExam, h_debut
            """, (id_session, code))
            rows = cursor.fetchall()

            if not rows:
                # Si aucun créneau trouvé, passer au suivant
                continue

            # Créer le PDF dans le dossier de la session
            pdf_path = os.path.join(session_pdf_dir, f"presence_responsable_{nom}_{prenom}_{id_session}.pdf")
            doc = SimpleDocTemplate(pdf_path, pagesize=A4, 
                                   leftMargin=50, rightMargin=50,
                                   topMargin=100, bottomMargin=80)
            styles = getSampleStyleSheet()
            elements = []
            logo_path = "assets/logo.png"
            
            # Créer l'image du logo en gardant le ratio
            from PIL import Image as PILImage
            img = PILImage.open(logo_path)
            img_width, img_height = img.size
            aspect_ratio = img_height / img_width
            
            desired_width = 3*cm
            logo = RLImage(logo_path, width=desired_width, height=desired_width * aspect_ratio)
            
            date_approbation = datetime.now().strftime("%d%m-%y")
            
            # En-tête du document
            header_data = [
                [logo, "GESTION DES EXAMENS ET\n\n DÉLIBÉRATIONS\n", "EXD-FR-08-01"],
                ["", "Procédure d'exécution des épreuves", f"Date d'approbation\n{date_approbation}"],
                ["", "Liste des créneaux de présence des responsables", "Page 1/1"]
            ]
            
            header_table = Table(header_data, colWidths=[4*cm, 12*cm, 4*cm])
            header_table.setStyle(TableStyle([
                ("ALIGN", (0, 0), (0, -1), "CENTER"),
                ("ALIGN", (1, 0), (1, -1), "CENTER"),
                ("ALIGN", (2, 0), (2, -1), "CENTER"),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("FONTNAME", (1, 0), (1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (1, 0), (1, 0), 16),
                ("FONTSIZE", (1, 1), (1, 2), 12),
                ("FONTSIZE", (2, 0), (2, -1), 10),
                ("GRID", (0, 0), (-1, -1), 1, colors.black),
                ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#003366")),
                ("SPAN", (0, 0), (0, 2)),  # Le logo prend les 3 lignes
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]))
            elements.append(header_table)
            elements.append(Spacer(1, 30))

            # Nom du responsable
            elements.append(Paragraph(
                f"<b>Notes à</b>", 
                ParagraphStyle(name="centered", parent=styles["Normal"], alignment=TA_CENTER)
            ))
            elements.append(Spacer(1, 5))
            elements.append(Paragraph(
                f"<b>Mr/Mme {prenom} {nom}</b>", 
                ParagraphStyle(name="centered", parent=styles["Heading2"], alignment=TA_CENTER)
            ))
            elements.append(Spacer(1, 20))
            
            # Texte d'intro
            intro = ("Cher(e) collègue,<br/>"
                     "Vous êtes prié(e) d'assurer la responsabilité des examens selon le calendrier ci-joint.")
            elements.append(Paragraph(intro, styles["Normal"]))
            elements.append(Spacer(1, 20))

            # Tableau des créneaux de responsabilité
            data = [["Date", "Heure", "Durée"]]
            for row in rows:
                h_debut = row["h_debut"]
                h_fin = row["h_fin"]

                # Calculer la durée
                fmt = "%H:%M"
                try:
                    h1 = datetime.strptime(h_debut, fmt)
                    h2 = datetime.strptime(h_fin, fmt)
                    duration = round((h2 - h1).seconds / 3600, 1)
                except Exception:
                    duration = "—"

                data.append([row["dateExam"], h_debut, f"{duration} H"])

            table = Table(data, colWidths=[120, 120, 120])
            table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.lightblue),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
                ("ALIGN", (0, 0), (-1, -1), "CENTER"),
                ("GRID", (0, 0), (-1, -1), 0.5, colors.black),
                ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
            ]))
            elements.append(table)
            elements.append(Spacer(1, 30))

            footer_text = Paragraph("Merci de votre collaboration.", styles["Italic"])
            elements.append(footer_text)
            
            # Construire le PDF avec le footer
            doc.build(
                elements, 
                onFirstPage=lambda c, d: add_footer(c, d, "assets/footer.png"),
                onLaterPages=lambda c, d: add_footer(c, d, "assets/footer.png")
            )

        cursor.close()
        return jsonify({
            "message": f"PDF de présence des responsables générés avec succès pour la session {id_session}",
            "nombre_responsables": len(responsables),
            "dossier": session_pdf_dir
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@affectation_bp.route('/presences_responsables/list/<int:id_session>', methods=['GET'])
def list_presences_responsables_pdfs(id_session):
    """
    GET /api/affectations/presences_responsables/list/<id_session>
    Liste les PDF de présence des responsables pour une session
    """
    try:
        session_pdf_dir = os.path.join(PRESENCE_PDF_DIR, f"session_{id_session}")
        
        if not os.path.exists(session_pdf_dir):
            return jsonify({
                "success": False,
                "message": f"Aucun PDF de présence trouvé pour la session {id_session}",
                "files": []
            }), 404

        files = []
        
        for fname in sorted(os.listdir(session_pdf_dir)):
            if fname.lower().endswith('.pdf'):
                filepath = os.path.join(session_pdf_dir, fname)
                files.append({
                    "filename": fname,
                    "size": os.path.getsize(filepath),
                    "size_mb": round(os.path.getsize(filepath) / (1024 * 1024), 2),
                    "created": datetime.fromtimestamp(os.path.getctime(filepath)).strftime('%Y-%m-%d %H:%M:%S'),
                    "download_url": f"/api/affectations/presences_responsables/download/{id_session}/{fname}"
                })

        return jsonify({
            "success": True,
            "session_id": id_session,
            "count": len(files),
            "files": files
        }), 200
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@affectation_bp.route('/presences_responsables/download/<int:id_session>/<path:filename>', methods=['GET'])
def download_presence_responsable_pdf(id_session, filename):
    """
    GET /api/affectations/presences_responsables/download/<id_session>/<filename>
    Télécharge un PDF de présence responsable
    """
    try:
        # Sécurité : utiliser basename pour éviter les attaques path traversal
        safe_filename = os.path.basename(filename)
        filepath = os.path.join(PRESENCE_PDF_DIR, f"session_{id_session}", safe_filename)
        
        if not os.path.exists(filepath):
            return jsonify({
                "success": False,
                "error": "Fichier non trouvé",
                "filepath": filepath
            }), 404
        
        return send_file(
            filepath,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=safe_filename
        )
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500


@affectation_bp.route('/presences_responsables/download-multiple/<int:id_session>', methods=['POST'])
def download_multiple_presences_responsables(id_session):
    """
    POST /api/affectations/presences_responsables/download-multiple/<id_session>
    Télécharge plusieurs PDFs de présence responsables en un seul fichier ZIP
    
    Body JSON:
    {
        "filenames": ["presence_responsable_NOM1_Prenom1_4.pdf", "presence_responsable_NOM2_Prenom2_4.pdf"],
        "download_all": false  // Optionnel: si true, télécharge tous les PDFs
    }
    
    Returns:
        Fichier ZIP contenant les PDFs sélectionnés
    """
    try:
        data = request.get_json()
        
        if not data:
            return jsonify({
                'error': 'Corps de requête JSON requis',
                'expected': {
                    'filenames': ['file1.pdf', 'file2.pdf'],
                    'download_all': False
                }
            }), 400
        
        session_pdf_dir = os.path.join(PRESENCE_PDF_DIR, f"session_{id_session}")
        
        if not os.path.exists(session_pdf_dir):
            return jsonify({
                'error': f'Aucun PDF de présence trouvé pour la session {id_session}'
            }), 404
        
        download_all = data.get('download_all', False)
        
        # Déterminer les fichiers à inclure
        if download_all:
            # Télécharger tous les PDFs
            filenames = [f for f in os.listdir(session_pdf_dir) if f.lower().endswith('.pdf')]
        else:
            # Télécharger uniquement les fichiers sélectionnés
            if 'filenames' not in data or not data['filenames']:
                return jsonify({
                    'error': 'Liste de fichiers requise (filenames) ou utilisez download_all=true'
                }), 400
            filenames = data['filenames']
        
        if not filenames or len(filenames) == 0:
            return jsonify({
                'error': 'Aucun fichier à télécharger'
            }), 400
        
        # Créer un fichier ZIP en mémoire
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            added_files = []
            missing_files = []
            
            for filename in filenames:
                # Sécurité : utiliser basename
                safe_filename = os.path.basename(filename)
                filepath = os.path.join(session_pdf_dir, safe_filename)
                
                if os.path.exists(filepath):
                    # Ajouter le fichier au ZIP
                    zip_file.write(filepath, safe_filename)
                    added_files.append(safe_filename)
                else:
                    missing_files.append(safe_filename)
        
        # Si aucun fichier n'a été ajouté
        if len(added_files) == 0:
            return jsonify({
                'error': 'Aucun fichier valide trouvé',
                'missing_files': missing_files
            }), 404
        
        # Préparer le buffer pour l'envoi
        zip_buffer.seek(0)
        
        # Nom du fichier ZIP
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"presences_responsables_session_{id_session}_{timestamp}.zip"
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        return jsonify({
            'error': str(e)
        }), 500


@affectation_bp.route('/download-multiple', methods=['POST'])
def download_multiple_files():
    """
    POST /api/affectations/download-multiple - Télécharge plusieurs fichiers (PDFs ou CSVs) en un fichier ZIP
    
    Body JSON:
    {
        "session_id": 1,
        "files": [
            {"type": "convocation", "format": "pdf", "filename": "convocation_Nom_Prenom_1.pdf"},
            {"type": "convocation", "format": "csv", "filename": "convocation_Nom_Prenom_session_1.csv"},
            {"type": "affectation", "format": "pdf", "filename": "affectation_session_1_20250118_123456.pdf"},
            {"type": "affectation", "format": "csv", "filename": "affectations_global_session_1.csv"}
        ]
    }
    
    Types acceptés:
    - "convocation": Fichiers individuels de convocations
    - "affectation": Fichiers globaux d'affectations
    
    Formats acceptés:
    - "pdf": Fichiers PDF
    - "csv": Fichiers CSV
    
    Returns:
        Fichier ZIP contenant tous les fichiers sélectionnés
    """
    try:
        data = request.get_json()
        
        if not data or 'files' not in data or 'session_id' not in data:
            return jsonify({
                "success": False,
                "error": "Paramètres requis: session_id et files (array)"
            }), 400
        
        session_id = data['session_id']
        files_to_download = data['files']
        
        if not files_to_download or len(files_to_download) == 0:
            return jsonify({
                "success": False,
                "error": "La liste de fichiers est vide"
            }), 400
        
        # Créer un fichier ZIP en mémoire
        zip_buffer = BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            added_files = []
            missing_files = []
            
            for file_info in files_to_download:
                file_type = file_info.get('type')  # "convocation" ou "affectation"
                file_format = file_info.get('format', 'pdf')  # "pdf" ou "csv" (défaut: pdf)
                filename = file_info.get('filename')
                
                if not file_type or not filename:
                    missing_files.append({
                        "file": file_info,
                        "error": "Type ou filename manquant"
                    })
                    continue
                
                # Sécurité : utiliser basename
                safe_filename = os.path.basename(filename)
                
                # Déterminer le chemin selon le type et le format
                if file_type == "convocation":
                    if file_format == "pdf":
                        base_dir = PDF_DIR  # results/convocations
                        filepath = os.path.join(base_dir, f"session_{session_id}", safe_filename)
                        zip_folder = "convocations/pdf"
                    elif file_format == "csv":
                        base_dir = os.path.join('results', 'convocation_csv')
                        filepath = os.path.join(base_dir, f"session_{session_id}", safe_filename)
                        zip_folder = "convocations/csv"
                    else:
                        missing_files.append({
                            "file": file_info,
                            "error": f"Format inconnu: {file_format}"
                        })
                        continue
                        
                elif file_type == "affectation":
                    if file_format == "pdf":
                        base_dir = RESULTS_DIR  # results/affectations
                        filepath = os.path.join(base_dir, f"session_{session_id}", safe_filename)
                        zip_folder = "affectations/pdf"
                    elif file_format == "csv":
                        base_dir = os.path.join('results', 'affectation_csv')
                        filepath = os.path.join(base_dir, f"session_{session_id}", safe_filename)
                        zip_folder = "affectations/csv"
                    else:
                        missing_files.append({
                            "file": file_info,
                            "error": f"Format inconnu: {file_format}"
                        })
                        continue
                else:
                    missing_files.append({
                        "file": file_info,
                        "error": f"Type inconnu: {file_type}"
                    })
                    continue
                
                # Vérifier que le fichier existe
                if not os.path.exists(filepath):
                    missing_files.append({
                        "file": file_info,
                        "error": "Fichier non trouvé",
                        "path": filepath
                    })
                    continue
                
                # Ajouter le fichier au ZIP avec un dossier organisé
                arcname = os.path.join(zip_folder, safe_filename)
                zip_file.write(filepath, arcname)
                added_files.append(safe_filename)
        
        # Si aucun fichier n'a été ajouté
        if len(added_files) == 0:
            return jsonify({
                "success": False,
                "error": "Aucun fichier trouvé",
                "missing_files": missing_files
            }), 404
        
        # Préparer le buffer pour l'envoi
        zip_buffer.seek(0)
        
        # Nom du fichier ZIP
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        zip_filename = f"fichiers_session_{session_id}_{timestamp}.zip"
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ========== ENDPOINTS CSV - LISTE ET TÉLÉCHARGEMENT ==========

@affectation_bp.route('/csv/convocations/list/<int:session_id>', methods=['GET'])
def list_convocations_csv(session_id):
    """
    GET /api/affectations/csv/convocations/list/<session_id>
    Liste tous les fichiers CSV de convocations disponibles pour une session
    
    Returns:
        JSON avec la liste des fichiers CSV de convocations
    """
    try:
        csv_dir = os.path.join('results', 'convocation_csv', f'session_{session_id}')
        
        if not os.path.exists(csv_dir):
            return jsonify({
                "success": False,
                "error": f"Aucun CSV de convocation trouvé pour la session {session_id}",
                "path": csv_dir
            }), 404
        
        files = []
        for filename in os.listdir(csv_dir):
            if filename.endswith('.csv'):
                filepath = os.path.join(csv_dir, filename)
                file_stat = os.stat(filepath)
                files.append({
                    "filename": filename,
                    "size": file_stat.st_size,
                    "created": datetime.fromtimestamp(file_stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    "download_url": f"/api/affectations/csv/convocations/download/{session_id}/{filename}"
                })
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "count": len(files),
            "files": files
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@affectation_bp.route('/csv/convocations/download/<int:session_id>/<path:filename>', methods=['GET'])
def download_convocation_csv(session_id, filename):
    """
    GET /api/affectations/csv/convocations/download/<session_id>/<filename>
    Télécharge un fichier CSV de convocation spécifique
    
    Args:
        session_id: ID de la session
        filename: Nom du fichier CSV
        
    Returns:
        Fichier CSV
    """
    try:
        # Sécurité : utiliser basename
        safe_filename = os.path.basename(filename)
        
        csv_dir = os.path.join('results', 'convocation_csv', f'session_{session_id}')
        filepath = os.path.join(csv_dir, safe_filename)
        
        if not os.path.exists(filepath):
            return jsonify({
                "success": False,
                "error": "Fichier CSV non trouvé",
                "path": filepath
            }), 404
        
        return send_file(
            filepath,
            mimetype='text/csv',
            as_attachment=True,
            download_name=safe_filename
        )
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@affectation_bp.route('/csv/affectations/list/<int:session_id>', methods=['GET'])
def list_affectations_csv(session_id):
    """
    GET /api/affectations/csv/affectations/list/<session_id>
    Liste tous les fichiers CSV d'affectations disponibles pour une session
    
    Returns:
        JSON avec la liste des fichiers CSV d'affectations
    """
    try:
        csv_dir = os.path.join('results', 'affectation_csv', f'session_{session_id}')
        
        if not os.path.exists(csv_dir):
            return jsonify({
                "success": False,
                "error": f"Aucun CSV d'affectation trouvé pour la session {session_id}",
                "path": csv_dir
            }), 404
        
        files = []
        for filename in os.listdir(csv_dir):
            if filename.endswith('.csv'):
                filepath = os.path.join(csv_dir, filename)
                file_stat = os.stat(filepath)
                files.append({
                    "filename": filename,
                    "size": file_stat.st_size,
                    "created": datetime.fromtimestamp(file_stat.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                    "download_url": f"/api/affectations/csv/affectations/download/{session_id}/{filename}"
                })
        
        return jsonify({
            "success": True,
            "session_id": session_id,
            "count": len(files),
            "files": files
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


@affectation_bp.route('/csv/affectations/download/<int:session_id>/<path:filename>', methods=['GET'])
def download_affectation_csv(session_id, filename):
    """
    GET /api/affectations/csv/affectations/download/<session_id>/<filename>
    Télécharge un fichier CSV d'affectation spécifique
    
    Args:
        session_id: ID de la session
        filename: Nom du fichier CSV
        
    Returns:
        Fichier CSV
    """
    try:
        # Sécurité : utiliser basename
        safe_filename = os.path.basename(filename)
        
        csv_dir = os.path.join('results', 'affectation_csv', f'session_{session_id}')
        filepath = os.path.join(csv_dir, safe_filename)
        
        if not os.path.exists(filepath):
            return jsonify({
                "success": False,
                "error": "Fichier CSV non trouvé",
                "path": filepath
            }), 404
        
        return send_file(
            filepath,
            mimetype='text/csv',
            as_attachment=True,
            download_name=safe_filename
        )
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# Créer le dossier pour les affectations
RESULTS_DIR = 'results/affectations'

def format_date_fr(date_str):
    """Convertit une date en format français"""
    try:
        from datetime import datetime
        date_obj = datetime.strptime(date_str, '%Y-%m-%d')
        return date_obj.strftime('%d/%m/%Y')
    except:
        return date_str

def get_session_info(session_id):
    """Récupère les informations de la session"""
    db = get_db()
    session = db.execute('''
        SELECT * FROM session WHERE id_session = ?
    ''', (session_id,)).fetchone()
    return session

def get_affectations_by_session_for_pdf(session_id):
    """Récupère toutes les affectations groupées par date et séance"""
    db = get_db()
    affectations = db.execute('''
        SELECT 
            a.date_examen,
            a.seance,
            a.jour,
            e.nom_ens || ' ' || e.prenom_ens as enseignant_nom,
            c.cod_salle
        FROM affectation a
        JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
        LEFT JOIN creneau c ON a.creneau_id = c.creneau_id
        WHERE a.id_session = ?
        ORDER BY a.date_examen, a.seance, enseignant_nom
    ''', (session_id,)).fetchall()
    
    # Grouper par date et séance
    grouped = {}
    for row in affectations:
        key = (row['date_examen'], row['seance'])
        if key not in grouped:
            grouped[key] = []
        grouped[key].append({
            'enseignant': row['enseignant_nom'],
            'salle': row['cod_salle'] if row['cod_salle'] else ''
        })
    
    return grouped

def create_header_table():
    """Crée l'en-tête du document sous forme de tableau"""
    logo_path = "assets/logo.png"
    
    try:
        # Créer l'image du logo en gardant le ratio
        from PIL import Image as PILImage
        img = PILImage.open(logo_path)
        img_width, img_height = img.size
        aspect_ratio = img_height / img_width
        
        desired_width = 3*cm
        logo = RLImage(logo_path, width=desired_width, height=desired_width * aspect_ratio)
    except:
        # Si le logo n'existe pas, utiliser un texte
        logo = Paragraph("<b>LOGO</b>", getSampleStyleSheet()['Normal'])
    
    from datetime import datetime
    date_approbation = datetime.now().strftime("%d%m-%y")
    
    header_data = [
        [logo, "GESTION DES EXAMENS ET\n\nDÉLIBÉRATIONS\n", "EXD-FR-08-01"],
        ["", "Procédure d'exécution des épreuves", f"Date d'approbation\n{date_approbation}"],
        ["", "Liste d'affectation des surveillants", "Page 1/1"]
    ]
    
    header_table = Table(header_data, colWidths=[4*cm, 12*cm, 4*cm])
    header_table.setStyle(TableStyle([
        ("ALIGN", (0, 0), (0, -1), "CENTER"),
        ("ALIGN", (1, 0), (1, -1), "CENTER"),
        ("ALIGN", (2, 0), (2, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (1, 0), (1, 2), "Helvetica-Bold"),
        ("FONTSIZE", (1, 0), (1, 0), 14),
        ("FONTSIZE", (1, 1), (1, 2), 11),
        ("FONTSIZE", (2, 0), (2, -1), 10),
        ("GRID", (0, 0), (-1, -1), 1, colors.black),
        ("TEXTCOLOR", (1, 0), (1, -1), colors.HexColor("#003366")),
        ("SPAN", (0, 0), (0, 2)),  # Le logo prend les 3 lignes
        ("LEFTPADDING", (0, 0), (-1, -1), 8),
        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
    ]))
    
    return header_table

def create_footer_pdf(canvas, doc):
    """Crée le pied de page"""
    canvas.saveState()
    
    # Footer avec image si disponible
    try:
        footer = RLImage('assets/footer.png', width=18*cm, height=1.5*cm)
        footer.drawOn(canvas, 1.5*cm, 1*cm)
    except:
        # Si pas d'image, utiliser du texte
        canvas.setFont('Helvetica', 8)
        canvas.drawString(2*cm, 2*cm, "02 Rue Abou Raihane Bayrouni 2080 Ariana")
        canvas.drawString(2*cm, 1.5*cm, "Tél : 71706164  Email : ISI@isi.rnu.tn")
    
    canvas.restoreState()

def generate_affectation_pdf_file(session_id):
    """Génère le PDF d'affectation des surveillants et l'enregistre dans results/affectations/session_{id}"""
    
    # Créer le dossier affectations pour cette session s'il n'existe pas
    session_results_dir = os.path.join(RESULTS_DIR, f"session_{session_id}")
    os.makedirs(session_results_dir, exist_ok=True)
    
    # Récupérer les données
    session_info = get_session_info(session_id)
    if not session_info:
        raise ValueError("Session non trouvée")
    
    affectations_grouped = get_affectations_by_session_for_pdf(session_id)
    
    if not affectations_grouped:
        raise ValueError("Aucune affectation trouvée pour cette session")
    
    # Nom du fichier
    from datetime import datetime
    filename = f"affectation_session_{session_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    filepath = os.path.join(session_results_dir, filename)
    
    # Créer le document PDF
    doc = SimpleDocTemplate(
        filepath,
        pagesize=A4,
        topMargin=2*cm,
        bottomMargin=3*cm,
        leftMargin=2*cm,
        rightMargin=2*cm
    )
    
    # Styles
    styles = getSampleStyleSheet()
    
    style_info = ParagraphStyle(
        'Info',
        parent=styles['Normal'],
        fontSize=10,
        textColor=colors.black,
        spaceAfter=6,
        fontName='Helvetica'
    )
    
    # Liste pour stocker tous les éléments du PDF
    elements = []
    
    # Générer une page par date/séance
    sorted_keys = sorted(affectations_grouped.keys())
    
    for idx, (date_examen, seance) in enumerate(sorted_keys):
        # Ajouter un saut de page avant chaque séance (sauf la première)
        if idx > 0:
            from reportlab.platypus import PageBreak
            elements.append(PageBreak())
        
        # Ajouter l'en-tête pour cette page
        elements.append(create_header_table())
        elements.append(Spacer(1, 0.5*cm))
        
        # Informations de la session
        style_info_centered = ParagraphStyle(
        name="InfoCentered",
        parent=style_info,           # hérite de ton style existant
        alignment=TA_CENTER,         # centrage
        fontName="Helvetica-Bold"    # gras
        )


        info_text = f"AU : {session_info['AU']} – Semestre : {session_info['Semestre']} – Session : {session_info['type_session']}"
        elements.append(Paragraph(info_text, style_info_centered))
        elements.append(Spacer(1, 0.3*cm))
        
        # Info date et séance
        date_seance_text = f"Date : {format_date_fr(date_examen)} – Séance : {seance}"
        elements.append(Paragraph(date_seance_text, style_info))
        elements.append(Spacer(1, 0.5*cm))
        
        # Préparer les données du tableau
        data = [['Enseignant', 'Salle', 'Signature']]
        
        for affectation in affectations_grouped[(date_examen, seance)]:
            data.append([
                affectation['enseignant'],
                '',
                ''  # Colonne signature vide
            ])
        
        # Créer le tableau
        table = Table(data, colWidths=[8*cm, 3*cm, 5*cm])
        table.setStyle(TableStyle([
            # En-tête
            ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
            ('ALIGN', (0, 0), (-1, 0), 'CENTER'),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTSIZE', (0, 0), (-1, 0), 10),
            ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
            
            # Corps du tableau
            ('BACKGROUND', (0, 1), (-1, -1), colors.white),
            ('TEXTCOLOR', (0, 1), (-1, -1), colors.black),
            ('ALIGN', (0, 1), (0, -1), 'LEFT'),
            ('ALIGN', (1, 1), (-1, -1), 'CENTER'),
            ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
            ('FONTSIZE', (0, 1), (-1, -1), 9),
            ('ROWHEIGHT', (0, 1), (-1, -1), 0.8*cm),
            
            # Grille
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ]))
        
        elements.append(table)
    
    # Construction du PDF avec footer sur toutes les pages
    def add_page_footer(canvas, doc):
        create_footer_pdf(canvas, doc)
    
    doc.build(elements, onFirstPage=add_page_footer, onLaterPages=add_page_footer)
    
    return filepath, filename

@affectation_bp.route('/pdf/<int:session_id>', methods=['GET'])
def generate_affectation_pdf(session_id):
    """
    Endpoint pour générer le PDF d'affectation des surveillants
    et l'enregistrer dans le dossier results/affectations
    
    Args:
        session_id: ID de la session
    
    Returns:
        JSON avec le chemin du fichier généré
    """
    try:
        filepath, filename = generate_affectation_pdf_file(session_id)
        
        return jsonify({
            "success": True,
            "message": "PDF généré avec succès",
            "filepath": filepath,
            "filename": filename,
            "download_url": f"/api/affectations/download/{filename}"
        }), 200
    
    except ValueError as e:
        return jsonify({"success": False, "error": str(e), "session_id": session_id}), 404
    except Exception as e:
        import traceback
        return jsonify({
            "success": False, 
            "error": f"Erreur lors de la génération du PDF: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500

@affectation_bp.route('/download/<path:filename>', methods=['GET'])
def download_affectation_pdf(filename):
    """
    Endpoint pour télécharger un PDF d'affectation déjà généré
    
    Args:
        filename: Chemin du fichier PDF (peut inclure session_X/fichier.pdf)
    
    Returns:
        PDF file
    """
    try:
        filepath = os.path.join(RESULTS_DIR, filename)
        
        if not os.path.exists(filepath):
            return jsonify({"error": "Fichier non trouvé"}), 404
        
        # Extraire juste le nom du fichier pour le téléchargement
        actual_filename = os.path.basename(filepath)
        
        return send_file(
            filepath,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=actual_filename
        )
    
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@affectation_bp.route('/list-pdfs', methods=['GET'])
def list_affectation_pdfs():
    """
    Endpoint pour lister tous les PDFs d'affectation générés
    
    Returns:
        JSON avec la liste des fichiers
    """
    try:
        files = []
        if os.path.exists(RESULTS_DIR):
            # Parcourir les sous-dossiers session_*
            for session_folder in os.listdir(RESULTS_DIR):
                session_path = os.path.join(RESULTS_DIR, session_folder)
                if os.path.isdir(session_path) and session_folder.startswith('session_'):
                    for filename in os.listdir(session_path):
                        if filename.endswith('.pdf'):
                            filepath = os.path.join(session_path, filename)
                            from datetime import datetime
                            file_info = {
                                "filename": filename,
                                "filepath": filepath,
                                "size": os.path.getsize(filepath),
                                "created": datetime.fromtimestamp(os.path.getctime(filepath)).strftime('%Y-%m-%d %H:%M:%S'),
                                "download_url": f"/api/affectations/download/{session_folder}/{filename}"
                            }
                            files.append(file_info)
        
        files.sort(key=lambda x: x['created'], reverse=True)
        
        return jsonify({
            "success": True,
            "count": len(files),
            "files": files
        }), 200
    
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@affectation_bp.route('/preview/<int:session_id>', methods=['GET'])
def preview_affectation_data(session_id):
    """
    Endpoint pour prévisualiser les données d'affectation (format JSON)
    
    Args:
        session_id: ID de la session
    
    Returns:
        JSON avec les données d'affectation
    """
    try:
        session_info = get_session_info(session_id)
        if not session_info:
            return jsonify({"error": "Session non trouvée", "session_id": session_id}), 404
        
        affectations = get_affectations_by_session_for_pdf(session_id)
        
        result = {
            "session": {
                "id": session_info['id_session'],
                "libelle": session_info['libelle_session'],
                "AU": session_info['AU'],
                "semestre": session_info['Semestre'],
                "type": session_info['type_session'],
                "date_debut": session_info['date_debut'],
                "date_fin": session_info['date_fin']
            },
            "affectations": []
        }
        
        for (date_examen, seance), enseignants in sorted(affectations.items()):
            result["affectations"].append({
                "date": date_examen,
                "seance": seance,
                "enseignants": enseignants
            })
        
        return jsonify(result), 200
    
    except Exception as e:
        import traceback
        return jsonify({
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500

@affectation_bp.route('/permuter', methods=['POST'])
def permuter_affectations():
    """
    Permuter deux affectations (swap)
    Body: { affectation_id_1, affectation_id_2 }
    """
    try:
        data = request.get_json()
        id1 = data.get('affectation_id_1')
        id2 = data.get('affectation_id_2')
        if not id1 or not id2:
            return jsonify({'error': 'Les deux IDs d’affectation sont requis.'}), 400
        db = get_db()
        # Récupérer les deux affectations
        aff1 = db.execute('''
            SELECT a.*, c.cod_salle, c.dateExam, c.h_debut, c.h_fin, c.enseignant
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE a.rowid = ?
        ''', (id1,)).fetchone()
        aff2 = db.execute('''
            SELECT a.*, c.cod_salle, c.dateExam, c.h_debut, c.h_fin, c.enseignant
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE a.rowid = ?
        ''', (id2,)).fetchone()
        if not aff1 or not aff2:
            return jsonify({'error': 'Affectation(s) non trouvée(s).'}), 404
        # Impossible de permuter si même enseignant
        if aff1['code_smartex_ens'] == aff2['code_smartex_ens']:
            return jsonify({'error': 'Impossible de permuter : les deux affectations concernent le même enseignant.'}), 400
        # Vérifier que les deux affectations sont dans la même session
        if aff1['id_session'] != aff2['id_session']:
            return jsonify({'error': 'Impossible de permuter : les deux affectations ne sont pas dans la même session.'}), 400
        # Refuser uniquement si salle ET créneau identiques
        if (
            aff1['cod_salle'] == aff2['cod_salle'] and
            aff1['dateExam'] == aff2['dateExam'] and
            aff1['h_debut'] == aff2['h_debut'] and
            aff1['h_fin'] == aff2['h_fin']
        ):
            return jsonify({'error': 'Impossible de permuter : même salle et même créneau.'}), 400
        # Vérifier participation à la surveillance
        for aff in [aff1, aff2]:
            ens = db.execute('SELECT participe_surveillance FROM enseignant WHERE code_smartex_ens = ?', (aff['code_smartex_ens'],)).fetchone()
            if not ens or not ens['participe_surveillance']:
                return jsonify({'error': f"L'enseignant {aff['code_smartex_ens']} ne participe pas à la surveillance."}), 400
        # Vérifier conflits d’horaire pour chaque permutation
        def has_conflict(code_smartex_ens, creneau_id, exclude_ids):
            placeholders = ','.join(['?'] * len(exclude_ids))
            query = f'''
                SELECT COUNT(*) as count
                FROM affectation a1
                JOIN creneau c1 ON a1.creneau_id = c1.creneau_id
                JOIN creneau c2 ON c2.creneau_id = ?
                WHERE a1.code_smartex_ens = ?
                AND c1.dateExam = c2.dateExam
                AND ((c1.h_debut < c2.h_fin AND c1.h_fin > c2.h_debut))
                AND a1.rowid NOT IN ({placeholders})
            '''
            params = [creneau_id, code_smartex_ens] + exclude_ids
            return db.execute(query, params).fetchone()['count'] > 0
        # Vérifier pour aff1 dans le créneau de aff2
        if has_conflict(aff1['code_smartex_ens'], aff2['creneau_id'], [id1, id2]):
            return jsonify({'error': 'Conflit d’horaire pour le premier enseignant.'}), 409
        # Vérifier pour aff2 dans le créneau de aff1
        if has_conflict(aff2['code_smartex_ens'], aff1['creneau_id'], [id1, id2]):
            return jsonify({'error': 'Conflit d’horaire pour le second enseignant.'}), 409
        # Effectuer la permutation
        db.execute('UPDATE affectation SET code_smartex_ens = ? WHERE rowid = ?', (aff2['code_smartex_ens'], id1))
        db.execute('UPDATE affectation SET code_smartex_ens = ? WHERE rowid = ?', (aff1['code_smartex_ens'], id2))
        db.commit()
        return jsonify({'message': 'Permutation effectuée avec succès.'}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@affectation_bp.route('/csv/affectations/<int:session_id>', methods=['GET'])
def generate_affectations_csv(session_id):
    """
    Génère les fichiers CSV d'affectations globales pour une session
    (similaire à /pdf/<session_id>):
    - affectations_global_session_{id}.csv
    - affectations_jour_{n}_session_{id}.csv
    
    Args:
        session_id: ID de la session
    
    Returns:
        JSON avec la liste des fichiers générés
    """
    try:
        db = get_db()
        
        # Vérifier que la session existe
        session = db.execute('SELECT * FROM session WHERE id_session = ?', (session_id,)).fetchone()
        if not session:
            return jsonify({
                "success": False,
                "error": f"Session {session_id} non trouvée"
            }), 404
        
        # Récupérer toutes les affectations de la session
        query = '''
            SELECT 
                a.code_smartex_ens,
                e.nom_ens,
                e.prenom_ens,
                e.grade_code_ens,
                c.dateExam as date,
                c.h_debut,
                c.h_fin,
                c.cod_salle,
                c.type_ex,
                a.position,
                a.jour,
                a.seance
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE c.id_session = ?
            ORDER BY c.dateExam, c.h_debut, c.cod_salle, e.nom_ens
        '''
        
        affectations = db.execute(query, (session_id,)).fetchall()
        
        if not affectations:
            return jsonify({
                "success": False,
                "error": f"Aucune affectation trouvée pour la session {session_id}"
            }), 404
        
        # Convertir en DataFrame
        aff_df = pd.DataFrame([dict(row) for row in affectations])
        
        # Créer le dossier pour cette session
        affectation_csv_dir = os.path.join('results', 'affectation_csv', f'session_{session_id}')
        os.makedirs(affectation_csv_dir, exist_ok=True)
        
        files_generated = []
        
        # 1. Affectation globale
        out_global = os.path.join(affectation_csv_dir, f'affectations_global_session_{session_id}.csv')
        aff_df.to_csv(out_global, index=False, encoding='utf-8')
        files_generated.append(out_global)
        print(f"✓ {out_global}")
        
        # 2. Fichiers par jour
        jours_count = 0
        if 'jour' in aff_df.columns:
            for jour in sorted(aff_df['jour'].unique()):
                if pd.notna(jour):
                    jour_df = aff_df[aff_df['jour'] == jour].copy()
                    out = os.path.join(affectation_csv_dir, f'affectations_jour_{int(jour)}_session_{session_id}.csv')
                    jour_df.to_csv(out, index=False, encoding='utf-8')
                    files_generated.append(out)
                    jours_count += 1
                    print(f"✓ {out}")
        
        return jsonify({
            "success": True,
            "message": f"CSV d'affectations générés avec succès pour la session {session_id}",
            "session_id": session_id,
            "files_count": len(files_generated),
            "affectations_count": len(aff_df),
            "jours_count": jours_count,
            "directory": affectation_csv_dir,
            "files": files_generated
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": f"Erreur lors de la génération des CSV d'affectations: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500


@affectation_bp.route('/csv/convocations/<int:session_id>', methods=['GET'])
def generate_convocations_csv(session_id):
    """
    Génère les fichiers CSV de convocations individuelles pour une session
    (similaire à /generate_convocations/<session_id>):
    - convocation_{nom}_{prenom}_session_{id}.csv (un par enseignant)
    
    Args:
        session_id: ID de la session
    
    Returns:
        JSON avec la liste des fichiers générés
    """
    try:
        db = get_db()
        
        # Vérifier que la session existe
        session = db.execute('SELECT * FROM session WHERE id_session = ?', (session_id,)).fetchone()
        if not session:
            return jsonify({
                "success": False,
                "error": f"Session {session_id} non trouvée"
            }), 404
        
        # Récupérer toutes les affectations de la session
        query = '''
            SELECT 
                a.code_smartex_ens,
                e.nom_ens,
                e.prenom_ens,
                e.grade_code_ens,
                c.dateExam as date,
                c.h_debut,
                c.h_fin,
                c.cod_salle,
                c.type_ex,
                a.position,
                a.jour,
                a.seance
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE c.id_session = ?
            ORDER BY c.dateExam, c.h_debut, c.cod_salle
        '''
        
        affectations = db.execute(query, (session_id,)).fetchall()
        
        if not affectations:
            return jsonify({
                "success": False,
                "error": f"Aucune affectation trouvée pour la session {session_id}"
            }), 404
        
        # Convertir en DataFrame
        aff_df = pd.DataFrame([dict(row) for row in affectations])
        
        # Créer le dossier pour cette session
        convocation_csv_dir = os.path.join('results', 'convocation_csv', f'session_{session_id}')
        os.makedirs(convocation_csv_dir, exist_ok=True)
        
        files_generated = []
        
        # Générer une convocation par enseignant
        convocations_generated = 0
        for code in aff_df['code_smartex_ens'].unique():
            ens_df = aff_df[aff_df['code_smartex_ens'] == code].copy()
            nom = ens_df.iloc[0]['nom_ens']
            prenom = ens_df.iloc[0]['prenom_ens']
            out = os.path.join(convocation_csv_dir, f'convocation_{code}_{nom}_{prenom}_session_{session_id}.csv')
            ens_df.to_csv(out, index=False, encoding='utf-8')
            files_generated.append(out)
            convocations_generated += 1
            print(f"✓ {out}")
        
        return jsonify({
            "success": True,
            "message": f"CSV de convocations générés avec succès pour la session {session_id}",
            "session_id": session_id,
            "files_count": len(files_generated),
            "convocations_count": convocations_generated,
            "directory": convocation_csv_dir,
            "files": files_generated[:10]  # Limiter la liste pour ne pas surcharger la réponse
        }), 200
        
    except Exception as e:
        import traceback
        return jsonify({
            "success": False,
            "error": f"Erreur lors de la génération des CSV de convocations: {str(e)}",
            "traceback": traceback.format_exc()
        }), 500
