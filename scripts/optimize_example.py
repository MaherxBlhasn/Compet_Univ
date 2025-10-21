#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Planificateur de surveillances avec OR-Tools CP-SAT
Version avec prise en compte des quotas ajustés de la session précédente

NOUVEAUTÉ :
- Utilise quota_ajuste et quota_ajuste_maj de la table quota_enseignant
- Priorise les enseignants avec les quotas ajustés les plus faibles
- Garantit l'équité sur plusieurs sessions
"""

import os
import sys
import json
import sqlite3
from datetime import datetime
import pandas as pd
from ortools.sat.python import cp_model

# Ajouter le dossier parent au path pour les imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.surveillance_stats import generate_statistics
from scripts.quota_enseignant_module import create_quota_enseignant_table, compute_quota_enseignant, export_quota_to_csv


# Configuration
DB_NAME = 'surveillance.db'
OUTPUT_FOLDER = 'results'


def get_db_connection():
    """Créer une connexion à la base de données"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def get_previous_session_id(conn, current_session_id):
    """Trouver la session précédente"""
    cursor = conn.cursor()
    cursor.execute("""
        SELECT id_session 
        FROM session 
        WHERE id_session < ? 
        ORDER BY id_session DESC 
        LIMIT 1
    """, (current_session_id,))
    
    row = cursor.fetchone()
    return row['id_session'] if row else None


def load_adjusted_quotas(conn, session_id):
    """
    Charger les quotas ajustés de la session précédente
    
    Returns:
        dict: {code_ens: {'quota_ajuste': X, 'quota_ajuste_maj': Y, 'grade': 'XX'}}
    """
    print("\n" + "="*60)
    print("CHARGEMENT DES QUOTAS AJUSTÉS DE LA SESSION PRÉCÉDENTE")
    print("="*60)
    
    previous_session = get_previous_session_id(conn, session_id)
    
    if previous_session is None:
        print("⚠️  Aucune session précédente trouvée")
        print("→ Utilisation des quotas de grade standards")
        return {}
    
    print(f"✓ Session précédente trouvée : {previous_session}")
    
    # Charger les quotas ajustés
    query = """
        SELECT 
            code_smartex_ens,
            grade_code_ens,
            quota_grade,
            quota_ajuste,
            quota_ajuste_maj,
            diff_quota_grade,
            diff_quota_majoritaire
        FROM quota_enseignant
        WHERE id_session = ?
    """
    
    df = pd.read_sql_query(query, conn, params=(previous_session,))
    
    adjusted_quotas = {}
    
    for _, row in df.iterrows():
        code = row['code_smartex_ens']
        adjusted_quotas[code] = {
            'grade': row['grade_code_ens'],
            'quota_grade': row['quota_grade'],
            'quota_ajuste': row['quota_ajuste'],
            'quota_ajuste_maj': row['quota_ajuste_maj'],
            'diff_quota_grade': row['diff_quota_grade'],
            'diff_quota_majoritaire': row['diff_quota_majoritaire']
        }
    
    print(f"✓ {len(adjusted_quotas)} quotas ajustés chargés")
    
    # Afficher un aperçu
    print("\n📊 Aperçu des quotas ajustés :")
    print("-" * 60)
    
    for grade in sorted(set(aq['grade'] for aq in adjusted_quotas.values())):
        grade_quotas = {k: v for k, v in adjusted_quotas.items() if v['grade'] == grade}
        
        if grade_quotas:
            avg_ajuste = sum(q['quota_ajuste'] for q in grade_quotas.values()) / len(grade_quotas)
            min_ajuste = min(q['quota_ajuste'] for q in grade_quotas.values())
            max_ajuste = max(q['quota_ajuste'] for q in grade_quotas.values())
            
            print(f"{grade:5s} : {min_ajuste:2.0f} - {max_ajuste:2.0f} (moy: {avg_ajuste:4.1f})")
    
    print("="*60)
    
    return adjusted_quotas


def load_data_from_db(session_id):
    """Charger toutes les données depuis la base de données"""
    print("\n" + "="*60)
    print("CHARGEMENT DES DONNÉES DEPUIS SQLite")
    print(f"SESSION ID : {session_id}")
    print("="*60)
    
    import time
    start_time = time.time()
    
    conn = get_db_connection()
    
    # 1. Charger les enseignants (tous, pas filtré par session)
    print("\n📊 Chargement des enseignants...")
    enseignants_df = pd.read_sql_query("""
        SELECT 
            e.code_smartex_ens,
            e.nom_ens,
            e.prenom_ens,
            e.email_ens,
            e.grade_code_ens,
            e.participe_surveillance,
            g.quota
        FROM enseignant e
        JOIN grade g ON e.grade_code_ens = g.code_grade
    """, conn)
    print(f"✓ {len(enseignants_df)} enseignants chargés")
    
    # 2. Charger les créneaux d'examen
    print("\n📅 Chargement des créneaux d'examen...")
    planning_df = pd.read_sql_query("""
        SELECT 
            creneau_id,
            dateExam,
            h_debut,
            h_fin,
            type_ex,
            semestre,
            enseignant,
            cod_salle
        FROM creneau
        WHERE id_session = ?
    """, conn, params=(session_id,))
    print(f"✓ {len(planning_df)} créneaux d'examen chargés")
    
    # 3. Créer salles_df
    print("\n🏫 Construction du fichier salles...")
    salles_df = planning_df[['dateExam', 'h_debut', 'h_fin', 'cod_salle']].copy()
    salles_df.columns = ['date_examen', 'heure_debut', 'heure_fin', 'salle']
    salles_df = salles_df.dropna(subset=['salle'])
    print(f"✓ {len(salles_df)} salles identifiées")
    
    # 4. Charger salle_par_creneau
    print("\n📊 Chargement de salle_par_creneau...")
    salle_par_creneau_df = pd.read_sql_query("""
        SELECT 
            dateExam,
            h_debut,
            nb_salle
        FROM salle_par_creneau
        WHERE id_session = ?
    """, conn, params=(session_id,))
    print(f"✓ {len(salle_par_creneau_df)} entrées salle_par_creneau")
    
    # 5. Charger les vœux
    print("\n💬 Chargement des vœux...")
    voeux_df = pd.read_sql_query("""
        SELECT 
            code_smartex_ens,
            jour,
            seance
        FROM voeu
        WHERE id_session = ?
    """, conn, params=(session_id,))
    print(f"✓ {len(voeux_df)} vœux chargés")
    
    # 6. Charger les paramètres de grades (tous, pas filtré par session)
    print("\n⚙️ Chargement des paramètres de grades...")
    parametres_df = pd.read_sql_query("""
        SELECT 
            code_grade as grade,
            quota as max_surveillances
        FROM grade
    """, conn)
    print(f"✓ {len(parametres_df)} grades chargés")
    
    # 7. Créer mapping jours/séances
    print("\n📅 Construction du mapping jours/séances...")
    dates_uniques = planning_df['dateExam'].unique()
    mapping_data = []
    
    for jour_num, date in enumerate(sorted(dates_uniques), start=1):
        heures = planning_df[planning_df['dateExam'] == date]['h_debut'].unique()
        
        for heure in sorted(heures):
            seance_code = determine_seance_from_time(heure)
            if seance_code:
                mapping_data.append({
                    'jour_num': jour_num,
                    'date': date,
                    'seance_code': seance_code,
                    'heure_debut': heure,
                    'heure_fin': None
                })
    
    mapping_df = pd.DataFrame(mapping_data)
    print(f"✓ {len(mapping_df)} mappings jour/séance créés")
    
    # 8. Charger les quotas ajustés de la session précédente
    adjusted_quotas = load_adjusted_quotas(conn, session_id)
    
    conn.close()
    
    elapsed = time.time() - start_time
    print(f"\n✓ Toutes les données chargées depuis SQLite en {elapsed:.2f}s")
    print(f"✓ Données de la session {session_id} uniquement")
    
    return enseignants_df, planning_df, salles_df, voeux_df, parametres_df, mapping_df, salle_par_creneau_df, adjusted_quotas


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


def parse_time(time_str):
    """Parse une heure au format 'HH:MM:SS' ou 'DD/MM/YYYY HH:MM:SS'"""
    if pd.isna(time_str):
        return None
    time_str = str(time_str)
    if ' ' in time_str:
        return time_str.split(' ')[1][:5]
    return time_str[:5]


def build_salle_responsable_mapping(planning_df):
    """Construire un mapping (date, heure, salle) -> code_responsable"""
    print("\n=== Construction du mapping salle -> responsable ===")
    
    planning_df['h_debut_parsed'] = planning_df['h_debut'].apply(parse_time)
    
    salle_responsable = {}
    for _, row in planning_df.iterrows():
        date = row['dateExam']
        h_debut = parse_time(row['h_debut'])
        salle = row['cod_salle']
        responsable = row['enseignant']
        
        if pd.notna(date) and pd.notna(h_debut) and pd.notna(salle) and pd.notna(responsable):
            try:
                responsable = int(responsable)
                key = (date, h_debut, salle)
                salle_responsable[key] = responsable
            except (ValueError, TypeError):
                continue
    
    print(f"✓ {len(salle_responsable)} mappings salle->responsable créés")
    return salle_responsable


def build_creneau_responsables_mapping(creneaux):
    """Construire un mapping creneau_id -> dict avec info des responsables par salle"""
    print("\n=== Construction du mapping créneau -> responsables par salle ===")
    
    creneau_responsables = {}
    
    for cid, cre in creneaux.items():
        creneau_responsables[cid] = {}
        
        for salle_info in cre['salles_info']:
            salle = salle_info['salle']
            responsable = salle_info['responsable']
            creneau_responsables[cid][salle] = responsable
    
    print(f"✓ {len(creneau_responsables)} créneaux avec infos responsables")
    
    return creneau_responsables


