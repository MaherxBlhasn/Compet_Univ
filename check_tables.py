import sqlite3

def check_tables():
    conn = sqlite3.connect('surveillance.db')
    cursor = conn.cursor()
    
    # Vérifier le nombre de créneaux
    cursor.execute("SELECT COUNT(*) FROM creneau")
    creneau_count = cursor.fetchone()[0]
    print(f"Nombre de créneaux dans la table creneau: {creneau_count}")
    
    # Vérifier le contenu de salle_par_creneau
    cursor.execute("SELECT COUNT(*) FROM salle_par_creneau")
    salle_count = cursor.fetchone()[0]
    print(f"Nombre d'entrées dans la table salle_par_creneau: {salle_count}")
    
    # Montrer quelques exemples de créneaux avec leurs salles
    cursor.execute("""
        SELECT id_session, dateExam, h_debut, cod_salle 
        FROM creneau 
        WHERE cod_salle IS NOT NULL 
        LIMIT 5
    """)
    print("\nExemples de créneaux avec salles:")
    for row in cursor.fetchall():
        print(f"Session: {row[0]}, Date: {row[1]}, Heure: {row[2]}, Salle: {row[3]}")

    # Vérifier si generate_jour_seance a été exécuté
    cursor.execute("SELECT COUNT(*) FROM jour_seance")
    jour_seance_count = cursor.fetchone()[0]
    print(f"\nNombre d'entrées dans la table jour_seance: {jour_seance_count}")

if __name__ == "__main__":
    check_tables()