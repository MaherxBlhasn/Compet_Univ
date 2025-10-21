from flask import Blueprint, request, jsonify
import json
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from email.utils import formataddr
import json
import re
# Création du blueprint
email_bp = Blueprint("email_bp", __name__)

# Fichier où la configuration sera sauvegardée
CONFIG_FILE = "email_config.json"


def save_email_config(data):
    """Sauvegarde la configuration dans un fichier JSON"""
    with open(CONFIG_FILE, "w") as f:
        json.dump(data, f, indent=4)


def load_email_config():
    """Charge la configuration si elle existe"""
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f:
            return json.load(f)
    return {}


@email_bp.route("/config", methods=["POST"])
def set_email_config():
    """
    Enregistre la configuration SMTP envoyée par le frontend
    Ex : POST /api/email/config
    """
    data = request.json

    required_fields = [
        "SMTP_SERVER", "SMTP_PORT", "SMTP_USER",
        "SMTP_PASSWORD", "FROM_EMAIL", "FROM_NAME"
    ]

    # Vérification des champs manquants
    missing = [field for field in required_fields if field not in data]
    if missing:
        return jsonify({"error": f"Champs manquants : {', '.join(missing)}"}), 400

    # Sauvegarde dans un fichier JSON
    save_email_config(data)

    return jsonify({
        "message": "✅ Configuration email enregistrée avec succès",
        "config": data
    }), 200


@email_bp.route("/config", methods=["GET"])
def get_email_config():
    """
    Retourne la configuration SMTP enregistrée
    Ex : GET /api/email/config
    """
    config = load_email_config()
    if not config:
        return jsonify({"message": "Aucune configuration trouvée"}), 404
    return jsonify(config), 200


@email_bp.route("/test", methods=["POST"])
def test_email():
    """
    Teste l'envoi d'un email avec la configuration sauvegardée
    Reçoit : {"to": "destinataire@example.com"}
    """
    import smtplib
    from email.mime.text import MIMEText

    config = load_email_config()
    if not config:
        return jsonify({"error": "Configuration SMTP non trouvée"}), 400

    data = request.json or {}
    to_email = data.get("to")
    if not to_email:
        return jsonify({"error": "Le champ 'to' est requis"}), 400

    try:
        # Créer le message de test
        msg = MIMEText("Ceci est un email de test envoyé depuis l'application Flask.")
        msg["Subject"] = "Test de configuration SMTP"
        msg["From"] = f"{config['FROM_NAME']} <{config['FROM_EMAIL']}>"
        msg["To"] = to_email

        # Connexion et envoi
        with smtplib.SMTP(config["SMTP_SERVER"], config["SMTP_PORT"]) as server:
            server.starttls()
            server.login(config["SMTP_USER"], config["SMTP_PASSWORD"])
            server.send_message(msg)

        return jsonify({"message": f"✅ Email de test envoyé à {to_email}"}), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

