import sqlite3
from flask import g
from config import Config

def get_db():
    """Obtenir une connexion à la base de données"""
    if 'db' not in g:
        g.db = sqlite3.connect(Config.DB_NAME)
        g.db.row_factory = sqlite3.Row  # Permet d'accéder aux colonnes par nom
        # IMPORTANT : Activer les contraintes de clés étrangères (nécessaire pour ON DELETE CASCADE)
        g.db.execute("PRAGMA foreign_keys = ON")
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
    Remplit la table responsable_absent_jour_examen pour les responsables qui ne sont PAS présents 
    LE JOUR de leur examen (vérifie la présence sur toute la journée, pas juste le créneau).
    
    Un responsable est considéré comme absent si :
    - Il est responsable d'un examen à une date donnée
    - Il n'a AUCUNE affectation de surveillance à cette même date
    
    Calcule également :
    - Nombre de jours absents vs total de jours où il est responsable
    - Nombre de créneaux absents vs total de créneaux où il est responsable
    """
    db = get_db()
    
    # Supprimer les anciennes entrées pour cette session
    db.execute('DELETE FROM responsable_absent_jour_examen WHERE id_session = ?', (id_session,))
    
    # Récupérer tous les responsables avec leurs dates d'examens
    rows = db.execute('''
        SELECT 
            c.enseignant as responsable,
            c.dateExam,
            COUNT(*) as nbre_creneaux_ce_jour
        FROM creneau c
        WHERE c.id_session = ? 
            AND c.enseignant IS NOT NULL
        GROUP BY c.enseignant, c.dateExam
    ''', (id_session,)).fetchall()
    
    # Dictionnaire pour stocker les infos par responsable
    responsables_data = {}
    
    for row in rows:
        resp_code = row['responsable']
        date_exam = row['dateExam']
        nbre_creneaux = row['nbre_creneaux_ce_jour']
        
        if resp_code not in responsables_data:
            responsables_data[resp_code] = {
                'dates_absentes': [],
                'creneaux_absents': 0,
                'total_jours': 0,
                'total_creneaux': 0
            }
        
        # Compter le total
        responsables_data[resp_code]['total_jours'] += 1
        responsables_data[resp_code]['total_creneaux'] += nbre_creneaux
        
        # Vérifier si le responsable est affecté À N'IMPORTE QUEL CRÉNEAU de cette date
        affectation_ce_jour = db.execute('''
            SELECT COUNT(*) as count
            FROM affectation a
            JOIN creneau c ON a.creneau_id = c.creneau_id
            WHERE a.code_smartex_ens = ?
                AND c.dateExam = ?
                AND c.id_session = ?
        ''', (resp_code, date_exam, id_session)).fetchone()
        
        # Si aucune affectation ce jour-là → jour absent
        if affectation_ce_jour['count'] == 0:
            responsables_data[resp_code]['dates_absentes'].append(date_exam)
            responsables_data[resp_code]['creneaux_absents'] += nbre_creneaux
    
    # Insérer uniquement les responsables qui ont au moins un jour absent
    for resp_code, data in responsables_data.items():
        if len(data['dates_absentes']) > 0:  # Au moins un jour absent
            # Récupérer les infos de l'enseignant
            ens = db.execute('''
                SELECT participe_surveillance, nom_ens, prenom_ens, grade_code_ens
                FROM enseignant
                WHERE code_smartex_ens = ?
            ''', (resp_code,)).fetchone()
            
            participe_surveillance = ens['participe_surveillance'] if ens else 0
            nom = ens['nom_ens'] if ens else ''
            prenom = ens['prenom_ens'] if ens else ''
            grade = ens['grade_code_ens'] if ens else ''
            
            # Convertir la liste des dates en JSON/string
            dates_absentes_str = ','.join(data['dates_absentes'])
            
            db.execute('''
                INSERT INTO responsable_absent_jour_examen (
                    id_session, 
                    code_smartex_ens, 
                    nom, 
                    prenom, 
                    grade_code,
                    participe_surveillance, 
                    nbre_jours_absents,
                    nbre_creneaux_absents,
                    nbre_total_jours_responsable,
                    nbre_total_creneaux_responsable,
                    dates_absentes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                id_session,
                resp_code,
                nom,
                prenom,
                grade,
                participe_surveillance,
                len(data['dates_absentes']),
                data['creneaux_absents'],
                data['total_jours'],
                data['total_creneaux'],
                dates_absentes_str
            ))
    
    db.commit()
