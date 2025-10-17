"""
Export CSV de l'analyse des responsables
"""

import sqlite3
import csv
import os
from config import Config
from datetime import datetime


def export_analyse_responsables_csv(session_id=None):
    """
    Exporter l'analyse des responsables en CSV
    """
    conn = sqlite3.connect(Config.DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    output_dir = 'exports'
    os.makedirs(output_dir, exist_ok=True)
    
    # Nom du fichier avec timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    session_suffix = f"_session_{session_id}" if session_id else "_all_sessions"
    filename = f"{output_dir}/analyse_responsables{session_suffix}_{timestamp}.csv"
    
    print("=" * 70)
    print("EXPORT ANALYSE RESPONSABLES EN CSV")
    print("=" * 70)
    
    session_filter = ""
    session_filter_and = ""
    params = []
    if session_id:
        session_filter = "AND aer.id_session = ?"
        session_filter_and = "AND id_session = ?"
        params = [session_id]
    
    # Récupérer tous les responsables
    query_responsables = f"""
        SELECT DISTINCT 
            aer.code_smartex_ens,
            e.nom_ens || ' ' || e.prenom_ens as nom_complet,
            e.grade_code_ens
        FROM affectation_ens_resp aer
        JOIN enseignant e ON aer.code_smartex_ens = e.code_smartex_ens
        WHERE aer.type_affectation = 'RESPONSABLE'
        {session_filter}
        ORDER BY nom_complet
    """
    
    if session_id:
        cursor.execute(query_responsables, params)
    else:
        cursor.execute(query_responsables)
    
    responsables = cursor.fetchall()
    
    # Préparer les données pour l'export
    export_data = []
    
    for resp in responsables:
        code_ens = resp['code_smartex_ens']
        nom = resp['nom_complet']
        grade = resp['grade_code_ens']
        
        # Dates où il est responsable
        query_dates_resp = f"""
            SELECT DISTINCT date_examen
            FROM affectation_ens_resp
            WHERE code_smartex_ens = ?
              AND type_affectation = 'RESPONSABLE'
              {session_filter_and}
        """
        
        if session_id:
            cursor.execute(query_dates_resp, [code_ens, session_id])
        else:
            cursor.execute(query_dates_resp, [code_ens])
        
        dates_responsable = [row['date_examen'] for row in cursor.fetchall()]
        
        # Dates où il surveille (même jour que responsabilité)
        if dates_responsable:
            query_surveillance_meme_jour = f"""
                SELECT DISTINCT date_examen
                FROM affectation_ens_resp
                WHERE code_smartex_ens = ?
                  AND type_affectation = 'SURVEILLANCE'
                  AND date_examen IN ({','.join('?' * len(dates_responsable))})
                  {session_filter_and}
            """
            
            if session_id:
                cursor.execute(query_surveillance_meme_jour, [code_ens] + dates_responsable + [session_id])
            else:
                cursor.execute(query_surveillance_meme_jour, [code_ens] + dates_responsable)
            
            dates_surveillance = [row['date_examen'] for row in cursor.fetchall()]
        else:
            dates_surveillance = []
        
        # Nombre total de responsabilités
        query_count_resp = f"""
            SELECT COUNT(*) as count
            FROM affectation_ens_resp
            WHERE code_smartex_ens = ?
              AND type_affectation = 'RESPONSABLE'
              {session_filter_and}
        """
        
        if session_id:
            cursor.execute(query_count_resp, [code_ens, session_id])
        else:
            cursor.execute(query_count_resp, [code_ens])
        
        nb_responsabilites = cursor.fetchone()['count']
        
        # Nombre total de surveillances
        query_count_surv = f"""
            SELECT COUNT(*) as count
            FROM affectation_ens_resp
            WHERE code_smartex_ens = ?
              AND type_affectation = 'SURVEILLANCE'
              {session_filter_and}
        """
        
        if session_id:
            cursor.execute(query_count_surv, [code_ens, session_id])
        else:
            cursor.execute(query_count_surv, [code_ens])
        
        nb_surveillances = cursor.fetchone()['count']
        
        # Statut
        surveille_meme_jour = len(dates_surveillance) > 0
        statut = "Surveille le jour de responsabilité" if surveille_meme_jour else "Ne surveille PAS le jour de responsabilité"
        
        export_data.append({
            'Code Enseignant': code_ens,
            'Nom Complet': nom,
            'Grade': grade,
            'Nb Responsabilités': nb_responsabilites,
            'Nb Surveillances': nb_surveillances,
            'Jours Responsable': len(dates_responsable),
            'Jours Surveillés (même date)': len(dates_surveillance),
            'Dates Responsable': ', '.join(dates_responsable),
            'Dates Surveillance (même jour)': ', '.join(dates_surveillance),
            'Statut': statut,
            'Surveillance Même Jour': 'Oui' if surveille_meme_jour else 'Non'
        })
    
    # Écrire le CSV
    with open(filename, 'w', newline='', encoding='utf-8-sig') as csvfile:
        if export_data:
            fieldnames = export_data[0].keys()
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(export_data)
    
    print(f"✅ Fichier exporté : {filename}")
    print(f"📊 {len(export_data)} responsables analysés")
    
    # Statistiques
    surveillent_meme_jour = sum(1 for d in export_data if d['Surveillance Même Jour'] == 'Oui')
    pourcentage = (surveillent_meme_jour / len(export_data) * 100) if export_data else 0
    
    print(f"\n📈 Statistiques :")
    print(f"   - Responsables qui surveillent le même jour : {surveillent_meme_jour}/{len(export_data)} ({pourcentage:.1f}%)")
    print(f"   - Responsables qui ne surveillent PAS       : {len(export_data) - surveillent_meme_jour}/{len(export_data)} ({100-pourcentage:.1f}%)")
    
    conn.close()
    
    return filename


if __name__ == "__main__":
    conn = sqlite3.connect(Config.DB_NAME)
    cursor = conn.cursor()
    
    # Afficher les sessions disponibles
    cursor.execute("SELECT id_session, libelle_session FROM session ORDER BY id_session")
    sessions = cursor.fetchall()
    
    if not sessions:
        print("❌ Aucune session trouvée dans la base de données.")
        conn.close()
        exit(1)
    
    print("\n" + "=" * 70)
    print("SESSIONS DISPONIBLES")
    print("=" * 70)
    for session in sessions:
        print(f"  {session[0]} - {session[1]}")
    
    print("\n0 - Toutes les sessions")
    print("=" * 70)
    
    try:
        choice = input("\nChoisissez une session (numéro) : ").strip()
        
        if choice == '0':
            session_id = None
        else:
            session_id = int(choice)
            if not any(s[0] == session_id for s in sessions):
                print(f"❌ Session {session_id} introuvable.")
                conn.close()
                exit(1)
        
        conn.close()
        
        # Exporter
        export_analyse_responsables_csv(session_id)
        
        print("\n✨ Export terminé avec succès!")
        
    except ValueError:
        print("❌ Entrée invalide.")
        conn.close()
    except KeyboardInterrupt:
        print("\n\n⚠️  Export interrompu.")
        conn.close()
