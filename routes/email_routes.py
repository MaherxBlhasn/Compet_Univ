from flask import Blueprint, request, jsonify
import json
import os

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
