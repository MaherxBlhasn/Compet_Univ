#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module pour gérer la table quota_enseignant
Calcule les écarts entre quotas réels et attendus
"""

import sqlite3
import pandas as pd
from collections import defaultdict


def create_quota_enseignant_table(conn):
    """Créer la table quota_enseignant si elle n'existe pas"""
    cursor = conn.cursor()
    
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
            FOREIGN KEY (code_smartex_ens) REFERENCES enseignant(code_smartex_ens),
            FOREIGN KEY (id_session) REFERENCES session(id_session),
            UNIQUE(code_smartex_ens, id_session)
        )
    """)
    
    cursor.execute("""
        CREATE INDEX IF NOT EXISTS idx_quota_ens
        ON quota_enseignant(code_smartex_ens, id_session)
    """)
    
    conn.commit()
    print("✓ Table 'quota_enseignant' créée")


def compute_quota_enseignant(affectations_df, session_id, conn):
    """
    Calculer et remplir la table quota_enseignant
    
    Args:
        affectations_df : DataFrame avec les affectations (résultat de la sauvegarde)
        session_id : ID de la session
        conn : connexion SQLite
    """
    
    print("\n" + "="*70)
    print("CALCUL DES QUOTAS PAR ENSEIGNANT")
    print("="*70)
    
    cursor = conn.cursor()
    
    # 1. Récupérer les quotas de grades et enseignants
    enseignants_query = """
        SELECT 
            e.code_smartex_ens,
            e.grade_code_ens,
            g.quota as quota_grade
        FROM enseignant e
        JOIN grade g ON e.grade_code_ens = g.code_grade
        WHERE e.participe_surveillance = 1
    """
    
    enseignants_df = pd.read_sql_query(enseignants_query, conn)
    
    # 2. Grouper par grade pour trouver la valeur majoritaire
    grades_info = {}  # grade -> {'quota_grade': X, 'professors': [list]}
    
    for grade in enseignants_df['grade_code_ens'].unique():
        profs_grade = enseignants_df[enseignants_df['grade_code_ens'] == grade]
        quota_grade = profs_grade['quota_grade'].iloc[0]
        
        grades_info[grade] = {
            'quota_grade': quota_grade,
            'professors': profs_grade['code_smartex_ens'].tolist()
        }
    
    # 3. Calculer les réalisations pour chaque enseignant
    if affectations_df.empty:
        print("⚠ Aucune affectation disponible")
        return
    
    realisations = affectations_df.groupby('code_smartex_ens').size().to_dict()
    
    # 4. Calculer les valeurs majoritaires par grade
    quotas_majoritaires = {}  # grade -> valeur_majoritaire
    
    for grade, info in grades_info.items():
        profs = info['professors']
        realisations_grade = [realisations.get(p, 0) for p in profs]
        
        if realisations_grade:
            # Trouver la valeur la plus fréquente
            from collections import Counter
            counter = Counter(realisations_grade)
            quota_majoritaire = counter.most_common(1)[0][0]
            quotas_majoritaires[grade] = quota_majoritaire
        else:
            quotas_majoritaires[grade] = 0
    
    print("\nValeurs majoritaires par grade :")
    for grade, val in sorted(quotas_majoritaires.items()):
        print(f"  {grade:3s} : {val}")
    
    # 5. Remplir la table quota_enseignant
    print("\nRemplissage de la table quota_enseignant...")
    
    data_to_insert = []
    
    for _, row in enseignants_df.iterrows():
        code = row['code_smartex_ens']
        grade = row['grade_code_ens']
        quota_grade = row['quota_grade']
        
        quota_realise = realisations.get(code, 0)
        quota_majoritaire = quotas_majoritaires[grade]
        
        # Calculer les différences
        diff_quota_grade = quota_realise - quota_grade
        diff_quota_majoritaire = quota_realise - quota_majoritaire
        
        # Calculer quota_ajuste (quota_grade - diff_quota_grade)(hne nhotou li nhebou)
        quota_ajuste = quota_grade - diff_quota_majoritaire
        
        # Calculer quota_ajuste_maj (quota_grade - diff_quota_majoritaire)
        quota_ajuste_maj = quota_grade - diff_quota_majoritaire
        
        data_to_insert.append({
            'code_smartex_ens': code,
            'id_session': session_id,
            'grade_code_ens': grade,
            'quota_grade': quota_grade,
            'quota_realise': quota_realise,
            'quota_majoritaire': quota_majoritaire,
            'diff_quota_grade': diff_quota_grade,
            'diff_quota_majoritaire': diff_quota_majoritaire,
            'quota_ajuste': quota_ajuste,
            'quota_ajuste_maj': quota_ajuste_maj
        })
    
    # 6. Insérer les données
    insert_query = """
        INSERT OR REPLACE INTO quota_enseignant (
            code_smartex_ens, id_session, grade_code_ens,
            quota_grade, quota_realise, quota_majoritaire,
            diff_quota_grade, diff_quota_majoritaire,
            quota_ajuste, quota_ajuste_maj
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    
    for data in data_to_insert:
        cursor.execute(insert_query, (
            data['code_smartex_ens'],
            data['id_session'],
            data['grade_code_ens'],
            data['quota_grade'],
            data['quota_realise'],
            data['quota_majoritaire'],
            data['diff_quota_grade'],
            data['diff_quota_majoritaire'],
            data['quota_ajuste'],
            data['quota_ajuste_maj']
        ))
    
    print(f"✓ {len(data_to_insert)} enregistrements insérés")
    
    # 7. Afficher un résumé
    print("\n" + "="*70)
    print("RÉSUMÉ PAR GRADE")
    print("="*70)
    
    summary_query = """
        SELECT 
            grade_code_ens,
            COUNT(*) as nb_profs,
            ROUND(AVG(quota_realise), 1) as moy_realise,
            MIN(quota_realise) as min_realise,
            MAX(quota_realise) as max_realise,
            quota_majoritaire,
            quota_grade
        FROM quota_enseignant
        WHERE id_session = ?
        GROUP BY grade_code_ens
        ORDER BY grade_code_ens
    """
    
    summary_df = pd.read_sql_query(summary_query, conn, params=(session_id,))
    
    for _, row in summary_df.iterrows():
        print(f"\n{row['grade_code_ens']}:")
        print(f"  Enseignants : {row['nb_profs']}")
        print(f"  Quota grade : {row['quota_grade']}")
        print(f"  Valeur majoritaire : {row['quota_majoritaire']}")
        print(f"  Réalisations : {row['min_realise']}-{row['max_realise']} (moy: {row['moy_realise']})")
    
    print("\n" + "="*70 + "\n")


def get_quota_stats(session_id, conn):
    """Récupérer les statistiques de quotas pour la session"""
    
    query = """
        SELECT 
            code_smartex_ens,
            grade_code_ens,
            quota_realise,
            quota_grade,
            quota_majoritaire,
            diff_quota_grade,
            diff_quota_majoritaire
        FROM quota_enseignant
        WHERE id_session = ?
        ORDER BY grade_code_ens, code_smartex_ens
    """
    
    return pd.read_sql_query(query, conn, params=(session_id,))


def export_quota_to_csv(session_id, conn, output_path='results/quota_enseignant.csv'):
    """Exporter les quotas à un fichier CSV"""
    
    df = get_quota_stats(session_id, conn)
    
    if not df.empty:
        df.to_csv(output_path, index=False, encoding='utf-8')
        print(f"✓ Quotas exportés vers : {output_path}")
        return df
    
    return None