def build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df, nb_reserves_dynamique=None):
    """
    Construire les créneaux avec calcul correct du nombre de surveillants
    
    Args:
        nb_reserves_dynamique: Nombre de réserves par créneau (dynamique). 
                               Si None, calcul automatique basé sur le nombre de salles
    """
    print("\n=== ÉTAPE 1 : Construction des créneaux ===")
    
    salles_df['h_debut_parsed'] = salles_df['heure_debut'].apply(parse_time)
    salles_df['h_fin_parsed'] = salles_df['heure_fin'].apply(parse_time)
    
    # Créer un mapping depuis salle_par_creneau
    salle_par_creneau_df['h_debut_parsed'] = salle_par_creneau_df['h_debut'].apply(parse_time)
    nb_salles_map = {}
    for _, row in salle_par_creneau_df.iterrows():
        key = (row['dateExam'], row['h_debut_parsed'])
        nb_salles_map[key] = row['nb_salle']
    
    creneau_groups = salles_df.groupby(['date_examen', 'h_debut_parsed', 'h_fin_parsed'])
    
    creneaux = {}
    for (date, h_debut, h_fin), group in creneau_groups:
        creneau_id = f"{date}_{h_debut}"
        
        # Récupérer nb_salle depuis salle_par_creneau
        key = (date, h_debut)
        nb_salles = nb_salles_map.get(key, len(group))
        
        # CALCUL DYNAMIQUE DES RÉSERVES
        if nb_reserves_dynamique is None:
            # Calcul automatique : min(nb_salles, 4) pour éviter trop de réserves
            nb_reserves = min(nb_salles, 4)
        else:
            nb_reserves = nb_reserves_dynamique
        
        # FORMULE : 2 surveillants par salle + nb_reserves réserves par créneau
        nb_surveillants = (nb_salles * 2) + nb_reserves
        
        # Associer chaque salle à son responsable
        salles_info = []
        for salle in group['salle'].tolist():
            key_salle = (date, h_debut, salle)
            responsable = salle_responsable.get(key_salle, None)
            salles_info.append({
                'salle': salle,
                'responsable': responsable
            })
        
        creneaux[creneau_id] = {
            'creneau_id': creneau_id,
            'date': date,
            'h_debut': h_debut,
            'h_fin': h_fin,
            'nb_salles': nb_salles,
            'nb_surveillants': nb_surveillants,
            'nb_reserves': nb_reserves,
            'salles_info': salles_info
        }
    
    print(f"✓ {len(creneaux)} créneaux identifiés")
    print(f"✓ Réserves par créneau : {'dynamique' if nb_reserves_dynamique is None else nb_reserves_dynamique}")
    print(f"✓ Total surveillants requis : {sum(c['nb_surveillants'] for c in creneaux.values())}")
    
    return creneaux


def map_creneaux_to_jours_seances(creneaux, mapping_df):
    """Associer chaque créneau à son (jour, seance)"""
    print("\n=== ÉTAPE 2 : Mapping jour/séance ===")
    
    mapping_df['h_debut_parsed'] = mapping_df['heure_debut'].apply(parse_time)
    
    for cid, cre in creneaux.items():
        match = mapping_df[
            (mapping_df['date'] == cre['date']) & 
            (mapping_df['h_debut_parsed'] == cre['h_debut'])
        ]
        
        if len(match) > 0:
            cre['jour'] = int(match.iloc[0]['jour_num'])
            cre['seance'] = match.iloc[0]['seance_code']
        else:
            cre['jour'] = None
            cre['seance'] = None
    
    print(f"✓ {sum(1 for c in creneaux.values() if c['jour'] is not None)} créneaux mappés")
    return creneaux


def calculate_optimal_quotas(teachers_by_grade, total_surveillances_needed, grade_quotas_max):
    """
    Calculer les quotas optimaux pour garantir l'équité et la participation de tous
    
    CONTRAINTE IMPORTANTE : Les quotas calculés ne dépassent JAMAIS les quotas de grade
    
    Stratégie :
    1. Chaque enseignant doit avoir AU MOINS 1 surveillance
    2. Distribution équitable par grade (différence = 0)
    3. Maximiser l'utilisation de la capacité disponible
    4. RESPECTER les quotas maximum par grade (ne jamais dépasser)
    
    Args:
        teachers_by_grade: dict {grade: [list of teacher codes]}
        total_surveillances_needed: int - nombre total de surveillances nécessaires
        grade_quotas_max: dict {grade: quota_max} - quotas maximum par grade
    
    Returns:
        dict: {grade: quota_optimal}
    """
    print("\n" + "="*60)
    print("CALCUL DES QUOTAS OPTIMAUX (≤ QUOTAS DE GRADE)")
    print("="*60)
    
    # Compter les enseignants par grade
    nb_ens_by_grade = {grade: len(tcodes) for grade, tcodes in teachers_by_grade.items()}
    total_enseignants = sum(nb_ens_by_grade.values())
    
    print(f"\n📊 Enseignants participants par grade :")
    for grade in sorted(nb_ens_by_grade.keys()):
        quota_max = grade_quotas_max.get(grade, 10)
        print(f"   {grade:5s} : {nb_ens_by_grade[grade]:3d} enseignants (quota max grade: {quota_max})")
    print(f"   TOTAL : {total_enseignants:3d} enseignants")
    
    print(f"\n🎯 Surveillances totales nécessaires : {total_surveillances_needed}")
    
    # Calculer la capacité minimale (1 par enseignant)
    capacite_min = total_enseignants * 1
    print(f"   Capacité minimale (1/ens)       : {capacite_min}")
    
    if total_surveillances_needed < capacite_min:
        print(f"\n⚠️  ATTENTION : Pas assez de surveillances pour tous les enseignants!")
        print(f"   Il faudrait au moins {capacite_min} surveillances")
        print(f"   Solution : Augmenter le nombre de réserves ou de créneaux")
    
    # STRATÉGIE : Commencer avec le quota moyen nécessaire, puis ajuster
    # en respectant les limites de grade
    
    optimal_quotas = {}
    
    # Calculer un quota initial basé sur la distribution équitable
    quota_moyen_necessaire = total_surveillances_needed / total_enseignants
    
    print(f"\n📐 Quota moyen nécessaire par enseignant : {quota_moyen_necessaire:.2f}")
    
    for grade, nb_ens in nb_ens_by_grade.items():
        quota_max_grade = grade_quotas_max.get(grade, 10)
        
        # Quota initial : arrondi du quota moyen
        quota_initial = max(1, min(int(quota_moyen_necessaire) + 1, quota_max_grade))
        
        # GARANTIE : Ne JAMAIS dépasser le quota de grade
        optimal_quotas[grade] = min(quota_initial, quota_max_grade)
    
    # Vérifier la capacité totale
    capacite_totale = sum(optimal_quotas[grade] * nb_ens_by_grade[grade] 
                          for grade in optimal_quotas)
    
    print(f"   Capacité avec quotas initiaux   : {capacite_totale}")
    
    # Si capacité trop grande, réduire proportionnellement
    if capacite_totale > total_surveillances_needed * 1.5:
        print(f"\n🔧 Ajustement des quotas (capacité trop grande)")
        
        # Réduire tous les quotas d'une unité tant que possible
        while capacite_totale > total_surveillances_needed * 1.2:
            # Trouver le grade avec le quota le plus élevé
            max_grade = max(optimal_quotas.keys(), key=lambda g: optimal_quotas[g])
            
            if optimal_quotas[max_grade] > 1:
                optimal_quotas[max_grade] -= 1
                capacite_totale = sum(optimal_quotas[grade] * nb_ens_by_grade[grade] 
                                     for grade in optimal_quotas)
            else:
                break
    
    # Si capacité trop petite, augmenter (en respectant les limites de grade)
    elif capacite_totale < total_surveillances_needed:
        print(f"\n🔧 Ajustement des quotas (capacité insuffisante)")
        
        max_iterations = 1000  # Sécurité pour éviter boucle infinie
        iterations = 0
        
        while capacite_totale < total_surveillances_needed and iterations < max_iterations:
            iterations += 1
            
            # Trouver le grade qui peut être augmenté (sans dépasser son quota max)
            grades_augmentables = [
                g for g in optimal_quotas.keys() 
                if optimal_quotas[g] < grade_quotas_max.get(g, 10)
            ]
            
            if not grades_augmentables:
                print(f"   ⚠️  Impossible d'augmenter : tous les grades à leur maximum")
                print(f"   → Capacité finale : {capacite_totale} < Nécessaire : {total_surveillances_needed}")
                print(f"   → Déficit : {total_surveillances_needed - capacite_totale} surveillances")
                break
            
            # Augmenter le quota du grade avec le moins d'enseignants (parmi les augmentables)
            min_grade = min(grades_augmentables, key=lambda g: nb_ens_by_grade[g])
            
            optimal_quotas[min_grade] += 1
            capacite_totale = sum(optimal_quotas[grade] * nb_ens_by_grade[grade] 
                                 for grade in optimal_quotas)
    
    capacite_finale = sum(optimal_quotas[grade] * nb_ens_by_grade[grade] 
                         for grade in optimal_quotas)
    
    print(f"   Capacité finale                 : {capacite_finale}")
    
    if capacite_finale > 0:
        print(f"   Ratio utilisation               : {total_surveillances_needed / capacite_finale * 100:.1f}%")
    
    # VÉRIFICATION FINALE : Aucun quota ne dépasse son maximum de grade
    print(f"\n✅ Vérification des contraintes :")
    all_ok = True
    for grade in optimal_quotas:
        quota_calc = optimal_quotas[grade]
        quota_max = grade_quotas_max.get(grade, 10)
        
        if quota_calc > quota_max:
            print(f"   ❌ {grade} : {quota_calc} > {quota_max} (ERREUR!)")
            all_ok = False
            # Correction forcée
            optimal_quotas[grade] = quota_max
        else:
            print(f"   ✓ {grade} : {quota_calc} ≤ {quota_max}")
    
    if all_ok:
        print(f"   ✅ Tous les quotas respectent les limites de grade")
    else:
        print(f"   ⚠️  Corrections appliquées pour respecter les limites")
    
    print(f"\n📊 Quotas optimaux calculés :")
    print("-" * 70)
    for grade in sorted(optimal_quotas.keys()):
        nb_ens = nb_ens_by_grade[grade]
        quota = optimal_quotas[grade]
        quota_max = grade_quotas_max.get(grade, 10)
        capacite_grade = nb_ens * quota
        print(f"   {grade:5s} : quota = {quota:2d}/{quota_max:2d} | "
              f"{nb_ens:3d} ens. × {quota:2d} = {capacite_grade:3d} surveillances")
    print("-" * 70)
    
    return optimal_quotas


