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
    # Supprimer les anciennes entrées pour cette session
    db.execute('DELETE FROM responsable_absent_jour_examen WHERE id_session = ?', (id_session,))
    # Récupérer tous les responsables absents et compter le nombre de créneaux
    rows = db.execute('''
        SELECT c.enseignant as responsable, COUNT(*) as nbre_creneaux
        FROM creneau c
        LEFT JOIN affectation a ON c.creneau_id = a.creneau_id AND a.code_smartex_ens = c.enseignant AND a.id_session = c.id_session
        WHERE c.id_session = ? AND c.enseignant IS NOT NULL AND a.code_smartex_ens IS NULL
        GROUP BY c.enseignant
    ''', (id_session,)).fetchall()
    for row in rows:
        resp_code = row['responsable']
        nbre_creneaux = row['nbre_creneaux']
        ens = db.execute('''
            SELECT participe_surveillance, nom_ens, prenom_ens
            FROM enseignant
            WHERE code_smartex_ens = ?
        ''', (resp_code,)).fetchone()
        participe_surveillance = ens['participe_surveillance'] if ens else 0
        nom = ens['nom_ens'] if ens else ''
        prenom = ens['prenom_ens'] if ens else ''
        db.execute('''
            INSERT INTO responsable_absent_jour_examen (
                id_session, code_smartex_ens, participe_surveillance, nom, prenom, nbre_creneaux
            ) VALUES (?, ?, ?, ?, ?, ?)
        ''', (
            id_session,
            resp_code,
            participe_surveillance,
            nom,
            prenom,
            nbre_creneaux
        ))
    db.commit()
