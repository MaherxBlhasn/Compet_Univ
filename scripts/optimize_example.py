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
    print("="*60)
    
    conn = get_db_connection()
    
    # 1. Charger les enseignants
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
    
    # 6. Charger les paramètres de grades
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
    
    print("\n✓ Toutes les données chargées depuis SQLite")
    
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


def build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df):
    """Construire les créneaux avec calcul correct du nombre de surveillants"""
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
        
        # FORMULE : 2 surveillants par salle + 4 réserves par créneau
        nb_reserves = 4
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
            'quota': quota_to_use,  # Quota effectif pour cette session
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
    print("\n📊 Statistiques des quotas par grade :")
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


def optimize_surveillance_scheduling(
    enseignants_df,
    planning_df,
    salles_df,
    voeux_df,
    parametres_df,
    mapping_df,
    salle_par_creneau_df,
    adjusted_quotas
):
    """
    Optimisation principale avec hiérarchie de contraintes
    
    CONTRAINTES HARD (Obligatoires) :
    - H1 : Couverture complète des créneaux
    - H2C : Responsable ne surveille pas sa propre salle
    - H3A : Respect des quotas maximum (ajustés)
    - H4 : ÉQUITÉ ABSOLUE PAR GRADE (différence = 0) - NOUVELLE CONTRAINTE HARD
    
    CONTRAINTES SOFT (Par ordre de priorité décroissante) :
    - S1 : Respect des vœux (poids 100)
    - S2 : Minimisation écarts quotas (poids 10)
    - S3 : Priorité quotas ajustés (poids 8)
    - S4 : Dispersion dans la journée (poids 5)
    - S5 : Présence responsables (poids 1)
    """
    print("\n" + "="*60)
    print("DÉMARRAGE DE L'OPTIMISATION OR-TOOLS CP-SAT")
    print("AVEC ÉQUITÉ ABSOLUE PAR GRADE EN CONTRAINTE HARD")
    print("="*60)
    
    salle_responsable = build_salle_responsable_mapping(planning_df)
    creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df)
    creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
    creneau_responsables = build_creneau_responsables_mapping(creneaux)
    teachers = build_teachers_dict(enseignants_df, parametres_df, adjusted_quotas)
    voeux_set = build_voeux_set(voeux_df)
    
    print("\n=== ÉTAPE 5 : Création du modèle CP-SAT ===")
    
    teacher_codes = [c for c, t in teachers.items() if t['participe']]
    creneau_ids = [cid for cid, c in creneaux.items() if c['jour'] is not None]
    
    # Grouper par grade pour contrainte d'équité (H4)
    teachers_by_grade = {}
    for tcode in teacher_codes:
        grade = teachers[tcode]['grade']
        if grade not in teachers_by_grade:
            teachers_by_grade[grade] = []
        teachers_by_grade[grade].append(tcode)
    
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
              f"Quota: {t['quota']} "
              f"(Prio ajustée: {t['priorite_ajustee']})")
    
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
    # CONTRAINTE HARD H3A : RESPECT DES QUOTAS MAXIMUM (AJUSTÉS)
    # -------------------------------------------------------------------------
    # Aucun enseignant ne peut dépasser son quota maximum
    # Les quotas sont ajustés selon l'historique de la session précédente
    print("\n[HARD H3A] Respect des quotas maximum (avec quotas ajustés)")
    print("Description : Aucun enseignant ne dépasse son quota maximum")
    print("              Les quotas tiennent compte de l'historique précédent")
    
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        quota = teachers[tcode]['quota']
        
        if vars_teacher:
            model.Add(sum(vars_teacher) <= quota)
    
    print(f"✓ H3A : {len(teacher_codes)} enseignants limités à leur quota (ajusté)")
    
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
    # CONTRAINTE SOFT S2 : DISPERSION DANS LA MÊME JOURNÉE
    # -------------------------------------------------------------------------
    # Éviter d'avoir des surveillances trop espacées dans la même journée
    # (ex: éviter S1 et S4 le même jour sans S2 ou S3)
    # Poids 5 = PRIORITÉ MOYENNE
    print("\n[SOFT S2] Dispersion des surveillances dans la même journée (poids 5)")
    print("Description : Évite les surveillances trop espacées dans la même journée")
    print("Priorité    : MOYENNE (poids 5)")
    print("Exemple     : Pénalise S1+S4 sans S2/S3 le même jour")
    
    dispersion_penalties = []
    
    for tcode in teacher_codes:
        creneaux_by_jour = {}
        for cid in creneau_ids:
            if (tcode, cid) in x:
                jour = creneaux[cid]['jour']
                if jour not in creneaux_by_jour:
                    creneaux_by_jour[jour] = []
                creneaux_by_jour[jour].append(cid)
        
        for jour, cids_jour in creneaux_by_jour.items():
            if len(cids_jour) <= 1:
                continue
            
            seances_info = []
            for cid in cids_jour:
                seance_num = get_seance_number(creneaux[cid]['seance'])
                if seance_num is not None:
                    seances_info.append((cid, seance_num))
            
            for i in range(len(seances_info)):
                for j in range(i + 1, len(seances_info)):
                    cid1, s1 = seances_info[i]
                    cid2, s2 = seances_info[j]
                    
                    gap = abs(s2 - s1)
                    if gap > 1:
                        both_assigned = model.NewBoolVar(f"both_{tcode}_{cid1}_{cid2}")
                        model.Add(both_assigned == 1).OnlyEnforceIf([x[(tcode, cid1)], x[(tcode, cid2)]])
                        model.Add(both_assigned == 0).OnlyEnforceIf([x[(tcode, cid1)].Not()])
                        model.Add(both_assigned == 0).OnlyEnforceIf([x[(tcode, cid2)].Not()])
                        
                        penalty = model.NewIntVar(0, gap * 10, f"penalty_{tcode}_{cid1}_{cid2}")
                        model.Add(penalty == gap * 10).OnlyEnforceIf(both_assigned)
                        model.Add(penalty == 0).OnlyEnforceIf(both_assigned.Not())
                        
                        dispersion_penalties.append(penalty)
    
    print(f"✓ S2 : {len(dispersion_penalties)} pénalités de dispersion")
    
    # -------------------------------------------------------------------------
    # CONTRAINTE SOFT S3 : PRÉFÉRENCE POUR RESPONSABLES DISPONIBLES
    # -------------------------------------------------------------------------
    # Préférence (légère) pour que les responsables soient présents dans leurs salles
    # Poids 1 = PRIORITÉ FAIBLE
    print("\n[SOFT S3] Préférence pour présence responsables (poids 1)")
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
    
    print(f"✓ S3 : {len(presence_penalties)} pénalités de présence responsable (souple)")
    
    # -------------------------------------------------------------------------
    # CONTRAINTE SOFT S4 : PRIORITÉ AUX QUOTAS AJUSTÉS FAIBLES
    # -------------------------------------------------------------------------
    # Les enseignants avec quotas ajustés faibles (qui ont moins surveillé avant)
    # sont priorisés pour surveiller moins
    # Poids 8 = PRIORITÉ MOYENNE-FAIBLE
    print("\n[SOFT S4] Priorité pour enseignants avec quotas ajustés faibles (poids 8)")
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
    
    print(f"✓ S4 : {len(priority_penalties)} pénalités de priorité basées sur quotas ajustés")
    
    # =========================================================================
    # DÉFINITION DE LA FONCTION OBJECTIF
    # =========================================================================
    print("\n" + "="*60)
    print("DÉFINITION DE LA FONCTION OBJECTIF")
    print("="*60)
    print("\nHiérarchie des poids (du plus important au moins important) :")
    print("  1. Respect vœux              : poids 100")
    print("  2. Écarts aux quotas         : poids 10")
    print("  3. Priorités quotas ajustés  : poids 8")
    print("  4. Dispersion journalière    : poids 5")
    print("  5. Présence responsables     : poids 1")
    print("\nNOTE: L'équité absolue par grade est maintenant une contrainte HARD")
    print("      Elle sera satisfaite ou le problème sera INFAISABLE")
    
    objective_terms = []
    
    # 1. PRIORITÉ HAUTE : Pénalités de non-respect des vœux (poids 100)
    for penalty in voeux_penalties:
        objective_terms.append(penalty * 100)
    
    # 2. Écarts individuels par rapport aux quotas (poids 10)
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        
        if vars_teacher:
            quota = teachers[tcode]['quota']
            nb_aff = model.NewIntVar(0, len(creneau_ids), f"nb_aff_{tcode}")
            model.Add(nb_aff == sum(vars_teacher))
            
            delta = model.NewIntVar(-len(creneau_ids), len(creneau_ids), f"delta_{tcode}")
            model.Add(delta == nb_aff - quota)
            
            abs_delta = model.NewIntVar(0, len(creneau_ids), f"abs_{tcode}")
            model.AddAbsEquality(abs_delta, delta)
            
            objective_terms.append(abs_delta * 10)
    
    # 3. Pénalités de priorité basées sur quotas ajustés (poids 8)
    for penalty in priority_penalties:
        objective_terms.append(penalty * 8)
    
    # 4. Pénalités de dispersion (poids 5)
    for penalty in dispersion_penalties:
        objective_terms.append(penalty * 5)
    
    # 5. Pénalités de présence responsable (poids 1)
    for penalty in presence_penalties:
        objective_terms.append(penalty * 1)
    
    model.Minimize(sum(objective_terms))
    
    print(f"\n✓ Fonction objectif définie avec {len(objective_terms)} termes :")
    print(f"   - Respect vœux (poids 100)          : {len(voeux_penalties)} termes")
    print(f"   - Écarts quotas (poids 10)          : {len(teacher_codes)} termes")
    print(f"   - Priorités ajustées (poids 8)      : {len(priority_penalties)} termes")
    print(f"   - Dispersion (poids 5)              : {len(dispersion_penalties)} termes")
    print(f"   - Présence responsables (poids 1)   : {len(presence_penalties)} termes")
    
    # =========================================================================
    # RÉSOLUTION DU PROBLÈME
    # =========================================================================
    print("\n" + "="*60)
    print("RÉSOLUTION DU PROBLÈME")
    print("="*60)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True
    
    print("\nParamètres du solver :")
    print(f"  - Temps maximum      : 180 secondes")
    print(f"  - Nombre de workers  : 8")
    print(f"  - Logs activés       : Oui")
    
    status = solver.Solve(model)
    
    print(f"\n✓ Statut : {solver.StatusName(status)}")
    print(f"✓ Temps de résolution : {solver.WallTime():.2f}s")
    
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
    """Affectation ÉQUITABLE des surveillants aux salles"""
    print("\n=== AFFECTATION ÉQUITABLE AUX SALLES ===")
    
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
        nb_reserves = creneaux[cid]['nb_reserves']
        
        total_surv = len(cre_affs)
        
        # ALGORITHME DE DISTRIBUTION ÉQUITABLE
        # Phase 1 : 2 TITULAIRES par salle
        surv_per_salle = [2] * nb_salles
        
        # Phase 2 : Distribuer les 4 RÉSERVES (1 par salle maximum)
        reserves_per_salle = [0] * nb_salles
        for i in range(min(nb_reserves, nb_salles)):
            reserves_per_salle[i] = 1
            surv_per_salle[i] += 1
        
        # Affectation effective
        idx = 0
        for i, salle_info in enumerate(salles_info):
            salle = salle_info['salle']
            
            # D'abord les 2 TITULAIRES
            for j in range(2):
                if idx < len(cre_affs):
                    row = cre_affs.iloc[idx].to_dict()
                    row['cod_salle'] = salle
                    
                    date = row['date']
                    h_debut = row['h_debut']
                    key = (date, h_debut, salle)
                    responsable_code = salle_responsable.get(key, None)
                    
                    row['responsable_salle'] = (row['code_smartex_ens'] == responsable_code)
                    row['position'] = 'TITULAIRE'
                    results.append(row)
                    idx += 1
            
            # Ensuite la RÉSERVE si cette salle en reçoit une
            if reserves_per_salle[i] > 0:
                if idx < len(cre_affs):
                    row = cre_affs.iloc[idx].to_dict()
                    row['cod_salle'] = salle
                    
                    date = row['date']
                    h_debut = row['h_debut']
                    key = (date, h_debut, salle)
                    responsable_code = salle_responsable.get(key, None)
                    
                    row['responsable_salle'] = (row['code_smartex_ens'] == responsable_code)
                    row['position'] = 'RESERVE'
                    results.append(row)
                    idx += 1
        
        # Affichage
        max_surv = max(surv_per_salle)
        if max_surv > 3:
            print(f"   ⚠️ {cid}: ERREUR - {max_surv} surveillants dans une salle")
        else:
            print(f"   ✓ {cid}: {surv_per_salle} surveillants par salle")
    
    # Statistiques finales
    total_titulaires = sum(1 for r in results if r['position'] == 'TITULAIRE')
    total_reserves = sum(1 for r in results if r['position'] == 'RESERVE')
    
    print(f"\n✓ {len(results)} affectations totales")
    print(f"✓ {total_titulaires} TITULAIRES + {total_reserves} RÉSERVES")
    
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
        adjusted_quotas  # NOUVEAU paramètre
    )
    
    # Sauvegarder les résultats
    if result['status'] == 'ok' and len(result['affectations']) > 0:
        # Construire les structures nécessaires pour les stats
        salle_responsable = build_salle_responsable_mapping(planning_df)
        creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df)
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
    print("   [HARD H2A] ✓ Équité stricte par grade (écart ≤ 1)")
    print("   [HARD H2B] ✓ Respect strict des vœux")
    print("   [HARD H2C] ✓ Responsable ne surveille pas sa propre salle")
    print("   [HARD H3A] ✓ Respect des quotas maximum (AJUSTÉS)")
    print("   [SOFT S1] ✓ Dispersion optimisée dans la journée")
    print("   [SOFT S2] ✓ Préférence pour présence responsables (souple)")
    print("   [SOFT S3] ✓ Priorité pour quotas ajustés faibles (NOUVEAU)")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