def build_teachers_dict(enseignants_df, parametres_df, adjusted_quotas):
    """
    Construire le dictionnaire des enseignants avec leurs quotas
    
    NOUVEAUTÉ : Utilise les quotas ajustés de la session précédente
    """
    print("\n=== ÉTAPE 3 : Préparation des enseignants avec quotas ajustés ===")
    
    # Construire le mapping grade -> quota
    grade_quotas = {}
    for _, row in parametres_df.iterrows():
        grade = str(row['grade']).strip().upper()
        quota = int(row['max_surveillances'])
        grade_quotas[grade] = quota
    
    teachers = {}
    participent = 0
    
    stats_by_grade = {}  # Pour statistiques
    
    for _, row in enseignants_df.iterrows():
        code = row['code_smartex_ens']
        
        if pd.isna(code):
            continue
        
        try:
            code = int(code)
        except (ValueError, TypeError):
            continue
        
        grade = str(row['grade_code_ens']).strip().upper()
        
        if grade not in grade_quotas:
            continue
        
        quota_base = grade_quotas[grade]
        participe = bool(row.get('participe_surveillance', True))
        
        if participe:
            participent += 1
        
        # NOUVEAUTÉ : Utiliser quota_ajuste si disponible
        if code in adjusted_quotas:
            # Utiliser le quota ajusté majoritaire pour cette session
            quota_to_use = adjusted_quotas[code]['quota_ajuste_maj']
            has_adjusted = True
            
            # Calculer la priorité inversée basée sur le quota ajusté
            # Plus le quota ajusté est FAIBLE, plus la priorité est ÉLEVÉE (numéro bas)
            # On inverse pour que ceux qui ont moins surveillé aient priorité
            adjusted_priority = -quota_to_use  # Négatif pour inverser l'ordre
        else:
            quota_to_use = quota_base
            has_adjusted = False
            adjusted_priority = 0
        
        # Priorités de grade (secondaires)
        priorite_map = {'PR': 1, 'MA': 2, 'PTC': 3, 'AC': 4, 'VA': 5}
        priorite_grade = priorite_map.get(grade, 5)
        
        teachers[code] = {
            'code': code,
            'nom': row['nom_ens'],
            'prenom': row['prenom_ens'],
            'grade': grade,
            'quota_base': quota_base,
            'quota': quota_to_use,  # Quota effectif pour cette session (sera recalculé)
            'quota_original': quota_to_use,  # Sauvegarder l'original
            'priorite_grade': priorite_grade,
            'priorite_ajustee': adjusted_priority,  # Nouvelle priorité basée sur quotas ajustés
            'participe': participe,
            'has_adjusted_quota': has_adjusted
        }
        
        # Statistiques
        if grade not in stats_by_grade:
            stats_by_grade[grade] = {
                'total': 0,
                'with_adjusted': 0,
                'quotas': []
            }
        
        stats_by_grade[grade]['total'] += 1
        if has_adjusted:
            stats_by_grade[grade]['with_adjusted'] += 1
        stats_by_grade[grade]['quotas'].append(quota_to_use)
    
    print(f"✓ {len(teachers)} enseignants chargés")
    print(f"✓ {participent} enseignants participent")
    
    # Afficher les statistiques
    print("\n📊 Statistiques des quotas par grade (avant optimisation) :")
    print("-" * 70)
    for grade in sorted(stats_by_grade.keys()):
        stats = stats_by_grade[grade]
        quotas = stats['quotas']
        min_q = min(quotas)
        max_q = max(quotas)
        avg_q = sum(quotas) / len(quotas)
        
        print(f"{grade:5s} : {stats['total']:2d} ens. | "
              f"{stats['with_adjusted']:2d} avec ajustement | "
              f"Quotas: {min_q:2.0f}-{max_q:2.0f} (moy: {avg_q:4.1f})")
    
    print("-" * 70)
    
    return teachers


def build_voeux_set(voeux_df):
    """Construire l'ensemble des vœux de non-surveillance"""
    print("\n=== ÉTAPE 4 : Traitement des vœux ===")
    
    voeux_set = set()
    
    for _, row in voeux_df.iterrows():
        code = row['code_smartex_ens']
        jour = row['jour']
        seance = row['seance']
        
        if pd.isna(code) or pd.isna(jour) or pd.isna(seance):
            continue
        
        try:
            code = int(code)
            jour = int(jour)
        except (ValueError, TypeError):
            continue
        
        voeux_set.add((code, jour, seance))
    
    print(f"✓ {len(voeux_set)} vœux de non-surveillance")
    
    return voeux_set


def get_seance_number(seance):
    """Convertir code séance en numéro (S1=1, S2=2, etc.)"""
    if pd.isna(seance):
        return None
    seance_str = str(seance).upper()
    if seance_str.startswith('S'):
        try:
            return int(seance_str[1:])
        except:
            return None
    return None


def enforce_absolute_equity_by_grade(affectations, teachers):
    """
    Post-traitement pour garantir l'équité ABSOLUE par grade
    
    Si un grade a des écarts (ex: 3 enseignants avec 8 surveillances, 6 avec 9),
    tous sont ajustés à la valeur maximale (9 dans cet exemple).
    
    Les enseignants en dessous du maximum sont marqués pour réaffectation.
    
    Returns:
        affectations_ajustees: Liste des affectations avec marquage
        needs_reaffectation: Liste des (code_ens, nb_manquant) à réaffecter
    """
    print("\n" + "="*60)
    print("POST-TRAITEMENT : ÉQUITÉ ABSOLUE PAR GRADE")
    print("="*60)
    
    # Compter les affectations par enseignant
    aff_counts = {}
    for aff in affectations:
        code = aff['code_smartex_ens']
        if code not in aff_counts:
            aff_counts[code] = 0
        aff_counts[code] += 1
    
    # Grouper par grade
    grade_stats = {}
    for code, teacher in teachers.items():
        if not teacher['participe']:
            continue
        
        grade = teacher['grade']
        if grade not in grade_stats:
            grade_stats[grade] = {
                'codes': [],
                'counts': []
            }
        
        count = aff_counts.get(code, 0)
        grade_stats[grade]['codes'].append(code)
        grade_stats[grade]['counts'].append(count)
    
    # Identifier les ajustements nécessaires
    needs_reaffectation = []
    
    print("\n📊 Analyse par grade :")
    print("-" * 70)
    
    for grade in sorted(grade_stats.keys()):
        stats = grade_stats[grade]
        counts = stats['counts']
        codes = stats['codes']
        
        if not counts:
            continue
        
        min_count = min(counts)
        max_count = max(counts)
        avg_count = sum(counts) / len(counts)
        diff = max_count - min_count
        
        print(f"{grade:5s} : {min_count:2d}-{max_count:2d} (moy: {avg_count:4.1f}) | ", end="")
        
        if diff == 0:
            print("✓ ÉQUITÉ PARFAITE")
        else:
            print(f"⚠️  ÉCART DÉTECTÉ = {diff}")
            
            # Identifier les enseignants en dessous du maximum
            for code, count in zip(codes, counts):
                if count < max_count:
                    nb_manquant = max_count - count
                    needs_reaffectation.append((code, nb_manquant))
                    teacher = teachers[code]
                    print(f"      → {teacher['nom']} {teacher['prenom']}: "
                          f"{count} → {max_count} (+{nb_manquant})")
    
    print("-" * 70)
    
    if needs_reaffectation:
        print(f"\n⚠️  {len(needs_reaffectation)} enseignants nécessitent une réaffectation")
        print("💡 SOLUTION : Augmenter les quotas maximum ou ajouter des créneaux")
        print("             pour permettre ces affectations supplémentaires")
    else:
        print("\n✅ ÉQUITÉ ABSOLUE GARANTIE pour tous les grades")
    
    return affectations, needs_reaffectation


