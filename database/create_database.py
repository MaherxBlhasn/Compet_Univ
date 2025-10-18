import sqlite3
import os

DB_NAME = 'surveillance.db'

def create_database():
    """Créer la base de données et toutes les tables"""
    
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    # Activer les contraintes de clés étrangères
    cursor.execute("PRAGMA foreign_keys = ON")
    
    print("="*60)
    print("CRÉATION DE LA BASE DE DONNÉES")
    print("="*60)
    
    # =========================================================================
    # TABLE: grade
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grade (
            code_grade TEXT PRIMARY KEY,
            grade TEXT NOT NULL,
            quota INTEGER NOT NULL
        )
    """)
    print("✅ Table 'grade' créée")
    
    # =========================================================================
    # TABLE: session
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS session (
            id_session INTEGER PRIMARY KEY AUTOINCREMENT,
            libelle_session TEXT NOT NULL UNIQUE,
            date_debut TEXT,
            date_fin TEXT,
            AU TEXT,
            Semestre TEXT,
            type_session TEXT
        )
    """)
    print("✅ Table 'session' créée")
    
    # =========================================================================
    # TABLE: enseignant
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS enseignant (
            code_smartex_ens INTEGER PRIMARY KEY,
            nom_ens TEXT NOT NULL,
            prenom_ens TEXT NOT NULL,
            email_ens TEXT,
            grade_code_ens TEXT NOT NULL,
            participe_surveillance BOOLEAN NOT NULL DEFAULT 1,
            FOREIGN KEY (grade_code_ens) REFERENCES grade(code_grade) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_enseignant_grade
        ON enseignant(grade_code_ens)
    """)
    print("✅ Table 'enseignant' créée")
    
    # =========================================================================
    # TABLE: creneau
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS creneau (
            creneau_id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_session INTEGER NOT NULL,
            dateExam TEXT NOT NULL,
            h_debut TEXT NOT NULL,
            h_fin TEXT NOT NULL,
            type_ex TEXT,
            semestre TEXT,
            enseignant INTEGER,
            cod_salle TEXT,
            FOREIGN KEY (id_session) REFERENCES session(id_session) ON DELETE CASCADE,
            FOREIGN KEY (enseignant) REFERENCES enseignant(code_smartex_ens) ON DELETE SET NULL
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_creneau_session
        ON creneau(id_session)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_creneau_date
        ON creneau(dateExam, h_debut)
    """)
    print("✅ Table 'creneau' créée")
    
    # =========================================================================
    # TABLE: jour_seance
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS jour_seance (
            id_jour_seance INTEGER PRIMARY KEY AUTOINCREMENT,
            id_session INTEGER NOT NULL,
            jour_num INTEGER NOT NULL,
            date_examen TEXT NOT NULL,
            seance_code TEXT NOT NULL,
            heure_debut TEXT NOT NULL,
            heure_fin TEXT NOT NULL,
            FOREIGN KEY (id_session) REFERENCES session(id_session) ON DELETE CASCADE,
            UNIQUE(id_session, jour_num, date_examen, seance_code)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jour_seance_session
        ON jour_seance(id_session)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_jour_seance_date
        ON jour_seance(id_session, date_examen)
    """)
    print("✅ Table 'jour_seance' créée")
    
    # =========================================================================
    # TABLE: voeu
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS voeu (
            voeu_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_smartex_ens INTEGER NOT NULL,
            id_session INTEGER NOT NULL,
            jour INTEGER NOT NULL,
            seance TEXT NOT NULL,
            FOREIGN KEY (code_smartex_ens) REFERENCES enseignant(code_smartex_ens) ON DELETE CASCADE,
            FOREIGN KEY (id_session) REFERENCES session(id_session) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_voeu_enseignant
        ON voeu(code_smartex_ens)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_voeu_session
        ON voeu(id_session)
    """)
    print("✅ Table 'voeu' créée")
    
    # =========================================================================
    # TABLE: affectation (MODIFIÉE - avec colonne jour)
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS affectation (
            affectation_id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_smartex_ens INTEGER NOT NULL,
            creneau_id INTEGER NOT NULL,
            id_session INTEGER NOT NULL,
            jour INTEGER,
            seance TEXT,
            date_examen TEXT,
            h_debut TEXT,
            h_fin TEXT,
            cod_salle TEXT,
            position TEXT,
            FOREIGN KEY (code_smartex_ens) REFERENCES enseignant(code_smartex_ens) ON DELETE CASCADE,
            FOREIGN KEY (creneau_id) REFERENCES creneau(creneau_id) ON DELETE CASCADE,
            FOREIGN KEY (id_session) REFERENCES session(id_session) ON DELETE CASCADE,
            UNIQUE(code_smartex_ens, creneau_id, cod_salle)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_affectation_ens
        ON affectation(code_smartex_ens)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_affectation_creneau
        ON affectation(creneau_id)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_affectation_session
        ON affectation(id_session)
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_affectation_jour
        ON affectation(id_session, jour)
    """)
    print("✅ Table 'affectation' créée (avec colonne jour)")
    
    conn.commit()
    # =========================================================================
    # TABLE: quota_enseignant 
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS quota_enseignant (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code_smartex_ens INTEGER NOT NULL,
            id_session INTEGER NOT NULL,
            grade_code_ens TEXT NOT NULL,
            quota_grade INTEGER NOT NULL,
            quota_realise INTEGER NOT NULL,
            quota_majoritaire INTEGER NOT NULL,
            diff_quota_grade INTEGER NOT NULL,
            diff_quota_majoritaire INTEGER NOT NULL,
            quota_ajuste INTEGER,
            quota_ajuste_maj INTEGER,
            FOREIGN KEY (code_smartex_ens) REFERENCES enseignant(code_smartex_ens) ON DELETE CASCADE,
            FOREIGN KEY (id_session) REFERENCES session(id_session) ON DELETE CASCADE,

            UNIQUE(code_smartex_ens, id_session)
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_quota_ens
        ON quota_enseignant(code_smartex_ens, id_session)
    """)
    print("✅ Table 'quota_enseignant' créée")

    conn.commit()

    # =========================================================================
    # TABLE: salle_par_creneau
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS salle_par_creneau (
            id_session INTEGER NOT NULL,
            dateExam TEXT NOT NULL,
            h_debut TEXT NOT NULL,
            nb_salle INTEGER NOT NULL,
            PRIMARY KEY (id_session, dateExam, h_debut),
            FOREIGN KEY (id_session) REFERENCES session(id_session) ON DELETE CASCADE
        )
    """)
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_salle_creneau_date
        ON salle_par_creneau(dateExam, h_debut)
    """)
    print("✅ Table 'salle_par_creneau' créée")

    # =========================================================================
    # TABLE: responsable_absent_jour_examen
    # =========================================================================
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS responsable_absent_jour_examen (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            id_session INTEGER NOT NULL,
            code_smartex_ens TEXT NOT NULL,
            nom TEXT NOT NULL,
            prenom TEXT NOT NULL,
            grade_code TEXT,
            participe_surveillance INTEGER NOT NULL,
            nbre_jours_absents INTEGER NOT NULL,
            nbre_creneaux_absents INTEGER NOT NULL,
            nbre_total_jours_responsable INTEGER NOT NULL,
            nbre_total_creneaux_responsable INTEGER NOT NULL,
            dates_absentes TEXT,
            FOREIGN KEY (id_session) REFERENCES session(id_session) ON DELETE CASCADE,
            FOREIGN KEY (code_smartex_ens) REFERENCES enseignant(code_smartex_ens) ON DELETE CASCADE
        )
    """)
    print("✅ Table 'responsable_absent_jour_examen' créée")

    print("\n✅ Base de données créée avec succès")
    print("✅ Tables créées : grade, session, enseignant, creneau, jour_seance, voeu, affectation, salle_par_creneau")
    
    insert_default_grades(cursor)
    
    conn.commit()
    conn.close()
    
    print("="*60 + "\n")


def insert_default_grades(cursor):
    """Insérer les grades par défaut avec leurs quotas selon l'image fournie"""
    grades = [
        ('PR', 'Professeur', 4),
        ('MC', 'Maître de conférences', 4),
        ('MA', 'Maître Assistant', 7),
        ('AS', 'Assistant', 8),
        ('AC', 'Assistant Contractuel', 9),
        ('PTC', 'Professeur Tronc Commun', 9),
        ('PES', "Professeur d'enseignement secondaire", 9),
        ('EX', 'Expert', 3),
        ('V', 'Vacataire', 4),
    ]
    
    cursor.executemany("""
        INSERT OR IGNORE INTO grade (code_grade, grade, quota)
        VALUES (?, ?, ?)
    """, grades)
    
    print(f"✅ {len(grades)} grades insérés par défaut")


