import sqlite3
import pandas as pd

DB_NAME = 'surveillance.db'

def analyze_quotas():
    """Analyser les quotas et identifier les problèmes d'infaisabilité"""
    
    conn = sqlite3.connect(DB_NAME)
    
    print("="*70)
    print("ANALYSE DES QUOTAS ET DIAGNOSTIC D'INFAISABILITÉ")
    print("="*70)
    
    # 1. Récupérer les quotas par grade
    print("\n[1] QUOTAS PAR GRADE")
    print("-"*70)
    grades_df = pd.read_sql_query("""
        SELECT code_grade, quota
        FROM grade
        ORDER BY code_grade
    """, conn)
    
    for _, row in grades_df.iterrows():
        print(f"   {row['code_grade']:6s}: {row['quota']} surveillances maximum")
    
    # 2. Compter les enseignants par grade (qui participent)
    print("\n[2] ENSEIGNANTS PAR GRADE (qui participent à la surveillance)")
    print("-"*70)
    ens_df = pd.read_sql_query("""
        SELECT 
            grade_code_ens,
            COUNT(*) as nb_enseignants,
            SUM(CASE WHEN participe_surveillance = 1 THEN 1 ELSE 0 END) as nb_participants
        FROM enseignant
        GROUP BY grade_code_ens
        ORDER BY grade_code_ens
    """, conn)
    
    for _, row in ens_df.iterrows():
        print(f"   {row['grade_code_ens']:6s}: {row['nb_participants']:2d} enseignants participent (sur {row['nb_enseignants']})")
    
    # 3. Calculer la capacité totale
    print("\n[3] CAPACITÉ TOTALE DE SURVEILLANCE")
    print("-"*70)
    
    capacity_df = pd.read_sql_query("""
        SELECT 
            e.grade_code_ens,
            COUNT(*) as nb_enseignants,
            g.quota,
            COUNT(*) * g.quota as capacite_totale
        FROM enseignant e
        JOIN grade g ON e.grade_code_ens = g.code_grade
        WHERE e.participe_surveillance = 1
        GROUP BY e.grade_code_ens
        ORDER BY e.grade_code_ens
    """, conn)
    
    total_capacity = 0
    for _, row in capacity_df.iterrows():
        capacity = row['capacite_totale']
        total_capacity += capacity
        print(f"   {row['grade_code_ens']:6s}: {row['nb_enseignants']:2d} ens × {row['quota']} surveillances = {capacity:3d} surveillances max")
    
    print(f"\n   TOTAL: {total_capacity} surveillances possibles")
    
    # 4. Compter les créneaux et surveillances requises
    print("\n[4] BESOINS EN SURVEILLANCE (pour session id=1)")
    print("-"*70)
    
    # Récupérer salle_par_creneau
    salle_creneau_df = pd.read_sql_query("""
        SELECT dateExam, h_debut, nb_salle
        FROM salle_par_creneau
        WHERE id_session = 1
    """, conn)
    
    total_required = 0
    nb_creneaux = 0
    
    for _, row in salle_creneau_df.iterrows():
        nb_salles = row['nb_salle']
        # Formule: 2 surveillants par salle + 4 réserves
        nb_surveillants = (nb_salles * 2) + 4
        total_required += nb_surveillants
        nb_creneaux += 1
        print(f"   {row['dateExam']} {row['h_debut']}: {nb_salles:2d} salles → {nb_surveillants:2d} surveillants requis")
    
    print(f"\n   TOTAL: {total_required} surveillances requises sur {nb_creneaux} créneaux")
    
    # 5. Diagnostic
    print("\n[5] DIAGNOSTIC")
    print("="*70)
    
    if total_required > total_capacity:
        deficit = total_required - total_capacity
        print(f"\n❌ PROBLÈME IDENTIFIÉ : INFAISABILITÉ")
        print(f"\n   Surveillances requises : {total_required}")
        print(f"   Capacité disponible    : {total_capacity}")
        print(f"   DÉFICIT                : {deficit} surveillances")
        print(f"\n   Le problème est INFAISABLE car il manque {deficit} surveillances.")
        
        print("\n[6] SOLUTIONS POSSIBLES")
        print("-"*70)
        print("   Option 1: Augmenter les quotas de certains grades")
        print("   Option 2: Recruter plus d'enseignants")
        print("   Option 3: Réduire le nombre de salles par créneau")
        print("   Option 4: Réduire le nombre de réserves (actuellement 4)")
        
        # Suggestion de nouveaux quotas
        print("\n[7] SUGGESTION DE NOUVEAUX QUOTAS")
        print("-"*70)
        
        # Calcul du quota moyen nécessaire
        total_ens_participants = capacity_df['nb_enseignants'].sum()
        quota_moyen_necessaire = total_required / total_ens_participants
        
        print(f"\n   Quota moyen nécessaire : {quota_moyen_necessaire:.2f} surveillances/enseignant")
        print(f"\n   Suggestions par grade:")
        
        for _, row in capacity_df.iterrows():
            grade = row['grade_code_ens']
            nb_ens = row['nb_enseignants']
            quota_actuel = row['quota']
            
            # Calculer le quota suggéré (arrondi au supérieur)
            quota_suggere = int(quota_moyen_necessaire) + 1
            
            nouvelle_capacite = nb_ens * quota_suggere
            ancienne_capacite = row['capacite_totale']
            gain = nouvelle_capacite - ancienne_capacite
            
            symbole = "↑" if quota_suggere > quota_actuel else "="
            
            print(f"   {grade:6s}: {quota_actuel} → {quota_suggere} {symbole} (+{gain} surveillances)")
        
    else:
        surplus = total_capacity - total_required
        print(f"\n✅ CAPACITÉ SUFFISANTE")
        print(f"\n   Surveillances requises : {total_required}")
        print(f"   Capacité disponible    : {total_capacity}")
        print(f"   MARGE                  : {surplus} surveillances")
        print(f"\n   Le problème devrait être FAISABLE.")
        print(f"\n   Si l'optimisation échoue, vérifiez:")
        print(f"   - Les contraintes d'équité (trop strictes?)")
        print(f"   - Les vœux de non-surveillance (trop nombreux?)")
        print(f"   - La distribution des enseignants par créneau")
    
    # 8. Analyser la distribution par grade
    print("\n[8] ANALYSE PAR GRADE")
    print("="*70)
    
    for _, row in capacity_df.iterrows():
        grade = row['grade_code_ens']
        nb_ens = row['nb_enseignants']
        quota = row['quota']
        capacite = row['capacite_totale']
        
        # Estimer la part de ce grade dans les surveillances
        part_theorique = capacite / total_capacity
        surveillances_attendues = total_required * part_theorique
        
        print(f"\n   Grade {grade}:")
        print(f"      - {nb_ens} enseignants × {quota} = {capacite} surveillances max")
        print(f"      - Part théorique: {part_theorique*100:.1f}% des surveillances")
        print(f"      - Surveillances attendues: {surveillances_attendues:.1f}")
        
        if surveillances_attendues > capacite:
            deficit_grade = surveillances_attendues - capacite
            print(f"      ⚠️ DÉFICIT: {deficit_grade:.1f} surveillances manquantes")
        else:
            marge_grade = capacite - surveillances_attendues
            print(f"      ✓ MARGE: {marge_grade:.1f} surveillances disponibles")
    
    conn.close()
    
    print("\n" + "="*70)

if __name__ == "__main__":
    analyze_quotas()