def optimize_surveillance_scheduling(
    enseignants_df,
    planning_df,
    salles_df,
    voeux_df,
    parametres_df,
    mapping_df,
    salle_par_creneau_df,
    adjusted_quotas,
    nb_reserves_dynamique=None
):
    """
    Optimisation principale avec hiérarchie de contraintes
    
    CONTRAINTES HARD (Obligatoires) :
    - H1 : Couverture complète des créneaux
    - H2C : Responsable ne surveille pas sa propre salle
    - H3A : Respect des quotas maximum + Équilibrage entre grades
    - H4 : ÉQUITÉ ABSOLUE PAR GRADE (différence = 0) - CONTRAINTE HARD STRICTE
    - H5 : Tous les enseignants (participe_surveillance=1) ont AU MOINS 1 affectation
    
    CONTRAINTES SOFT (Par ordre de priorité décroissante) :
    - S1 : Respect des vœux (poids 100)
    - S2 : Concentration sur minimum de jours (poids 50)
    - S3 : Équilibrage de charge entre grades (poids 30)
    - S4 : Écarts individuels aux quotas (poids 10)
    - S5 : Priorité quotas ajustés (poids 8)
    - S6 : Présence responsables (poids 1)
    
    Args:
        nb_reserves_dynamique: Nombre de réserves par créneau (None = automatique)
    """
    import time
    opt_start_time = time.time()
    
    print("\n" + "="*60)
    print("DÉMARRAGE DE L'OPTIMISATION OR-TOOLS CP-SAT")
    print("AVEC ÉQUITÉ ABSOLUE PAR GRADE EN CONTRAINTE HARD")
    if nb_reserves_dynamique is not None:
        print(f"RÉSERVES DYNAMIQUES : {nb_reserves_dynamique} par créneau")
    else:
        print("RÉSERVES DYNAMIQUES : Calcul automatique")
    print("="*60)
    
    salle_responsable = build_salle_responsable_mapping(planning_df)
    creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df, nb_reserves_dynamique)
    creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
    creneau_responsables = build_creneau_responsables_mapping(creneaux)
    teachers = build_teachers_dict(enseignants_df, parametres_df, adjusted_quotas)
    voeux_set = build_voeux_set(voeux_df)
    
    prep_time = time.time() - opt_start_time
    print(f"\n⏱️  Temps de préparation : {prep_time:.2f}s")
    
    print("\n=== ÉTAPE 5 : Création du modèle CP-SAT ===")
    
    teacher_codes = [c for c, t in teachers.items() if t['participe']]
    creneau_ids = [cid for cid, c in creneaux.items() if c['jour'] is not None]
    
    # Calculer le nombre total de surveillances nécessaires
    total_surveillances_needed = sum(creneaux[cid]['nb_surveillants'] for cid in creneau_ids)
    
    print(f"\n📊 Taille du problème :")
    print(f"   - Enseignants participants : {len(teacher_codes)}")
    print(f"   - Créneaux à couvrir       : {len(creneau_ids)}")
    print(f"   - Surveillances nécessaires: {total_surveillances_needed}")
    print(f"   - Variables max possibles  : {len(teacher_codes) * len(creneau_ids):,}")
    print(f"   - Vœux de non-surveillance : {len(voeux_set)}")
    
    # Grouper par grade pour contrainte d'équité (H4)
    teachers_by_grade = {}
    grade_quotas_max = {}  # Quotas maximum par grade
    
    for tcode in teacher_codes:
        grade = teachers[tcode]['grade']
        if grade not in teachers_by_grade:
            teachers_by_grade[grade] = []
        teachers_by_grade[grade].append(tcode)
        
        # Sauvegarder le quota de base du grade
        if grade not in grade_quotas_max:
            grade_quotas_max[grade] = teachers[tcode]['quota_base']
    
    # CALCUL DES QUOTAS OPTIMAUX POUR GARANTIR L'ÉQUITÉ ET LA PARTICIPATION DE TOUS
    # AVEC RESPECT DES QUOTAS DE GRADE (quota_optimal ≤ quota_grade)
    optimal_quotas_by_grade = calculate_optimal_quotas(
        teachers_by_grade, 
        total_surveillances_needed, 
        grade_quotas_max  # NOUVEAU : passer les quotas max par grade
    )
    
    # APPLIQUER LES QUOTAS OPTIMAUX À TOUS LES ENSEIGNANTS
    print("\n" + "="*60)
    print("APPLICATION DES QUOTAS OPTIMAUX")
    print("="*60)
    
    for tcode in teacher_codes:
        grade = teachers[tcode]['grade']
        optimal_quota = optimal_quotas_by_grade[grade]
        teachers[tcode]['quota'] = optimal_quota
    
    print("\n✓ Quotas optimaux appliqués à tous les enseignants")
    print("✓ Garantie : Tous les enseignants participeront")
    print("✓ Garantie : Équité absolue par grade (différence = 0)")
    
    # Vérifier la capacité totale
    capacite_totale_optimale = sum(teachers[t]['quota'] for t in teacher_codes)
    print(f"\n📊 Capacité totale optimale : {capacite_totale_optimale}")
    print(f"   Surveillances nécessaires : {total_surveillances_needed}")
    print(f"   Ratio : {total_surveillances_needed / capacite_totale_optimale * 100:.1f}%")
    
    if capacite_totale_optimale < total_surveillances_needed:
        print(f"\n⚠️  AVERTISSEMENT : Capacité insuffisante!")
        print(f"   Manque : {total_surveillances_needed - capacite_totale_optimale} surveillances")
        print(f"   Le problème sera INFAISABLE")
        print(f"\n💡 SOLUTION : Augmenter le nombre de réserves ou réduire le nombre de créneaux")
    
    # Trier par priorité ajustée
    teachers_by_priority = sorted(
        teacher_codes,
        key=lambda t: (
            teachers[t]['priorite_ajustee'],
            teachers[t]['priorite_grade']
        )
    )
    
    print(f"\n📊 Ordre de priorité (5 premiers) :")
    for i, tcode in enumerate(teachers_by_priority[:5], 1):
        t = teachers[tcode]
        print(f"   {i}. {t['nom']} {t['prenom']} ({t['grade']}) - "
              f"Quota optimal: {t['quota']} "
              f"(Quota original: {t['quota_original']})")
    
    model = cp_model.CpModel()
    
    # =========================================================================
    # CRÉATION DES VARIABLES DE DÉCISION
    # =========================================================================
    print("\n=== Création des variables de décision ===")
    print("Variables créées : x[(enseignant, créneau)] = 0 ou 1")
    print("Exclusions appliquées :")
    print("  - H2C : Responsable ne peut pas surveiller sa propre salle")
    print("  - Les vœux NE sont PAS exclus (gérés en SOFT)")
    
    x = {}
    
    nb_vars = 0
    nb_exclusions_responsable = 0
    
    for tcode in teacher_codes:
        for cid in creneau_ids:
            cre = creneaux[cid]
            
            # CONTRAINTE H2C : L'enseignant ne peut surveiller que les salles
            # dont il n'est PAS responsable dans ce créneau
            salles_disponibles = []
            
            for salle_info in cre['salles_info']:
                salle = salle_info['salle']
                responsable = salle_info['responsable']
                
                if responsable != tcode:
                    salles_disponibles.append(salle)
            
            if not salles_disponibles:
                # L'enseignant est responsable de TOUTES les salles
                nb_exclusions_responsable += 1
                continue
            
            x[(tcode, cid)] = model.NewBoolVar(f"x_{tcode}_{cid}")
            nb_vars += 1
    
    print(f"\n✓ {nb_vars:,} variables créées")
    print(f"✓ {nb_exclusions_responsable:,} exclusions (responsable - H2C)")
    print(f"⚠️  Vœux gérés en SOFT (aucune exclusion)")
    
    # =========================================================================
    # CONTRAINTES HARD (OBLIGATOIRES)
    # =========================================================================
    print("\n" + "="*60)
    print("AJOUT DES CONTRAINTES HARD (OBLIGATOIRES)")
    print("="*60)
    
    # -------------------------------------------------------------------------
    # CONTRAINTE HARD H1 : COUVERTURE COMPLÈTE DES CRÉNEAUX
    # -------------------------------------------------------------------------
    # Chaque créneau doit avoir EXACTEMENT le nombre requis de surveillants
    # (2 titulaires par salle + 4 réserves par créneau)
    print("\n[HARD H1] Couverture complète des créneaux")
    print("Description : Chaque créneau reçoit exactement le nombre requis de surveillants")
    
    for cid in creneau_ids:
        vars_creneau = [x[(t, cid)] for t in teacher_codes if (t, cid) in x]
        required = creneaux[cid]['nb_surveillants']
        model.Add(sum(vars_creneau) == required)
    
    print(f"✓ H1 : {len(creneau_ids)} créneaux couverts exactement")
    
    # -------------------------------------------------------------------------
    # CONTRAINTE HARD H3A : RESPECT DES QUOTAS MAXIMUM + ÉQUILIBRAGE ENTRE GRADES
    # -------------------------------------------------------------------------
    # Aucun enseignant ne peut dépasser son quota maximum
    # NOUVEAU : Équilibrage des ratios réalisé/quota entre grades
    print("\n[HARD H3A] Respect des quotas maximum + Équilibrage entre grades")
    print("Description : Aucun enseignant ne dépasse son quota maximum")
    print("              NOUVEAU : Équilibrage des ratios (réalisé/quota) entre grades")
    print("              pour éviter qu'un grade soit à 100% pendant que d'autres sont à 0%")
    
    # Créer des variables pour le nombre d'affectations par enseignant
    nb_aff_per_teacher = {}
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        quota = teachers[tcode]['quota']
        
        if vars_teacher:
            # Variable pour compter les affectations
            nb_aff = model.NewIntVar(0, quota, f"nb_aff_h3a_{tcode}")
            model.Add(nb_aff == sum(vars_teacher))
            nb_aff_per_teacher[tcode] = nb_aff
            
            # Contrainte de quota maximum
            model.Add(sum(vars_teacher) <= quota)
    
    print(f"✓ H3A : {len(teacher_codes)} enseignants limités à leur quota")
    
    # SUPPRESSION DE LA CONTRAINTE HARD D'ÉQUILIBRAGE DES RATIOS
    # (Trop coûteuse en temps de calcul, déplacée en SOFT S3)
    print(f"   → Équilibrage des ratios entre grades : géré en SOFT (S3)")
    
    # -------------------------------------------------------------------------
    # CONTRAINTE HARD H4 : ÉQUITÉ ABSOLUE PAR GRADE
    # -------------------------------------------------------------------------
    # Tous les enseignants d'un même grade doivent avoir EXACTEMENT le même
    # nombre de surveillances (différence = 0)
    # CONTRAINTE ÉLIMINATOIRE : Si non satisfaite, le problème est INFAISABLE
    print("\n[HARD H4] Équité ABSOLUE par grade (différence = 0)")
    print("Description : Tous les enseignants d'un même grade ont EXACTEMENT")
    print("              le même nombre de surveillances")
    print("Type        : CONTRAINTE ÉLIMINATOIRE (HARD)")
    print("Comportement: Si impossible à satisfaire, le problème sera INFAISABLE")
    
    nb_equite_constraints = 0
    
    for grade, tcodes_grade in teachers_by_grade.items():
        if len(tcodes_grade) <= 1:
            print(f"   Grade {grade}: 1 seul enseignant, pas de contrainte d'équité")
            continue
        
        print(f"   Grade {grade}: {len(tcodes_grade)} enseignants - équité stricte imposée")
        
        # Créer des variables pour le nombre d'affectations de chaque enseignant
        nb_vars_per_teacher = {}
        for tcode in tcodes_grade:
            vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
            
            if vars_teacher:
                nb_var = model.NewIntVar(0, len(creneau_ids), f"nb_aff_{tcode}")
                model.Add(nb_var == sum(vars_teacher))
                nb_vars_per_teacher[tcode] = nb_var
        
        # Imposer que tous les enseignants du même grade aient le même nombre
        # d'affectations (égalité stricte)
        if len(nb_vars_per_teacher) > 1:
            first_teacher = list(nb_vars_per_teacher.keys())[0]
            first_nb = nb_vars_per_teacher[first_teacher]
            
            for tcode in list(nb_vars_per_teacher.keys())[1:]:
                # Contrainte HARD : nb_affectations(enseignant_i) == nb_affectations(enseignant_1)
                model.Add(nb_vars_per_teacher[tcode] == first_nb)
                nb_equite_constraints += 1
    
    print(f"✓ H4 : {nb_equite_constraints} contraintes d'égalité stricte par grade (HARD)")
    print(f"       Si non satisfaisables, le solver retournera INFAISABLE")
    
    # -------------------------------------------------------------------------
    # CONTRAINTE HARD H5 : TOUS LES ENSEIGNANTS ONT AU MOINS 1 AFFECTATION
    # -------------------------------------------------------------------------
    # Garantit que TOUS les enseignants avec participe_surveillance=1 
    # ont AU MOINS 1 affectation (aucun enseignant à 0)
    print("\n[HARD H5] Tous les enseignants ont AU MOINS 1 affectation")
    print("Description : Garantit que TOUS les enseignants participants")
    print("              ont AU MOINS 1 surveillance (aucun à 0)")
    print("Type        : CONTRAINTE ÉLIMINATOIRE (HARD)")
    
    nb_min_constraints = 0
    
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        
        if vars_teacher:
            # Contrainte HARD : au moins 1 affectation
            model.Add(sum(vars_teacher) >= 1)
            nb_min_constraints += 1
    
    print(f"✓ H5 : {nb_min_constraints} enseignants avec minimum 1 affectation garantie (HARD)")
    print(f"       Aucun enseignant ne sera à 0 surveillance")
    
    # =========================================================================
    # CONTRAINTES SOFT (OPTIMISATION PAR ORDRE DE PRIORITÉ)
    # =========================================================================
    print("\n" + "="*60)
    print("AJOUT DES CONTRAINTES SOFT (OPTIMISATION)")
    print("="*60)
    
    # -------------------------------------------------------------------------
    # CONTRAINTE SOFT S1 : RESPECT DES VŒUX
    # -------------------------------------------------------------------------
    # Les vœux de non-surveillance sont respectés autant que possible
    # Poids 100 = PRIORITÉ HAUTE
    print("\n[SOFT S1] Respect des vœux (priorité haute, poids 100)")
    print("Description : Les vœux de non-surveillance sont respectés autant que possible")
    print("Priorité    : HAUTE (poids 100)")
    print("Comportement: Si nécessaire pour l'équité, un vœu peut être non respecté")
    
    voeux_penalties = []
    
    for tcode in teacher_codes:
        for cid in creneau_ids:
            if (tcode, cid) not in x:
                continue
            
            cre = creneaux[cid]
            
            # Si l'enseignant a un vœu de non-surveillance pour ce créneau
            if (tcode, cre['jour'], cre['seance']) in voeux_set:
                # Créer une pénalité si l'enseignant est affecté malgré son vœu
                voeu_penalty = model.NewIntVar(0, 100, f"voeu_penalty_{tcode}_{cid}")
                
                # Pénalité de 100 si affecté malgré le vœu
                model.Add(voeu_penalty == 100).OnlyEnforceIf(x[(tcode, cid)])
                model.Add(voeu_penalty == 0).OnlyEnforceIf(x[(tcode, cid)].Not())
                
                voeux_penalties.append(voeu_penalty)
    
    print(f"✓ S1 : {len(voeux_penalties)} pénalités de non-respect des vœux")
    
    # -------------------------------------------------------------------------
    # CONTRAINTE SOFT S2 : CONCENTRATION SUR LE MINIMUM DE JOURS (OPTIMISÉE)
    # -------------------------------------------------------------------------
    # VERSION ULTRA-OPTIMISÉE : Moins de variables, calcul rapide
    # Poids 50 = PRIORITÉ HAUTE
    print("\n[SOFT S2] Concentration sur le minimum de jours (version ultra-optimisée, poids 50)")
    print("Description : Concentre les surveillances sur le minimum de jours possible")
    print("Priorité    : HAUTE (poids 50)")
    print("Optimisation: Version allégée pour minimiser l'impact sur performance")
    
    concentration_penalties = []
    
    # Identifier tous les jours uniques
    all_jours = sorted(set(creneaux[cid]['jour'] for cid in creneau_ids 
                          if creneaux[cid]['jour'] is not None))
    
    # OPTIMISATION : Ne créer les variables que pour les enseignants avec > 3 surveillances prévues
    # Les autres ont automatiquement une concentration naturelle
    for tcode in teacher_codes:
        quota = teachers[tcode]['quota']
        
        # FILTRE D'OPTIMISATION : Si quota ≤ 2, pas besoin de contrainte de concentration
        if quota <= 2:
            continue
        
        # Pour chaque enseignant, compter le nombre de jours différents utilisés
        jours_used_vars = []
        
        for jour in all_jours:
            # Récupérer tous les créneaux de ce jour pour cet enseignant
            creneaux_jour = [cid for cid in creneau_ids 
                            if (tcode, cid) in x and creneaux[cid]['jour'] == jour]
            
            if creneaux_jour:
                # Variable booléenne : ce jour est-il utilisé ?
                jour_used = model.NewBoolVar(f"j_{tcode}_{jour}")
                
                # jour_used = 1 SSI au moins un créneau de ce jour est affecté
                vars_jour = [x[(tcode, cid)] for cid in creneaux_jour]
                model.AddMaxEquality(jour_used, vars_jour)
                
                jours_used_vars.append(jour_used)
        
        # Pénalité = nombre de jours utilisés
        if jours_used_vars:
            # OPTIMISATION : Utiliser directement la somme sans variable intermédiaire
            concentration_penalties.append(sum(jours_used_vars))
    
    print(f"✓ S2 : {len(concentration_penalties)} enseignants avec contrainte de concentration")
    print(f"       (enseignants avec quota ≤ 2 exclus pour optimisation)")

    # -------------------------------------------------------------------------
    # CONTRAINTE SOFT S3 : ÉQUILIBRAGE DE CHARGE ENTRE GRADES (SIMPLIFIÉ)
    # -------------------------------------------------------------------------
    # Pénalise les écarts de charge entre grades
    # VERSION SIMPLIFIÉE : Sans calcul de ratios complexes
    # Poids 30 = PRIORITÉ HAUTE
    print("\n[SOFT S3] Équilibrage de charge entre grades (version simplifiée, poids 30)")
    print("Description : Pénalise les écarts de charge entre grades")
    print("Priorité    : HAUTE (poids 30)")
    print("Objectif    : Éviter qu'un grade atteigne son maximum pendant que d'autres sont à 0%")
    
    equilibrage_penalties = []
    
    # Calculer le nombre d'affectations moyen par grade
    # et pénaliser les écarts à la moyenne
    grade_aff_vars = {}
    
    for grade, tcodes_grade in teachers_by_grade.items():
        # Somme des affectations pour ce grade
        vars_grade = []
        for tcode in tcodes_grade:
            vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
            if vars_teacher:
                vars_grade.extend(vars_teacher)
        
        if vars_grade:
            grade_total = model.NewIntVar(0, len(vars_grade), f"grade_total_{grade}")
            model.Add(grade_total == sum(vars_grade))
            grade_aff_vars[grade] = (grade_total, len(tcodes_grade))
    
    if len(grade_aff_vars) > 1:
        # Calculer les ratios moyens (affectations / nb_enseignants) pour chaque grade
        # Pénaliser les écarts entre ces ratios
        
        # On va simplement pénaliser l'écart-type des moyennes par grade
        # Moyenne par enseignant du grade = total_grade / nb_ens_grade
        
        # Pour simplifier, on pénalise directement la somme des écarts
        for grade1 in grade_aff_vars:
            total1, nb_ens1 = grade_aff_vars[grade1]
            
            for grade2 in grade_aff_vars:
                if grade1 >= grade2:  # Éviter les doublons
                    continue
                
                total2, nb_ens2 = grade_aff_vars[grade2]
                
                # Écart relatif : |total1/nb_ens1 - total2/nb_ens2|
                # Pour éviter la division : |total1 * nb_ens2 - total2 * nb_ens1| / (nb_ens1 * nb_ens2)
                # On pénalise simplement |total1 * nb_ens2 - total2 * nb_ens1|
                
                diff_var = model.NewIntVar(-10000, 10000, f"diff_{grade1}_{grade2}")
                model.Add(diff_var == total1 * nb_ens2 - total2 * nb_ens1)
                
                abs_diff = model.NewIntVar(0, 10000, f"abs_diff_{grade1}_{grade2}")
                model.AddAbsEquality(abs_diff, diff_var)
                
                # Pénalité proportionnelle
                penalty = model.NewIntVar(0, 100000, f"penalty_{grade1}_{grade2}")
                model.Add(penalty == abs_diff)
                
                equilibrage_penalties.append(penalty)
        
        print(f"✓ S3 : {len(equilibrage_penalties)} pénalités d'équilibrage entre grades")
        print(f"       Favorise une distribution équilibrée entre tous les grades")
    else:
        print(f"✓ S3 : Pas d'équilibrage nécessaire (1 seul grade ou moins)")
        # Ajouter une pénalité nulle pour la compatibilité
        equilibrage_penalties.append(model.NewIntVar(0, 0, "equilibrage_penalty_dummy"))

    # -------------------------------------------------------------------------
    # CONTRAINTE SOFT S4 : ÉCARTS INDIVIDUELS AUX QUOTAS
    # -------------------------------------------------------------------------
    # Pénalise les écarts individuels par rapport aux quotas
    # Poids 10 = PRIORITÉ MOYENNE
    print("\n[SOFT S4] Écarts individuels aux quotas (poids 10)")
    print("Description : Minimise les écarts entre affectations et quotas individuels")
    print("Priorité    : MOYENNE (poids 10)")
    
    ecarts_penalties = []
    
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        
        if vars_teacher:
            quota = teachers[tcode]['quota']
            nb_aff = model.NewIntVar(0, len(creneau_ids), f"nb_aff_s4_{tcode}")
            model.Add(nb_aff == sum(vars_teacher))
            
            delta = model.NewIntVar(-len(creneau_ids), len(creneau_ids), f"delta_s4_{tcode}")
            model.Add(delta == nb_aff - quota)
            
            abs_delta = model.NewIntVar(0, len(creneau_ids), f"abs_s4_{tcode}")
            model.AddAbsEquality(abs_delta, delta)
            
            ecarts_penalties.append(abs_delta)
    
    print(f"✓ S4 : {len(ecarts_penalties)} pénalités d'écart aux quotas")

    # -------------------------------------------------------------------------
    # CONTRAINTE SOFT S5 : PRIORITÉ AUX QUOTAS AJUSTÉS FAIBLES
    # -------------------------------------------------------------------------
    # Les enseignants avec quotas ajustés faibles (qui ont moins surveillé avant)
    # sont priorisés pour surveiller moins
    # Poids 8 = PRIORITÉ MOYENNE-FAIBLE
    print("\n[SOFT S5] Priorité pour enseignants avec quotas ajustés faibles (poids 8)")
    print("Description : Les enseignants qui ont moins surveillé auparavant")
    print("              sont priorisés pour surveiller moins cette fois")
    print("Priorité    : MOYENNE-FAIBLE (poids 8)")
    
    priority_penalties = []
    
    for tcode in teacher_codes:
        if not teachers[tcode]['has_adjusted_quota']:
            continue
        
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        
        if vars_teacher:
            nb_aff = model.NewIntVar(0, len(creneau_ids), f"nb_aff_prio_{tcode}")
            model.Add(nb_aff == sum(vars_teacher))
            
            quota_ajuste = teachers[tcode]['quota']
            penalty_coef = max(1, 20 - quota_ajuste)
            
            penalty = model.NewIntVar(0, len(creneau_ids) * penalty_coef, 
                                     f"prio_penalty_{tcode}")
            model.Add(penalty == nb_aff * penalty_coef)
            
            priority_penalties.append(penalty)
    
    print(f"✓ S5 : {len(priority_penalties)} pénalités de priorité basées sur quotas ajustés")
    
    # -------------------------------------------------------------------------
    # CONTRAINTE SOFT S6 : PRÉFÉRENCE POUR RESPONSABLES DISPONIBLES
    # -------------------------------------------------------------------------
    # Préférence (légère) pour que les responsables soient présents dans leurs salles
    # Poids 1 = PRIORITÉ FAIBLE
    print("\n[SOFT S6] Préférence pour présence responsables (poids 1)")
    print("Description : Préférence légère pour que les responsables soient présents")
    print("Priorité    : FAIBLE (poids 1)")
    print("Comportement: Contrainte souple, facilement sacrifiée pour autres objectifs")
    
    presence_penalties = []
    
    for cid in creneau_ids:
        for salle, responsable in creneau_responsables[cid].items():
            if responsable is None or responsable not in teacher_codes:
                continue
            
            if (responsable, cid) in x:
                absence_penalty = model.NewIntVar(0, 100, f"resp_penalty_{responsable}_{cid}")
                
                model.Add(absence_penalty == 0).OnlyEnforceIf(x[(responsable, cid)])
                model.Add(absence_penalty == 50).OnlyEnforceIf(x[(responsable, cid)].Not())
                
                presence_penalties.append(absence_penalty)
    
    print(f"✓ S6 : {len(presence_penalties)} pénalités de présence responsable (souple)")
    
    # =========================================================================
    # DÉFINITION DE LA FONCTION OBJECTIF
    # =========================================================================
    print("\n" + "="*60)
    print("DÉFINITION DE LA FONCTION OBJECTIF")
    print("="*60)
    print("\nHiérarchie des poids (du plus important au moins important) :")
    print("  1. Respect vœux              : poids 100")
    print("  2. Concentration jours       : poids 50 (optimisée)")
    print("  3. Équilibrage entre grades  : poids dynamique")
    print("  4. Écarts aux quotas         : poids 10")
    print("  5. Priorités quotas ajustés  : poids 8")
    print("  6. Présence responsables     : poids 1")
    print("\nNOTE: L'équité absolue par grade est maintenant une contrainte HARD")
    print("      Elle sera satisfaite ou le problème sera INFAISABLE")
    print("\nNOTE: Tous les enseignants ont AU MOINS 1 affectation (contrainte HARD H5)")
    
    objective_terms = []
    
    # 1. PRIORITÉ TRÈS HAUTE : Pénalités de non-respect des vœux (poids 100)
    for penalty in voeux_penalties:
        objective_terms.append(penalty * 100)
    
    # 2. PRIORITÉ HAUTE : Concentration sur minimum de jours (poids 50)
    for penalty in concentration_penalties:
        objective_terms.append(penalty * 50)
    
    # 3. PRIORITÉ HAUTE : Équilibrage de charge entre grades (poids dynamique)
    for penalty in equilibrage_penalties:
        objective_terms.append(penalty)  # Pas de multiplication, déjà dans la pénalité
    
    # 4. Écarts individuels par rapport aux quotas (poids 10)
    for penalty in ecarts_penalties:
        objective_terms.append(penalty * 10)
    
    # 5. Pénalités de priorité basées sur quotas ajustés (poids 8)
    for penalty in priority_penalties:
        objective_terms.append(penalty * 8)
    
    # 6. Pénalités de présence responsable (poids 1)
    for penalty in presence_penalties:
        objective_terms.append(penalty * 1)
    
    model.Minimize(sum(objective_terms))
    
    model_creation_time = time.time() - opt_start_time - prep_time
    print(f"\n⏱️  Temps de création du modèle : {model_creation_time:.2f}s")
    print(f"\n✓ Fonction objectif définie avec {len(objective_terms)} termes :")
    print(f"   - Respect vœux (poids 100)          : {len(voeux_penalties)} termes")
    print(f"   - Concentration jours (poids 50)    : {len(concentration_penalties)} termes (optimisée)")
    print(f"   - Équilibrage grades (dynamique)    : {len(equilibrage_penalties)} termes")
    print(f"   - Écarts quotas (poids 10)          : {len(ecarts_penalties)} termes")
    print(f"   - Priorités ajustées (poids 8)      : {len(priority_penalties)} termes")
    print(f"   - Présence responsables (poids 1)   : {len(presence_penalties)} termes")
    
    # =========================================================================
    # RÉSOLUTION DU PROBLÈME
    # =========================================================================
    print("\n" + "="*60)
    print("RÉSOLUTION DU PROBLÈME")
    print("="*60)
    
    solver = cp_model.CpSolver()
    
    # PARAMÈTRES OPTIMISÉS POUR GRANDS PROBLÈMES
    solver.parameters.max_time_in_seconds = 600  # 10 minutes
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True
    
    # OPTIMISATIONS CRITIQUES POUR PERFORMANCE
    solver.parameters.cp_model_presolve = True
    solver.parameters.linearization_level = 2
    solver.parameters.cp_model_probing_level = 2
    
    # PARAMÈTRES AVANCÉS POUR ACCÉLÉRER (compatibles)
    solver.parameters.symmetry_level = 2  # Détection de symétries
    solver.parameters.use_sat_inprocessing = True  # Preprocessing SAT
    
    print("\nParamètres du solver (OPTIMISÉS pour grands problèmes) :")
    print(f"  - Temps maximum      : 600 secondes (10 minutes)")
    print(f"  - Nombre de workers  : 8")
    print(f"  - Logs activés       : Oui")
    print(f"  - Prétraitement      : Activé (probing level 2)")
    print(f"  - Linéarisation      : Niveau 2")
    print(f"  - Symétries          : Niveau 2 (détection avancée)")
    print(f"  - Inprocessing SAT   : Activé")
    
    status = solver.Solve(model)
    
    solve_time_only = solver.WallTime()
    total_time = time.time() - opt_start_time
    
    print(f"\n✓ Statut : {solver.StatusName(status)}")
    print(f"✓ Temps de résolution pure : {solve_time_only:.2f}s")
    print(f"✓ Temps total (préparation + modèle + résolution) : {total_time:.2f}s")
    
    affectations = []
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("\n" + "="*60)
        print("EXTRACTION DE LA SOLUTION")
        print("="*60)
        
        for (tcode, cid), var in x.items():
            if solver.Value(var) == 1:
                t = teachers[tcode]
                c = creneaux[cid]
                
                affectations.append({
                    'code_smartex_ens': tcode,
                    'nom_ens': t['nom'],
                    'prenom_ens': t['prenom'],
                    'grade_code_ens': t['grade'],
                    'quota_utilise': t['quota'],
                    'quota_ajuste': t['has_adjusted_quota'],
                    'creneau_id': cid,
                    'jour': c['jour'],
                    'seance': c['seance'],
                    'date': c['date'],
                    'h_debut': c['h_debut'],
                    'h_fin': c['h_fin'],
                    'cod_salle': None
                })
        
        print(f"✓ {len(affectations)} affectations extraites")
        
        # Statistiques sur l'utilisation des quotas ajustés
        with_adjusted = sum(1 for a in affectations if a['quota_ajuste'])
        print(f"✓ {with_adjusted} affectations avec quotas ajustés")
        
        # Vérification de l'équité par grade (doit être PARFAITE maintenant)
        print("\n📊 Vérification de l'équité par grade (CONTRAINTE HARD) :")
        print("-" * 60)
        aff_by_grade = {}
        for aff in affectations:
            grade = aff['grade_code_ens']
            code = aff['code_smartex_ens']
            if grade not in aff_by_grade:
                aff_by_grade[grade] = {}
            if code not in aff_by_grade[grade]:
                aff_by_grade[grade][code] = 0
            aff_by_grade[grade][code] += 1
        
        for grade in sorted(aff_by_grade.keys()):
            counts = list(aff_by_grade[grade].values())
            min_c = min(counts)
            max_c = max(counts)
            avg_c = sum(counts) / len(counts)
            diff = max_c - min_c
            
            # Maintenant l'équité doit TOUJOURS être parfaite (contrainte HARD)
            status_eq = "✓ PARFAIT (HARD)" if diff == 0 else f"❌ ERREUR: ÉCART={diff}"
            print(f"{grade:5s} : {min_c:2d}-{max_c:2d} (moy: {avg_c:4.1f}) | {status_eq}")
        
        print("-" * 60)
        
        affectations = assign_rooms_equitable(affectations, creneaux, planning_df)
        
        # POST-TRAITEMENT : Garantir l'équité absolue par grade
        affectations, needs_reaffectation = enforce_absolute_equity_by_grade(affectations, teachers)
        
        if needs_reaffectation:
            print("\n" + "="*60)
            print("⚠️  ATTENTION : ÉQUITÉ ABSOLUE NON GARANTIE")
            print("="*60)
            print(f"\n{len(needs_reaffectation)} enseignants nécessitent des affectations supplémentaires")
            print("\n💡 ACTIONS RECOMMANDÉES :")
            print("   1. Augmenter les quotas maximum pour les grades concernés")
            print("   2. Ajouter des créneaux de surveillance supplémentaires")
            print("   3. Réexécuter l'optimisation avec des paramètres ajustés")
            print("\n📋 Détails des réaffectations nécessaires :")
            for code, nb_manquant in needs_reaffectation:
                t = teachers[code]
                print(f"   - {t['nom']} {t['prenom']} ({t['grade']}): +{nb_manquant} surveillance(s)")
        
    else:
        print("\n" + "="*60)
        print("❌ AUCUNE SOLUTION TROUVÉE")
        print("="*60)
        if status == cp_model.INFEASIBLE:
            print("Le problème est INFAISABLE")
            print("\n⚠️  RAISONS POSSIBLES :")
            print("  1. La contrainte d'ÉQUITÉ ABSOLUE par grade ne peut être satisfaite")
            print("     avec les quotas et créneaux disponibles")
            print("  2. Le nombre total de surveillants disponibles est insuffisant")
            print("  3. Les quotas maximum par grade sont trop restrictifs")
            print("\n💡 SUGGESTIONS :")
            print("  - Vérifier que les quotas permettent une distribution équitable")
            print("  - Augmenter les quotas si nécessaire")
            print("  - Vérifier la disponibilité des enseignants par grade")
            print("  - Si l'équité absolue est impossible, la remettre en SOFT")
        elif status == cp_model.MODEL_INVALID:
            print("Le modèle est INVALIDE")
            print("Contacter l'administrateur du système")
    
    return {
        'status': 'ok' if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 'infeasible',
        'solver_status': solver.StatusName(status),
        'solve_time': solver.WallTime(),
        'affectations': affectations
    }

    
