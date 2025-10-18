import sqlite3
from flask import g
from config import Config

def get_db():
    """Obtenir une connexion à la base de données"""
    if 'db' not in g:
        g.db = sqlite3.connect(Config.DB_NAME)
        g.db.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par nom
    return g.db

def close_db(e=None):
    """Fermer la connexion à la base de données"""
    db = g.pop('db', None)
    if db is not None:
        db.close()

def init_db(app):
    """Initialiser la base de données"""
    app.teardown_appcontext(close_db)

def remplir_responsables_absents(id_session):
    """
    Remplit la table responsable_absent_jour_examen pour les responsables qui ne sont pas présents le jour de leur examen
    """
    db = get_db()
    # Récupérer tous les créneaux où il y a un responsable
    creneaux_resp = db.execute('''
        SELECT creneau_id, dateExam, h_debut, h_fin, cod_salle, enseignant as responsable
        FROM creneau
        WHERE id_session = ? AND enseignant IS NOT NULL
    ''', (id_session,)).fetchall()
    for creneau in creneaux_resp:
        resp_code = creneau['responsable']
        # Vérifier si le responsable a une affectation le jour de son examen
        affectation = db.execute('''
            SELECT 1 FROM affectation
            WHERE id_session = ? AND code_smartex_ens = ? AND creneau_id = ?
        ''', (id_session, resp_code, creneau['creneau_id'])).fetchone()
        if not affectation:
            # Récupérer les infos de l'enseignant
            ens = db.execute('''
                SELECT participe_surveillance, nom_ens, prenom_ens
                FROM enseignant
                WHERE code_smartex_ens = ?
            ''', (resp_code,)).fetchone()
            participe_surveillance = ens['participe_surveillance'] if ens else 0
            nom = ens['nom_ens'] if ens else ''
            prenom = ens['prenom_ens'] if ens else ''
            # Insérer dans la table responsable_absent_jour_examen
            db.execute('''
                INSERT INTO responsable_absent_jour_examen (
                    id_session, code_smartex_ens, creneau_id, date_exam, h_debut, h_fin, cod_salle, participe_surveillance, nom, prenom
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                id_session,
                resp_code,
                creneau['creneau_id'],
                creneau['dateExam'],
                creneau['h_debut'],
                creneau['h_fin'],
                creneau['cod_salle'],
                participe_surveillance,
                nom,
                prenom
            ))
    db.commit()
