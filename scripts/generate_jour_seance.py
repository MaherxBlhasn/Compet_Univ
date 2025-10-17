import sqlite3
import pandas as pd

DB_NAME = 'surveillance.db'

def get_db_connection():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def parse_time(time_str):
    """Parse une heure au format 'HH:MM:SS' ou 'DD/MM/YYYY HH:MM:SS'"""
    if pd.isna(time_str):
        return None
    time_str = str(time_str)
    if ' ' in time_str:
        return time_str.split(' ')[1][:5]
    return time_str[:5]


def determine_seance_from_time(time_str):
    """Déterminer le code de séance à partir de l'heure"""
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
    """
    Générer automatiquement la table jour_seance à partir des créneaux
    
    Logique:
    1. Récupérer tous les créneaux DISTINCTS (dateExam, h_debut, h_fin)
    2. Extraire les dates uniques ET LES TRIER
    3. Numéroter les jours (jour_num = 1, 2, 3, ... par ordre chronologique)
    4. Pour chaque date, extraire les séances uniques (S1, S2, S3, S4)
    5. Insérer dans jour_seance
    """
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    print(f"\n{'='*70}")
    print(f"GÉNÉRATION DYNAMIQUE DE jour_seance POUR SESSION {session_id}")
    print(f"{'='*70}")
    
    # 1. Récupérer tous les créneaux DISTINCTS de la session
    print("\n1️⃣ Récupération des créneaux distincts...")
    cursor.execute("""
        SELECT DISTINCT dateExam, h_debut, h_fin
        FROM creneau
        WHERE id_session = ?
        ORDER BY dateExam, h_debut
    """, (session_id,))
    
    creneaux = cursor.fetchall()
    
    if not creneaux:
        print("   ⚠️  Aucun créneau trouvé pour cette session!")
        conn.close()
        return False
    
    print(f"   ✓ {len(creneaux)} créneaux distincts trouvés")
    
    # 2. Extraire les DATES UNIQUES et les TRIER
    print("\n2️⃣ Extraction des dates uniques...")
    dates_uniques = sorted(set(row['dateExam'] for row in creneaux))
    
    print(f"   ✓ {len(dates_uniques)} dates identifiées:")
    for i, date in enumerate(dates_uniques, 1):
        print(f"      Jour {i}: {date}")
    
    # 3. Construire la structure jour_seance
    print("\n3️⃣ Construction de jour_seance...")
    jour_seance_list = []
    
    for jour_num, date in enumerate(dates_uniques, 1):
        # Récupérer tous les créneaux pour cette date
        creneaux_date = [c for c in creneaux if c['dateExam'] == date]
        
        # Extraire les SÉANCES UNIQUES pour cette date
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
        
        # Ajouter les séances pour cette date (triées par heure)
        for heure in sorted(seances_dict.keys()):
            seance_info = seances_dict[heure]
            jour_seance_list.append({
                'id_session': session_id,
                'jour_num': jour_num,
                'date_examen': date,
                'seance_code': seance_info['seance_code'],
                'heure_debut': seance_info['heure_debut'],
                'heure_fin': seance_info['heure_fin']
            })
        
        print(f"   Jour {jour_num} ({date}): {len(seances_dict)} séances")
    
    print(f"\n   ✓ Total: {len(jour_seance_list)} combinaisons jour/séance")
    
    # 4. Afficher un aperçu
    print("\n4️⃣ Aperçu des données:")
    print("   " + "-"*66)
    print(f"   {'Jour':<6} {'Date':<12} {'Séance':<8} {'Début':<10} {'Fin':<10}")
    print("   " + "-"*66)
    
    for i, item in enumerate(jour_seance_list):
        if i < 10:  # Afficher les 10 premiers
            print(f"   {item['jour_num']:<6} {item['date_examen']:<12} {item['seance_code']:<8} {item['heure_debut']:<10} {item['heure_fin']:<10}")
    
    if len(jour_seance_list) > 10:
        print(f"   ... ({len(jour_seance_list) - 10} autres)")
    
    # 5. Supprimer l'ancien mapping pour cette session
    print("\n5️⃣ Nettoyage de l'ancien mapping...")
    cursor.execute("DELETE FROM jour_seance WHERE id_session = ?", (session_id,))
    deleted = cursor.rowcount
    print(f"   ✓ {deleted} anciens enregistrements supprimés")
    
    # 6. Insérer les nouvelles données
    print("\n6️⃣ Insertion des nouvelles données...")
    try:
        cursor.executemany("""
            INSERT INTO jour_seance 
            (id_session, jour_num, date_examen, seance_code, heure_debut, heure_fin)
            VALUES (?, ?, ?, ?, ?, ?)
        """, [
            (
                item['id_session'],
                item['jour_num'],
                item['date_examen'],
                item['seance_code'],
                item['heure_debut'],
                item['heure_fin']
            )
            for item in jour_seance_list
        ])
        
        conn.commit()
        print(f"   ✓ {len(jour_seance_list)} enregistrements insérés")
        
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Erreur lors de l'insertion: {e}")
        conn.close()
        return False
    
    # 7. Vérification finale
    print("\n7️⃣ Vérification...")
    cursor.execute("""
        SELECT COUNT(*) as total,
               COUNT(DISTINCT jour_num) as nb_jours,
               COUNT(DISTINCT seance_code) as nb_seances
        FROM jour_seance
        WHERE id_session = ?
    """, (session_id,))
    
    stats = cursor.fetchone()
    print(f"   ✓ Total: {stats['total']} entrées")
    print(f"   ✓ Jours: {stats['nb_jours']} (de jour 1 à {stats['nb_jours']})")
    print(f"   ✓ Séances: {stats['nb_seances']} (S1, S2, S3, S4, ...)")
    
    # 8. Générer salle_par_creneau
    print("\n8️⃣ Génération de salle_par_creneau...")
    try:
        # Supprimer les anciennes entrées pour cette session
        cursor.execute("DELETE FROM salle_par_creneau WHERE id_session = ?", (session_id,))
        
        # Compter le nombre de salles pour chaque créneau
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
        
        inserted = cursor.rowcount
        conn.commit()
        print(f"   ✓ {inserted} créneaux avec leur nombre de salles insérés")
    except Exception as e:
        conn.rollback()
        print(f"   ❌ Erreur lors de la génération de salle_par_creneau: {e}")
    
    conn.close()
    
    print(f"\n{'='*70}")
    print("✅ Génération terminée avec succès!")
    print(f"{'='*70}\n")
    
    return True


