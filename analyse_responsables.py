"""
Analyse des responsables d'examen et leurs surveillances
- Pourcentage de responsables qui surveillent le jour où ils sont responsables
- Liste des responsables qui ne font que surveiller (pas de surveillance le jour de responsabilité)
"""

import sqlite3
from config import Config

# Essayer d'importer tabulate, sinon utiliser un affichage simple
try:
    from tabulate import tabulate
    HAS_TABULATE = True
except ImportError:
    HAS_TABULATE = False
    
    def tabulate(data, headers='keys', tablefmt='grid'):
        """Version simple de tabulate si le module n'est pas installé"""
        if not data:
            return "Aucune donnée"
        
        if headers == 'keys' and isinstance(data[0], dict):
            headers = list(data[0].keys())
            rows = [[row[h] for h in headers] for row in data]
        else:
            rows = data
        
        # Calculer les largeurs de colonnes
        col_widths = [len(str(h)) for h in headers]
        for row in rows:
            for i, cell in enumerate(row):
                col_widths[i] = max(col_widths[i], len(str(cell)))
        
        # Créer le tableau
        sep = "+" + "+".join("-" * (w + 2) for w in col_widths) + "+"
        header_row = "|" + "|".join(f" {str(h):<{col_widths[i]}} " for i, h in enumerate(headers)) + "|"
        
        result = [sep, header_row, sep]
        for row in rows:
            row_str = "|" + "|".join(f" {str(cell):<{col_widths[i]}} " for i, cell in enumerate(row)) + "|"
            result.append(row_str)
        result.append(sep)
        
        return "\n".join(result)