PDF_DIR = os.path.join("results", "convocations")
# Charger la configuration email depuis le fichier JSON
def load_email_config():
    """Charge la configuration email depuis email_config.json"""
    try:
        with open('email_config.json', 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        raise Exception("Fichier email_config.json non trouvé")
    except json.JSONDecodeError:
        raise Exception("Erreur de format dans email_config.json")

def extract_code_smartex_from_filename(filename):
    """
    Extrait le code_smartex_ens du nom de fichier
    Format attendu: convocation_{code_smartex_ens}_{nom}_{prenom}_{session_id}.pdf
    
    Args:
        filename: Nom du fichier (ex: convocation_3_Arous_Najet_1.pdf)
    
    Returns:
        int: code_smartex_ens ou None si non trouvé
    """
    try:
        # Pattern pour extraire le code après "convocation_"
        match = re.match(r'convocation_(\d+)_', filename)
        if match:
            return int(match.group(1))
        return None
    except Exception:
        return None

def send_email_with_pdf(to_email, to_name, subject, body, pdf_path, pdf_filename, email_config):
    """
    Envoie un email avec un PDF en pièce jointe
    
    Args:
        to_email: Email du destinataire
        to_name: Nom du destinataire
        subject: Sujet de l'email
        body: Corps de l'email (HTML)
        pdf_path: Chemin complet vers le PDF
        pdf_filename: Nom du fichier PDF
        email_config: Configuration SMTP
    
    Returns:
        tuple: (success: bool, message: str)
    """
    try:
        # Créer le message
        msg = MIMEMultipart()
        msg['From'] = formataddr((email_config['FROM_NAME'], email_config['FROM_EMAIL']))
        msg['To'] = formataddr((to_name, to_email))
        msg['Subject'] = subject
        
        # Ajouter le corps du message
        msg.attach(MIMEText(body, 'html'))
        
        # Ajouter la pièce jointe PDF
        if pdf_path and os.path.exists(pdf_path):
            with open(pdf_path, 'rb') as f:
                pdf = MIMEApplication(f.read(), _subtype='pdf')
                pdf.add_header('Content-Disposition', 'attachment', filename=pdf_filename)
                msg.attach(pdf)
        else:
            return False, f"Fichier PDF non trouvé: {pdf_path}"
        
        # Connexion au serveur SMTP et envoi
        with smtplib.SMTP(email_config['SMTP_SERVER'], email_config['SMTP_PORT']) as server:
            server.starttls()
            server.login(email_config['SMTP_USER'], email_config['SMTP_PASSWORD'])
            server.send_message(msg)
        
        return True, "Email envoyé avec succès"
    
    except smtplib.SMTPAuthenticationError:
        return False, "Erreur d'authentification SMTP - Vérifiez vos identifiants"
    except smtplib.SMTPException as e:
        return False, f"Erreur SMTP: {str(e)}"
    except Exception as e:
        return False, f"Erreur lors de l'envoi: {str(e)}"

def create_convocation_email_body(enseignant_nom, enseignant_prenom):
    """
    Crée le corps HTML de l'email de convocation
    
    Args:
        enseignant_nom: Nom de l'enseignant
        enseignant_prenom: Prénom de l'enseignant
    
    Returns:
        str: Corps HTML de l'email
    """
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <style>
            body {{ font-family: Arial, sans-serif; line-height: 1.6; color: #333; }}
            .container {{ max-width: 600px; margin: 0 auto; padding: 20px; }}
            .header {{ background-color: #003366; color: white; padding: 20px; text-align: center; border-radius: 5px 5px 0 0; }}
            .content {{ padding: 30px; background-color: #f9f9f9; border: 1px solid #ddd; }}
            .footer {{ text-align: center; padding: 20px; font-size: 12px; color: #666; background-color: #f0f0f0; border-radius: 0 0 5px 5px; }}
            .button {{ display: inline-block; padding: 10px 20px; background-color: #003366; color: white; text-decoration: none; border-radius: 5px; margin: 10px 0; }}
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h2>Convocation Surveillance des Examens</h2>
            </div>
            <div class="content">
                <p>Bonjour <strong>{enseignant_prenom} {enseignant_nom}</strong>,</p>
                
                <p>Vous trouverez ci-joint votre convocation pour la surveillance des examens.</p>
                
                <p>Ce document contient :</p>
                <ul>
                    <li>Les dates de vos surveillances</li>
                    <li>Les horaires des séances</li>
                    <li>La durée de chaque surveillance</li>
                </ul>
                
                <p><strong>Merci de consulter attentivement votre convocation et de vous présenter aux dates et heures indiquées.</strong></p>
                
                <p>Pour toute question ou modification, veuillez contacter le service des examens.</p>
                
                <p>Cordialement,<br>
                <strong>Le Service de Gestion des Examens</strong></p>
            </div>
            <div class="footer">
                <p><strong>Institut Supérieur d'Informatique (ISI)</strong><br>
                02 Rue Abou Raihane Bayrouni 2080 Ariana<br>
                Tél : 71706164 | Email : ISI@isi.rnu.tn</p>
            </div>
        </div>
    </body>
    </html>
    """
    return html

@email_bp.route('/send-convocations', methods=['POST'])
def send_convocations_by_filenames():
    """
    Envoie les convocations par email en fonction d'une liste de noms de fichiers
    
    Body JSON:
        {
            "session_id": 1,
            "filenames": [
                "convocation_3_Arous_Najet_1.pdf",
                "convocation_7_Salhi_Salah_1.pdf"
            ]
        }
    
    Returns:
        JSON avec le statut des envois
    """
    try:
        data = request.get_json()
        
        if not data or 'filenames' not in data or 'session_id' not in data:
            return jsonify({
                'error': 'Champs requis: session_id et filenames (liste)'
            }), 400
        
        session_id = data['session_id']
        filenames = data['filenames']
        
        if not isinstance(filenames, list) or len(filenames) == 0:
            return jsonify({
                'error': 'filenames doit être une liste non vide'
            }), 400
        
        # Charger la configuration email
        try:
            email_config = load_email_config()
        except Exception as e:
            return jsonify({
                'error': f'Erreur de configuration email: {str(e)}'
            }), 500
        from database.database import get_db
        db = get_db()
        
        results = {
            'success': [],
            'errors': [],
            'skipped': []
        }
        
        # Parcourir tous les fichiers
        for filename in filenames:
            try:
                # Extraire le code_smartex_ens du nom de fichier
                code_smartex_ens = extract_code_smartex_from_filename(filename)
                
                if code_smartex_ens is None:
                    results['skipped'].append({
                        'filename': filename,
                        'reason': 'Impossible d\'extraire le code enseignant du nom de fichier'
                    })
                    continue
                
                # Récupérer l'enseignant depuis la base de données
                cursor = db.execute('''
                    SELECT code_smartex_ens, nom_ens, prenom_ens, email_ens
                    FROM enseignant
                    WHERE code_smartex_ens = ?
                ''', (code_smartex_ens,))
                enseignant = cursor.fetchone()
                
                if not enseignant:
                    results['skipped'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'reason': 'Enseignant non trouvé dans la base de données'
                    })
                    continue
                
                # Vérifier si l'email existe
                if not enseignant['email_ens']:
                    results['skipped'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'enseignant': f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                        'reason': 'Email non renseigné'
                    })
                    continue
                
                # Construire le chemin complet du PDF
                pdf_path = os.path.join(PDF_DIR, f"session_{session_id}", filename)
                
                # Vérifier si le fichier existe
                if not os.path.exists(pdf_path):
                    results['errors'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'enseignant': f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                        'email': enseignant['email_ens'],
                        'error': f'Fichier PDF non trouvé: {pdf_path}'
                    })
                    continue
                
                # Créer le corps de l'email
                email_body = create_convocation_email_body(
                    enseignant['nom_ens'],
                    enseignant['prenom_ens']
                )
                
                # Sujet de l'email
                subject = "Convocation - Surveillance des Examens"
                
                # Envoyer l'email
                success, message = send_email_with_pdf(
                    to_email=enseignant['email_ens'],
                    to_name=f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                    subject=subject,
                    body=email_body,
                    pdf_path=pdf_path,
                    pdf_filename=filename,
                    email_config=email_config
                )
                
                if success:
                    results['success'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'enseignant': f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                        'email': enseignant['email_ens'],
                        'message': message
                    })
                else:
                    results['errors'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'enseignant': f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                        'email': enseignant['email_ens'],
                        'error': message
                    })
                
            except Exception as e:
                results['errors'].append({
                    'filename': filename,
                    'error': f'Erreur lors du traitement: {str(e)}'
                })
        
        return jsonify({
            'message': 'Envoi des convocations terminé',
            'total_files': len(filenames),
            'success_count': len(results['success']),
            'error_count': len(results['errors']),
            'skipped_count': len(results['skipped']),
            'details': results
        }), 200
    
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@email_bp.route('/send-convocations-all/<int:session_id>', methods=['POST'])
def send_all_convocations_for_session(session_id):
    """
    Envoie toutes les convocations d'une session automatiquement
    Lit tous les fichiers PDF du dossier results/convocations/{session_id}/
    
    Args:
        session_id: ID de la session
    
    Returns:
        JSON avec le statut des envois
    """
    try:
        # Charger la configuration email
        try:
            email_config = load_email_config()
        except Exception as e:
            return jsonify({
                'error': f'Erreur de configuration email: {str(e)}'
            }), 500
        
        # Chemin du dossier des convocations
        convocations_dir = os.path.join(PDF_DIR, str(session_id))
        
        if not os.path.exists(convocations_dir):
            return jsonify({
                'error': f'Dossier de convocations non trouvé: {convocations_dir}'
            }), 404
        
        # Lister tous les fichiers PDF
        pdf_files = [f for f in os.listdir(convocations_dir) if f.endswith('.pdf')]
        
        if not pdf_files:
            return jsonify({
                'error': f'Aucun fichier PDF trouvé dans {convocations_dir}'
            }), 404
        from database.database import get_db
        db = get_db()
        
        results = {
            'success': [],
            'errors': [],
            'skipped': []
        }
        
        # Parcourir tous les fichiers PDF
        for filename in pdf_files:
            try:
                # Extraire le code_smartex_ens
                code_smartex_ens = extract_code_smartex_from_filename(filename)
                
                if code_smartex_ens is None:
                    results['skipped'].append({
                        'filename': filename,
                        'reason': 'Format de fichier invalide'
                    })
                    continue
                
                # Récupérer l'enseignant
                cursor = db.execute('''
                    SELECT code_smartex_ens, nom_ens, prenom_ens, email_ens
                    FROM enseignant
                    WHERE code_smartex_ens = ?
                ''', (code_smartex_ens,))
                enseignant = cursor.fetchone()
                
                if not enseignant:
                    results['skipped'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'reason': 'Enseignant non trouvé'
                    })
                    continue
                
                if not enseignant['email_ens']:
                    results['skipped'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'enseignant': f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                        'reason': 'Email non renseigné'
                    })
                    continue
                
                # Chemin complet du PDF
                pdf_path = os.path.join(convocations_dir, filename)
                
                # Créer le corps de l'email
                email_body = create_convocation_email_body(
                    enseignant['nom_ens'],
                    enseignant['prenom_ens']
                )
                
                subject = "Convocation - Surveillance des Examens"
                
                # Envoyer l'email
                success, message = send_email_with_pdf(
                    to_email=enseignant['email_ens'],
                    to_name=f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                    subject=subject,
                    body=email_body,
                    pdf_path=pdf_path,
                    pdf_filename=filename,
                    email_config=email_config
                )
                
                if success:
                    results['success'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'enseignant': f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                        'email': enseignant['email_ens']
                    })
                else:
                    results['errors'].append({
                        'filename': filename,
                        'code_smartex_ens': code_smartex_ens,
                        'enseignant': f"{enseignant['prenom_ens']} {enseignant['nom_ens']}",
                        'email': enseignant['email_ens'],
                        'error': message
                    })
                
            except Exception as e:
                results['errors'].append({
                    'filename': filename,
                    'error': str(e)
                })
        
        return jsonify({
            'message': 'Envoi des convocations terminé',
            'session_id': session_id,
            'total_files': len(pdf_files),
            'success_count': len(results['success']),
            'error_count': len(results['errors']),
            'skipped_count': len(results['skipped']),
            'details': results
        }), 200
    
    except Exception as e:
        import traceback
        return jsonify({
            'error': str(e),
            'traceback': traceback.format_exc()
        }), 500

@email_bp.route('/test-email-config', methods=['POST'])
def test_email_configuration():
    """
    Teste la configuration email
    
    Body JSON:
        {
            "to_email": "test@example.com"
        }
    
    Returns:
        JSON avec le résultat du test
    """
    try:
        data = request.get_json()
        
        if not data or 'to_email' not in data:
            return jsonify({'error': 'Email destinataire requis'}), 400
        
        # Charger la configuration
        try:
            email_config = load_email_config()
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'Erreur de chargement de la configuration: {str(e)}'
            }), 500
        
        to_email = data['to_email']
        
        subject = "Test - Configuration Email ISI"
        body = """
        <!DOCTYPE html>
        <html>
        <body style="font-family: Arial, sans-serif; padding: 20px;">
            <h2 style="color: #003366;">Test de Configuration Email</h2>
            <p>Ceci est un email de test pour vérifier la configuration SMTP.</p>
            <p><strong>Si vous recevez cet email, la configuration fonctionne correctement ✓</strong></p>
            <hr>
            <p style="font-size: 12px; color: #666;">
                Institut Supérieur d'Informatique (ISI)<br>
                02 Rue Abou Raihane Bayrouni 2080 Ariana
            </p>
        </body>
        </html>
        """
        
        # Tester l'envoi
        msg = MIMEMultipart()
        msg['From'] = formataddr((email_config['FROM_NAME'], email_config['FROM_EMAIL']))
        msg['To'] = to_email
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'html'))
        
        with smtplib.SMTP(email_config['SMTP_SERVER'], email_config['SMTP_PORT']) as server:
            server.starttls()
            server.login(email_config['SMTP_USER'], email_config['SMTP_PASSWORD'])
            server.send_message(msg)
        
        return jsonify({
            'success': True,
            'message': 'Email de test envoyé avec succès',
            'to_email': to_email,
            'config': {
                'server': email_config['SMTP_SERVER'],
                'port': email_config['SMTP_PORT'],
                'from': email_config['FROM_EMAIL']
            }
        }), 200
    
    except smtplib.SMTPAuthenticationError:
        return jsonify({
            'success': False,
            'error': 'Erreur d\'authentification SMTP - Vérifiez SMTP_USER et SMTP_PASSWORD'
        }), 500
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500



@email_bp.route("/update-email", methods=["POST"])
def update_email():
    """
    Met à jour l'email d'un enseignant dans la table 'enseignant'
    JSON attendu :
    {
        "code_smartex_ens": 123,
        "new_email": "nouveau@mail.com"
    }
    """
    data = request.json or {}
    code_smartex_ens = data.get("code_smartex_ens")
    new_email = data.get("new_email")

    # Validation basique
    if not code_smartex_ens or not new_email:
        return jsonify({"error": "code_smartex_ens et new_email sont requis"}), 400

    try:
        from database.database import get_db
        conn =get_db()
        cursor = conn.cursor()

        # Vérifier si l'enseignant existe
        cursor.execute("SELECT * FROM enseignant WHERE code_smartex_ens = ?", (code_smartex_ens,))
        enseignant = cursor.fetchone()

        if not enseignant:
            return jsonify({"error": f"Enseignant avec code_smartex_ens {code_smartex_ens} non trouvé"}), 404

        # Mise à jour de l'email
        cursor.execute(
            "UPDATE enseignant SET email_ens = ? WHERE code_smartex_ens = ?",
            (new_email, code_smartex_ens)
        )
        conn.commit()
        conn.close()

        return jsonify({
            "message": f"Email de l'enseignant {code_smartex_ens} mis à jour avec succès",
            "code_smartex_ens": code_smartex_ens,
            "new_email": new_email
        }), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500