def display_jour_seance(session_id):
    """Afficher le contenu de jour_seance pour une session"""
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT jour_num, date_examen, seance_code, heure_debut, heure_fin
        FROM jour_seance
        WHERE id_session = ?
        ORDER BY jour_num, heure_debut
    """, (session_id,))
    
    rows = cursor.fetchall()
    conn.close()
    
    if not rows:
        print(f"\n⚠️  Aucune donnée pour la session {session_id}")
        return
    
    print(f"\n{'='*70}")
    print(f"CONTENU DE jour_seance - Session {session_id}")
    print(f"{'='*70}\n")
    
    current_jour = None
    for row in rows:
        if row['jour_num'] != current_jour:
            print(f"\n📅 JOUR {row['jour_num']} - {row['date_examen']}")
            print("-" * 70)
            current_jour = row['jour_num']
        
        print(f"   {row['seance_code']:<5} {row['heure_debut']:>10} → {row['heure_fin']:<10}")
    
    print(f"\n{'='*70}")
    print(f"Total: {len(rows)} entrées")
    print(f"{'='*70}\n")


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python generate_jour_seance.py <session_id>")
        print("\nExemple:")
        print("   python generate_jour_seance.py 1")
        sys.exit(1)
    
    session_id = int(sys.argv[1])
    
    # Générer jour_seance à partir des créneaux
    success = generate_jour_seance_from_creneaux(session_id)
    
    if success:
        # Afficher le résultat
        display_jour_seance(session_id)