def show_database_structure():
    """Afficher la structure de la base de données"""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    print("\n" + "="*60)
    print("STRUCTURE DE LA BASE DE DONNÉES")
    print("="*60 + "\n")
    
    tables = ['grade', 'session', 'enseignant', 'creneau', 'jour_seance', 'voeu', 'affectation', 'salle_par_creneau']
    
    for table in tables:
        cursor.execute(f"PRAGMA table_info({table})")
        columns = cursor.fetchall()
        
        print(f"📊 TABLE: {table}")
        print("-" * 60)
        for col in columns:
            col_id, name, dtype, notnull, default, pk = col
            pk_str = " [PK]" if pk else ""
            notnull_str = " NOT NULL" if notnull else ""
            default_str = f" DEFAULT {default}" if default else ""
            print(f"   • {name:<25} {dtype:<10}{pk_str}{notnull_str}{default_str}")
        print()
    
    conn.close()


if __name__ == "__main__":
    # Supprimer l'ancienne base si elle existe
    if os.path.exists(DB_NAME):
        os.remove(DB_NAME)
        print(f"🗑️  Ancienne base supprimée: {DB_NAME}\n")
    
    # Créer la nouvelle base
    create_database()
    
    # Afficher la structure
    show_database_structure()
    
    print("="*60)
    print("✨ Initialisation terminée!")
    print(f"📁 Base de données: {DB_NAME}")
    print("="*60)