def assign_rooms_equitable(affectations, creneaux, planning_df):
    """
    Affectation ÉQUITABLE des surveillants aux salles avec distribution optimale
    
    CONTRAINTE STRICTE : La différence entre le nombre de surveillants dans deux salles
    du même créneau ne doit JAMAIS dépasser 1.
    
    Exemples valides :
    - [3, 3, 3, 3] : différence max = 0 ✓
    - [3, 3, 3, 2] : différence max = 1 ✓
    - [3, 3, 2, 2] : différence max = 1 ✓
    
    Exemples INVALIDES :
    - [4, 2, 2, 2] : différence max = 2 ✗
    - [4, 3, 2, 2] : différence max = 2 ✗
    """
    print("\n=== AFFECTATION ÉQUITABLE AUX SALLES ===")
    print("CONTRAINTE : Différence max entre salles d'un même créneau ≤ 1")
    
    # Créer le mapping (date, heure, salle) -> responsable
    planning_df['h_debut_parsed'] = planning_df['h_debut'].apply(parse_time)
    salle_responsable = {}
    for _, row in planning_df.iterrows():
        date = row['dateExam']
        h_debut = parse_time(row['h_debut'])
        salle = row['cod_salle']
        responsable = row['enseignant']
        
        if pd.notna(date) and pd.notna(h_debut) and pd.notna(salle) and pd.notna(responsable):
            try:
                responsable = int(responsable)
                key = (date, h_debut, salle)
                salle_responsable[key] = responsable
            except (ValueError, TypeError):
                continue
    
    aff_df = pd.DataFrame(affectations)
    results = []
    
    for cid in aff_df['creneau_id'].unique():
        cre_affs = aff_df[aff_df['creneau_id'] == cid].copy()
        salles_info = creneaux[cid]['salles_info']
        nb_salles = len(salles_info)
        
        total_surv = len(cre_affs)
        
        # ALGORITHME DE DISTRIBUTION ÉQUITABLE STRICTE
        # Garantit que la différence entre min et max ne dépasse JAMAIS 1
        
        # Calculer la distribution de base (division équitable)
        surv_base = total_surv // nb_salles  # Nombre de base par salle
        surv_extra = total_surv % nb_salles   # Surveillants supplémentaires à distribuer
        
        # Créer le tableau de distribution
        surv_per_salle = []
        
        # Les premières 'surv_extra' salles reçoivent (surv_base + 1) surveillants
        # Les salles restantes reçoivent 'surv_base' surveillants
        # Cela garantit automatiquement que max - min ≤ 1
        for i in range(nb_salles):
            if i < surv_extra:
                surv_per_salle.append(surv_base + 1)
            else:
                surv_per_salle.append(surv_base)
        
        # Vérification de la contrainte (différence ≤ 1)
        min_surv = min(surv_per_salle)
        max_surv = max(surv_per_salle)
        diff = max_surv - min_surv
        
        if diff > 1:
            print(f"   ❌ ERREUR {cid}: différence {diff} > 1 détectée : {surv_per_salle}")
            # Correction d'urgence si nécessaire
            # Redistribuer pour garantir diff ≤ 1
            total = sum(surv_per_salle)
            base = total // nb_salles
            extra = total % nb_salles
            surv_per_salle = [base + 1 if i < extra else base for i in range(nb_salles)]
            min_surv = min(surv_per_salle)
            max_surv = max(surv_per_salle)
            diff = max_surv - min_surv
            print(f"   ✓ Correction appliquée : {surv_per_salle} (diff={diff})")
        
        # Affectation effective
        idx = 0
        for i, salle_info in enumerate(salles_info):
            salle = salle_info['salle']
            nb_surv_salle = surv_per_salle[i]
            
            for j in range(nb_surv_salle):
                if idx < len(cre_affs):
                    row = cre_affs.iloc[idx].to_dict()
                    row['cod_salle'] = salle
                    
                    date = row['date']
                    h_debut = row['h_debut']
                    key = (date, h_debut, salle)
                    responsable_code = salle_responsable.get(key, None)
                    
                    row['responsable_salle'] = (row['code_smartex_ens'] == responsable_code)
                    
                    # Déterminer si c'est un TITULAIRE ou une RÉSERVE
                    # Les 2 premiers sont TITULAIRES, le reste RÉSERVE
                    if j < 2:
                        row['position'] = 'TITULAIRE'
                    else:
                        row['position'] = 'RESERVE'
                    
                    results.append(row)
                    idx += 1
        
        # Affichage de la distribution avec vérification
        status = "✓" if diff <= 1 else "❌"
        print(f"   {status} {cid}: {surv_per_salle} (min={min_surv}, max={max_surv}, diff={diff})")
    
    # Statistiques finales
    total_titulaires = sum(1 for r in results if r['position'] == 'TITULAIRE')
    total_reserves = sum(1 for r in results if r['position'] == 'RESERVE')
    
    print(f"\n✓ {len(results)} affectations totales")
    print(f"✓ {total_titulaires} TITULAIRES + {total_reserves} RÉSERVES")
    print(f"✓ Distribution équitable : différence max entre salles ≤ 1")
    
    return results