def analyse_responsables(session_id=None):
    """
    Analyser les responsables et leurs surveillances le même jour
    """
    conn = sqlite3.connect(Config.DB_NAME)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    print("=" * 80)
    print("ANALYSE DES RESPONSABLES D'EXAMEN")
    print("=" * 80)
    
    # Filtrer par session si spécifié
    session_filter = ""
    session_filter_and = ""
    params = []
    if session_id:
        session_filter = "AND aer.id_session = ?"
        session_filter_and = "AND id_session = ?"
        params = [session_id]
        cursor.execute("SELECT libelle_session FROM session WHERE id_session = ?", (session_id,))
        session_info = cursor.fetchone()
        if session_info:
            print(f"Session : {session_info['libelle_session']}")
    else:
        print("Toutes les sessions")
    
    print("=" * 80)
    
    # 1. Récupérer tous les responsables (au moins une ligne avec type RESPONSABLE)
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
    total_responsables = len(responsables)
    
    print(f"\n📊 Nombre total de responsables : {total_responsables}")
    
    if total_responsables == 0:
        print("\n⚠️  Aucun responsable trouvé dans la base de données.")
        conn.close()
        return
    
    # 2. Pour chaque responsable, vérifier s'il surveille le même jour où il est responsable
    responsables_surveillent_meme_jour = 0
    responsables_ne_surveillent_pas = []
    details_responsables = []
    
    for resp in responsables:
        code_ens = resp['code_smartex_ens']
        nom = resp['nom_complet']
        grade = resp['grade_code_ens']
        
        # Récupérer les dates où il est responsable
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
        
        # Vérifier s'il surveille au moins un de ces jours
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
        
        # Compter le nombre de responsabilités et surveillances
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
        
        # Déterminer le statut
        surveille_meme_jour = len(dates_surveillance) > 0
        
        if surveille_meme_jour:
            responsables_surveillent_meme_jour += 1
            statut = "✅ Surveille le jour de responsabilité"
        else:
            statut = "❌ Ne surveille PAS le jour de responsabilité"
            responsables_ne_surveillent_pas.append({
                'nom': nom,
                'grade': grade,
                'nb_resp': nb_responsabilites,
                'nb_surv': nb_surveillances,
                'dates_resp': ', '.join(dates_responsable)
            })
        
        details_responsables.append({
            'Enseignant': nom,
            'Grade': grade,
            'Nb Responsabilités': nb_responsabilites,
            'Nb Surveillances': nb_surveillances,
            'Jours responsable': len(dates_responsable),
            'Jours surveillés (même date)': len(dates_surveillance),
            'Statut': statut
        })
    
    # 3. Calculer les statistiques
    pourcentage_surveillent = (responsables_surveillent_meme_jour / total_responsables * 100) if total_responsables > 0 else 0
    
    print("\n" + "=" * 80)
    print("STATISTIQUES GLOBALES")
    print("=" * 80)
    print(f"Total responsables                          : {total_responsables}")
    print(f"Responsables qui surveillent le même jour   : {responsables_surveillent_meme_jour} ({pourcentage_surveillent:.1f}%)")
    print(f"Responsables qui ne surveillent PAS         : {len(responsables_ne_surveillent_pas)} ({100-pourcentage_surveillent:.1f}%)")
    
    # 4. Afficher les détails de tous les responsables
    print("\n" + "=" * 80)
    print("DÉTAILS DE TOUS LES RESPONSABLES")
    print("=" * 80)
    print(tabulate(details_responsables, headers='keys', tablefmt='grid'))
    
    # 5. Afficher la liste des responsables qui ne surveillent pas le jour de responsabilité
    if responsables_ne_surveillent_pas:
        print("\n" + "=" * 80)
        print("⚠️  RESPONSABLES QUI NE SURVEILLENT PAS LE JOUR DE RESPONSABILITÉ")
        print("=" * 80)
        
        table_data = []
        for resp in responsables_ne_surveillent_pas:
            table_data.append({
                'Enseignant': resp['nom'],
                'Grade': resp['grade'],
                'Nb Responsabilités': resp['nb_resp'],
                'Nb Surveillances (autres jours)': resp['nb_surv'],
                'Dates responsable': resp['dates_resp']
            })
        
        print(tabulate(table_data, headers='keys', tablefmt='grid'))
    
    # 6. Afficher les responsables qui sont UNIQUEMENT responsables (aucune surveillance)
    query_responsables_only = f"""
        SELECT DISTINCT 
            e.nom_ens || ' ' || e.prenom_ens as nom_complet,
            e.grade_code_ens,
            COUNT(aer.id) as nb_responsabilites
        FROM affectation_ens_resp aer
        JOIN enseignant e ON aer.code_smartex_ens = e.code_smartex_ens
        WHERE aer.type_affectation = 'RESPONSABLE'
          {session_filter}
          AND aer.code_smartex_ens NOT IN (
              SELECT DISTINCT code_smartex_ens 
              FROM affectation_ens_resp 
              WHERE type_affectation = 'SURVEILLANCE'
              {session_filter_and}
          )
        GROUP BY aer.code_smartex_ens, nom_complet, e.grade_code_ens
        ORDER BY nb_responsabilites DESC, nom_complet
    """
    
    if session_id:
        cursor.execute(query_responsables_only, [session_id, session_id])
    else:
        cursor.execute(query_responsables_only)
    
    responsables_only = cursor.fetchall()
    
    if responsables_only:
        print("\n" + "=" * 80)
        print("🎯 RESPONSABLES UNIQUEMENT (AUCUNE SURVEILLANCE)")
        print("=" * 80)
        
        table_only = []
        for row in responsables_only:
            table_only.append({
                'Enseignant': row['nom_complet'],
                'Grade': row['grade_code_ens'],
                'Nb Responsabilités': row['nb_responsabilites']
            })
        
        print(tabulate(table_only, headers='keys', tablefmt='grid'))
        print(f"\nTotal : {len(responsables_only)} enseignant(s) sont uniquement responsables")
    
    print("\n" + "=" * 80)
    
    conn.close()


def main():
    """Point d'entrée principal"""
    conn = sqlite3.connect(Config.DB_NAME)
    cursor = conn.cursor()
    
    # Afficher les sessions disponibles
    cursor.execute("SELECT id_session, libelle_session FROM session ORDER BY id_session")
    sessions = cursor.fetchall()
    
    if not sessions:
        print("❌ Aucune session trouvée dans la base de données.")
        conn.close()
        return
    
    print("\n" + "=" * 80)
    print("SESSIONS DISPONIBLES")
    print("=" * 80)
    for session in sessions:
        print(f"  {session[0]} - {session[1]}")
    
    print("\n0 - Toutes les sessions")
    print("=" * 80)
    
    try:
        choice = input("\nChoisissez une session (numéro) : ").strip()
        
        if choice == '0':
            session_id = None
        else:
            session_id = int(choice)
            # Vérifier que la session existe
            if not any(s[0] == session_id for s in sessions):
                print(f"❌ Session {session_id} introuvable.")
                conn.close()
                return
        
        conn.close()
        
        # Lancer l'analyse
        analyse_responsables(session_id)
        
    except ValueError:
        print("❌ Entrée invalide.")
        conn.close()
    except KeyboardInterrupt:
        print("\n\n⚠️  Analyse interrompue.")
        conn.close()


if __name__ == "__main__":
    main()