# Note: La fonction save_results() a été supprimée.
# La génération des CSV se fait maintenant via l'API:
# GET /api/affectations/csv/<session_id>
# Similaire à la génération des PDF: GET /api/affectations/pdf/<session_id>


def save_results_to_db(affectations, session_id):
    """Sauvegarder les résultats dans la base de données"""
    print("\n" + "="*60)
    print("SAUVEGARDE DANS LA BASE DE DONNÉES")
    print("="*60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Supprimer les anciennes affectations
    cursor.execute("""
        DELETE FROM affectation 
        WHERE id_session = ?
    """, (session_id,))
    
    deleted = cursor.rowcount
    print(f"\n🗑️ {deleted} anciennes affectations supprimées")
    
    # Créer un mapping (date, heure, salle) -> creneau_id
    creneaux_map = {}
    cursor.execute("""
        SELECT creneau_id, dateExam, h_debut, cod_salle
        FROM creneau
        WHERE id_session = ?
    """, (session_id,))
    
    for row in cursor.fetchall():
        key = (row['dateExam'], parse_time(row['h_debut']), row['cod_salle'])
        creneaux_map[key] = row['creneau_id']
    
    print(f"📋 {len(creneaux_map)} créneaux mappés")
    
    nb_inserted = 0
    nb_errors = 0
    
    for aff in affectations:
        date = aff['date']
        h_debut = aff['h_debut']
        salle = aff.get('cod_salle')
        code_ens = aff['code_smartex_ens']
        jour = aff.get('jour')
        seance = aff.get('seance')
        h_fin = aff.get('h_fin')
        position = aff.get('position', 'TITULAIRE')
        
        if not salle or pd.isna(salle):
            nb_errors += 1
            continue
        
        key = (date, h_debut, salle)
        creneau_id = creneaux_map.get(key)
        
        if creneau_id is None:
            for k, v in creneaux_map.items():
                if k[0] == date and k[1] == h_debut:
                    creneau_id = v
                    break
        
        if creneau_id:
            try:
                cursor.execute("""
                    INSERT INTO affectation (
                        code_smartex_ens, creneau_id, id_session,
                        jour, seance, date_examen, h_debut, h_fin, 
                        cod_salle, position
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (code_ens, creneau_id, session_id, jour, seance, 
                      date, h_debut, h_fin, salle, position))
                nb_inserted += 1
            except sqlite3.IntegrityError:
                nb_errors += 1
        else:
            nb_errors += 1
    
    conn.commit()
    
    print(f"\n✅ {nb_inserted} affectations insérées dans la base")
    if nb_errors > 0:
        print(f"⚠️ {nb_errors} erreurs d'insertion")
    
    conn.commit()
    conn.close()
    
    return nb_inserted


def main():
    """Point d'entrée principal"""
    print("\n" + "="*60)
    print("SYSTÈME DE PLANIFICATION DE SURVEILLANCES")
    print("Version avec Quotas Ajustés Multi-Sessions")
    print("="*60)
    
    if not os.path.exists(DB_NAME):
        print(f"\n❌ Base de données '{DB_NAME}' introuvable!")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_session, libelle_session FROM session")
    sessions = cursor.fetchall()
    conn.close()
    
    if not sessions:
        print("\n❌ Aucune session trouvée dans la base!")
        return
    
    print("\nSessions disponibles :")
    for s in sessions:
        print(f"   [{s['id_session']}] {s['libelle_session']}")
    
    session_id = int(input("\nEntrez l'ID de la session à optimiser: "))
    
    # Demander le nombre de réserves (optionnel)
    print("\n" + "="*60)
    print("CONFIGURATION DES RÉSERVES")
    print("="*60)
    print("Nombre de réserves par créneau :")
    print("  - Appuyez sur ENTRÉE pour calcul automatique (recommandé)")
    print("  - Ou entrez un nombre (ex: 4)")
    
    nb_reserves_input = input("\nVotre choix : ").strip()
    nb_reserves_dynamique = None
    
    if nb_reserves_input:
        try:
            nb_reserves_dynamique = int(nb_reserves_input)
            print(f"✓ Nombre de réserves fixé à {nb_reserves_dynamique} par créneau")
        except ValueError:
            print("⚠️  Valeur invalide, utilisation du calcul automatique")
            nb_reserves_dynamique = None
    else:
        print("✓ Calcul automatique activé")
    
    try:
        print("\nChargement des données depuis SQLite...")
        (enseignants_df, planning_df, salles_df, voeux_df, parametres_df, 
         mapping_df, salle_par_creneau_df, adjusted_quotas) = load_data_from_db(session_id)
        print("✓ Toutes les données chargées")
    except Exception as e:
        print(f"❌ Erreur de chargement : {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Lancer l'optimisation
    result = optimize_surveillance_scheduling(
        enseignants_df, planning_df, salles_df, 
        voeux_df, parametres_df, mapping_df, salle_par_creneau_df,
        adjusted_quotas,  # NOUVEAU paramètre
        nb_reserves_dynamique  # Paramètre dynamique pour les réserves
    )
    
    # Sauvegarder les résultats
    if result['status'] == 'ok' and len(result['affectations']) > 0:
        # Construire les structures nécessaires pour les stats
        salle_responsable = build_salle_responsable_mapping(planning_df)
        creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df, nb_reserves_dynamique)
        creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
        teachers = build_teachers_dict(enseignants_df, parametres_df, adjusted_quotas)
        voeux_set = build_voeux_set(voeux_df)
        
        stats = generate_statistics(
            result['affectations'],
            creneaux,
            teachers,
            voeux_set,
            planning_df
        )
        
        # Note: La génération des CSV se fait maintenant via l'API
        # GET /api/affectations/csv/<session_id>
        
        # Sauvegarder dans la base de données
        nb_inserted = save_results_to_db(result['affectations'], session_id)
        
        if nb_inserted > 0:
            print(f"\n✅ {nb_inserted} affectations sauvegardées en base de données")
            
            # CALCUL ET SAUVEGARDE DES QUOTAS
            print("\n" + "="*60)
            print("CALCUL DES QUOTAS PAR ENSEIGNANT")
            print("="*60)
            
            try:
                conn = get_db_connection()
                create_quota_enseignant_table(conn)
                
                # Récupérer les affectations
                affectations_query = """
                    SELECT code_smartex_ens, creneau_id, id_session, position
                    FROM affectation WHERE id_session = ?
                """
                affectations_df = pd.read_sql_query(affectations_query, conn, params=(session_id,))
                
                # Calculer et remplir la table
                compute_quota_enseignant(affectations_df, session_id, conn)
                
                # Exporter en CSV
                quota_output = os.path.join(OUTPUT_FOLDER, 'quota_enseignant.csv')
                quota_df = export_quota_to_csv(session_id, conn, quota_output)
                
                if quota_df is not None:
                    print(f"\n✅ Quotas exportés : {quota_output}")
                
                conn.commit()
                conn.close()
                
            except Exception as e:
                print(f"\n❌ Erreur lors du calcul des quotas : {e}")
    
    # Afficher le résumé final
    print("\n" + "="*60)
    print("RÉSUMÉ FINAL")
    print("="*60)
    print(f"Statut : {result['status']}")
    print(f"Affectations : {len(result['affectations'])}")
    print(f"Fichiers dans : {OUTPUT_FOLDER}")
    
    print("\nCONTRAINTES APPLIQUÉES :")
    print("   [HARD H1] ✓ Couverture complète des créneaux")
    print("   [HARD H2C] ✓ Responsable ne surveille pas sa propre salle")
    print("   [HARD H3A] ✓ Respect des quotas maximum optimaux (≤ quota_grade)")
    print("   [HARD H4] ✓ Équité absolue par grade (différence = 0)")
    print("   [HARD H5] ✓ Tous les enseignants ont AU MOINS 1 affectation")
    print("   [SOFT S1] ✓ Respect des vœux (poids 100)")
    print("   [SOFT S2] ✓ Concentration jours (poids 50, OPTIMISÉE)")
    print("   [SOFT S3] ✓ Équilibrage de charge entre grades (poids dynamique)")
    print("   [SOFT S4] ✓ Écarts individuels aux quotas (poids 10)")
    print("   [SOFT S5] ✓ Priorité quotas ajustés faibles (poids 8)")
    print("   [SOFT S6] ✓ Préférence présence responsables (poids 1)")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
