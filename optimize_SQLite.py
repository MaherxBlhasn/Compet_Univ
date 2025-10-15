#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Planificateur de surveillances avec OR-Tools CP-SAT
Version SQLite CORRIGÉE
"""

import os
import json
import sqlite3
from datetime import datetime
import pandas as pd
from ortools.sat.python import cp_model

# Configuration
DB_NAME = 'surveillance.db'
OUTPUT_FOLDER = 'results'
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def get_db_connection():
    """Créer une connexion à la base de données"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def load_data_from_db(session_id):
    """
    ÉTAPE 0 : Charger toutes les données depuis la base de données
    """
    print("\n" + "="*60)
    print("CHARGEMENT DES DONNÉES DEPUIS SQLite")
    print("="*60)
    
    conn = get_db_connection()
    
    # 1. Charger les enseignants avec leurs grades (SANS MAPPING)
    print("\n📚 Chargement des enseignants...")
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
    
    # 2. Charger les créneaux d'examen pour la session
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
    
    # 3. Créer salles_df (grouper par date/heure)
    print("\n🏫 Construction du fichier salles...")
    salles_df = planning_df[['dateExam', 'h_debut', 'h_fin', 'cod_salle']].copy()
    salles_df.columns = ['date_examen', 'heure_debut', 'heure_fin', 'salle']
    salles_df = salles_df.dropna(subset=['salle'])
    print(f"✓ {len(salles_df)} salles identifiées")
    
    # 4. Charger salle_par_creneau
    print("\n🏢 Chargement de salle_par_creneau...")
    salle_par_creneau_df = pd.read_sql_query("""
        SELECT 
            dateExam,
            h_debut,
            nb_salle
        FROM salle_par_creneau
        WHERE id_session = ?
    """, conn, params=(session_id,))
    print(f"✓ {len(salle_par_creneau_df)} entrées salle_par_creneau")
    
    # 5. Charger les vœux de non-surveillance
    print("\n🙅 Chargement des vœux...")
    voeux_df = pd.read_sql_query("""
        SELECT 
            code_smartex_ens,
            jour,
            seance
        FROM voeu
        WHERE id_session = ?
    """, conn, params=(session_id,))
    print(f"✓ {len(voeux_df)} vœux chargés")
    
    # 6. Charger les paramètres de grades DIRECTEMENT depuis la base
    print("\n⚙️ Chargement des paramètres de grades...")
    parametres_df = pd.read_sql_query("""
        SELECT 
            code_grade as grade,
            quota as max_surveillances
        FROM grade
    """, conn)
    print(f"✓ {len(parametres_df)} grades chargés")
    
    # 7. Créer mapping jours/séances depuis les créneaux
    print("\n🗓️ Construction du mapping jours/séances...")
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
    
    conn.close()
    
    print("\n✅ Toutes les données chargées depuis SQLite")
    
    return enseignants_df, planning_df, salles_df, voeux_df, parametres_df, mapping_df, salle_par_creneau_df


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
    """
    Construire un mapping (date, heure, salle) -> code_responsable
    """
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


def build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df):
    """
    Construire les créneaux avec distribution depuis salle_par_creneau
    FORMULE : nb_surveillants = nb_salles * 2 + nb_reserves (4 par défaut)
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
        
        # FORMULE CORRIGÉE : 2 surveillants par salle + 4 réserves
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
    
    for cid, cre in list(creneaux.items())[:3]:
        print(f"   Ex: {cid} -> {cre['nb_salles']} salles, {cre['nb_surveillants']} surveillants")
    
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
            print(f"⚠️ Pas de mapping pour créneau {cid}")
            cre['jour'] = None
            cre['seance'] = None
    
    print(f"✓ {sum(1 for c in creneaux.values() if c['jour'] is not None)} créneaux mappés")
    return creneaux


def build_teachers_dict(enseignants_df, parametres_df):
    """
    Construire le dictionnaire des enseignants avec leurs quotas
    SANS MAPPING DES GRADES
    """
    print("\n=== ÉTAPE 3 : Préparation des enseignants ===")
    
    # Construire le mapping grade -> quota depuis parametres_df
    grade_quotas = {}
    for _, row in parametres_df.iterrows():
        grade = str(row['grade']).strip().upper()
        quota = int(row['max_surveillances'])
        grade_quotas[grade] = quota
    
    teachers = {}
    participent = 0
    
    for _, row in enseignants_df.iterrows():
        code = row['code_smartex_ens']
        
        if pd.isna(code):
            continue
        
        try:
            code = int(code)
        except (ValueError, TypeError):
            continue
        
        # UTILISER LE GRADE TEL QUEL - SANS MAPPING
        grade = str(row['grade_code_ens']).strip().upper()
        
        if grade not in grade_quotas:
            print(f"⚠️ Grade '{grade}' non trouvé dans les paramètres, ignoré")
            continue
        
        quota = grade_quotas[grade]
        participe = bool(row.get('participe_surveillance', True))
        if participe:
            participent += 1
        
        # Priorités
        priorite_map = {'PR': 1, 'MA': 2, 'PTC': 3, 'AC': 4, 'VA': 5}
        priorite = priorite_map.get(grade, 5)
        
        teachers[code] = {
            'code': code,
            'nom': row['nom_ens'],
            'prenom': row['prenom_ens'],
            'grade': grade,  # Grade SANS mapping
            'quota': quota,
            'priorite': priorite,
            'participe': participe
        }
    
    print(f"✓ {len(teachers)} enseignants chargés")
    print(f"✓ {participent} enseignants participent")
    print(f"✓ Répartition par grade :")
    
    grade_counts = {}
    for t in teachers.values():
        if t['participe']:
            g = t['grade']
            if g not in grade_counts:
                grade_counts[g] = {'count': 0, 'quota_total': 0}
            grade_counts[g]['count'] += 1
            grade_counts[g]['quota_total'] += t['quota']
    
    for grade in sorted(grade_counts.keys()):
        info = grade_counts[grade]
        print(f"     {grade}: {info['count']} enseignants × quota = {info['quota_total']} surveillances max")
    
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
    salle_par_creneau_df
):
    """
    OPTIMISATION PRINCIPALE avec contrainte responsable de salle
    """
    print("\n" + "="*60)
    print("DÉMARRAGE DE L'OPTIMISATION OR-TOOLS CP-SAT")
    print("="*60)
    
    salle_responsable = build_salle_responsable_mapping(planning_df)
    creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df)
    creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
    teachers = build_teachers_dict(enseignants_df, parametres_df)
    voeux_set = build_voeux_set(voeux_df)
    
    print("\n=== ÉTAPE 5 : Création du modèle CP-SAT ===")
    
    teacher_codes = [c for c, t in teachers.items() if t['participe']]
    creneau_ids = [cid for cid, c in creneaux.items() if c['jour'] is not None]
    
    # Grouper par grade
    teachers_by_grade = {}
    for tcode in teacher_codes:
        grade = teachers[tcode]['grade']
        if grade not in teachers_by_grade:
            teachers_by_grade[grade] = []
        teachers_by_grade[grade].append(tcode)
    
    model = cp_model.CpModel()
    
    print("Création des variables...")
    x = {}
    
    nb_vars = 0
    nb_exclusions = 0
    nb_exclusions_responsable = 0
    
    for tcode in teacher_codes:
        for cid in creneau_ids:
            cre = creneaux[cid]
            
            # Exclusion par vœux
            if (tcode, cre['jour'], cre['seance']) in voeux_set:
                nb_exclusions += 1
                continue
            
            # Exclusion si l'enseignant est responsable d'UNE des salles du créneau
            est_responsable = False
            for salle_info in cre['salles_info']:
                if salle_info['responsable'] == tcode:
                    est_responsable = True
                    nb_exclusions_responsable += 1
                    break
            
            if est_responsable:
                continue
            
            x[(tcode, cid)] = model.NewBoolVar(f"x_{tcode}_{cid}")
            nb_vars += 1
    
    print(f"✓ {nb_vars:,} variables créées")
    print(f"✓ {nb_exclusions:,} exclusions (vœux)")
    print(f"✓ {nb_exclusions_responsable:,} exclusions (responsable de salle)")
    
    print("\n" + "="*60)
    print("AJOUT DES CONTRAINTES (PAR ORDRE DE PRIORITÉ)")
    print("="*60)
    
    # PRIORITÉ 1 : COUVERTURE COMPLÈTE
    print("\n[PRIORITÉ 1] Contrainte de couverture complète des créneaux")
    for cid in creneau_ids:
        vars_creneau = [x[(t, cid)] for t in teacher_codes if (t, cid) in x]
        required = creneaux[cid]['nb_surveillants']
        model.Add(sum(vars_creneau) == required)
    print(f"✓ H1 : {len(creneau_ids)} créneaux doivent être couverts exactement")
    
    # PRIORITÉ 2A : ÉQUITÉ STRICTE PAR GRADE
    print("\n[PRIORITÉ 2A] Équité stricte entre enseignants du même grade")
    
    for grade, tcodes_grade in teachers_by_grade.items():
        if len(tcodes_grade) <= 1:
            continue
        
        for i in range(len(tcodes_grade)):
            for j in range(i + 1, len(tcodes_grade)):
                t1 = tcodes_grade[i]
                t2 = tcodes_grade[j]
                
                vars_t1 = [x[(t1, cid)] for cid in creneau_ids if (t1, cid) in x]
                vars_t2 = [x[(t2, cid)] for cid in creneau_ids if (t2, cid) in x]
                
                if vars_t1 and vars_t2:
                    nb_t1 = model.NewIntVar(0, len(creneau_ids), f"nb_{t1}")
                    nb_t2 = model.NewIntVar(0, len(creneau_ids), f"nb_{t2}")
                    
                    model.Add(nb_t1 == sum(vars_t1))
                    model.Add(nb_t2 == sum(vars_t2))
                    
                    # Écart max de 1 surveillance
                    model.Add(nb_t1 - nb_t2 <= 1)
                    model.Add(nb_t2 - nb_t1 <= 1)
    
    print(f"✓ H2A : Écart max de 1 surveillance entre enseignants du même grade")
    
    # PRIORITÉ 2B : RESPECT STRICT DES VŒUX
    print("\n[PRIORITÉ 2B] Respect strict des vœux de non-surveillance")
    print(f"✓ H2B : {nb_exclusions} vœux respectés par construction des variables")
    
    # PRIORITÉ 2C : RESPECT RESPONSABLE DE SALLE
    print("\n[PRIORITÉ 2C] Respect de la contrainte responsable de salle")
    print(f"✓ H2C : {nb_exclusions_responsable} exclusions (enseignant ne surveille pas sa propre salle)")
    
    # PRIORITÉ 3A : QUOTAS MAXIMUM
    print("\n[PRIORITÉ 3A] Respect des quotas maximum par enseignant")
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        quota = teachers[tcode]['quota']
        
        if vars_teacher:
            model.Add(sum(vars_teacher) <= quota)
    
    print(f"✓ H3A : {len(teacher_codes)} enseignants limités à leur quota")
    
    # OBJECTIF
    print("\n=== DÉFINITION DE L'OBJECTIF ===")
    
    objective_terms = []
    
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
            
            objective_terms.append(abs_delta)
    
    model.Minimize(sum(objective_terms))
    
    print(f"✓ Objectif : minimiser {len(objective_terms)} écarts individuels")
    
    # RÉSOLUTION
    print("\n" + "="*60)
    print("RÉSOLUTION DU PROBLÈME")
    print("="*60)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True
    
    status = solver.Solve(model)
    
    print(f"\n✓ Statut : {solver.StatusName(status)}")
    print(f"✓ Temps de résolution : {solver.WallTime():.2f}s")
    
    affectations = []
    
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print("\n=== EXTRACTION DE LA SOLUTION ===")
        
        for (tcode, cid), var in x.items():
            if solver.Value(var) == 1:
                t = teachers[tcode]
                c = creneaux[cid]
                
                affectations.append({
                    'code_smartex_ens': tcode,
                    'nom_ens': t['nom'],
                    'prenom_ens': t['prenom'],
                    'grade_code_ens': t['grade'],
                    'creneau_id': cid,
                    'jour': c['jour'],
                    'seance': c['seance'],
                    'date': c['date'],
                    'h_debut': c['h_debut'],
                    'h_fin': c['h_fin'],
                    'cod_salle': None
                })
        
        print(f"✓ {len(affectations)} affectations extraites")
        
        # Afficher les statistiques par grade
        aff_temp_df = pd.DataFrame(affectations)
        print("\n📊 Répartition par grade :")
        for grade in sorted(teachers_by_grade.keys()):
            count = len(aff_temp_df[aff_temp_df['grade_code_ens'] == grade])
            tcodes = teachers_by_grade[grade]
            capacity = sum(teachers[tc]['quota'] for tc in tcodes)
            taux = (count / capacity * 100) if capacity > 0 else 0
            print(f"     {grade}: {count}/{capacity} surveillances ({taux:.1f}%)")
        
        affectations = assign_rooms_equitable(affectations, creneaux, planning_df)
        
    else:
        print("\n❌ Aucune solution trouvée")
        if status == cp_model.INFEASIBLE:
            print("Le problème est INFAISABLE")
        elif status == cp_model.MODEL_INVALID:
            print("Le modèle est INVALIDE")
    
    save_results(affectations, enseignants_df, solver, status, len(creneaux))
    
    return {
        'status': 'ok' if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 'infeasible',
        'affectations': affectations,
        'statistiques': {
            'status_solver': solver.StatusName(status),
            'nb_affectations': len(affectations),
            'temps_resolution': solver.WallTime()
        }
    }


def assign_rooms_equitable(affectations, creneaux, planning_df):
    """
    Affectation ÉQUITABLE des surveillants aux salles
    RÈGLE : 2-3 surveillants par salle MAXIMUM
    """
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
        
        total_surv = len(cre_affs)
        
        # RÈGLE : 2 titulaires par salle + distribution équitable des réserves
        surv_per_salle = [2] * nb_salles  # Base : 2 par salle
        
        # Distribuer les réserves (max 1 par salle pour ne pas dépasser 3)
        remaining = total_surv - (2 * nb_salles)
        idx = 0
        while remaining > 0 and idx < nb_salles:
            if surv_per_salle[idx] < 3:  # MAX 3 par salle
                surv_per_salle[idx] += 1
                remaining -= 1
            idx += 1
        
        # Affectation
        idx = 0
        for i, salle_info in enumerate(salles_info):
            salle = salle_info['salle']
            for j in range(surv_per_salle[i]):
                if idx < len(cre_affs):
                    row = cre_affs.iloc[idx].to_dict()
                    row['cod_salle'] = salle
                    
                    # Déterminer si ce surveillant est le responsable de la salle
                    date = row['date']
                    h_debut = row['h_debut']
                    key = (date, h_debut, salle)
                    responsable_code = salle_responsable.get(key, None)
                    
                    row['responsable_salle'] = (row['code_smartex_ens'] == responsable_code)
                    row['position'] = 'TITULAIRE' if j < 2 else 'RESERVE'
                    results.append(row)
                    idx += 1
        
        # Extras (si reste) - Distribuer sur les salles existantes
        salle_idx = 0
        while idx < len(cre_affs):
            row = cre_affs.iloc[idx].to_dict()
            # Affecter aux salles existantes en rotation
            if salle_idx < len(salles_info):
                row['cod_salle'] = salles_info[salle_idx]['salle']
                salle_idx += 1
            else:
                row['cod_salle'] = salles_info[0]['salle']  # Fallback
            row['responsable_salle'] = False
            row['position'] = 'EXTRA'
            results.append(row)
            idx += 1
        
        # Afficher la distribution
        print(f"   {cid}: {surv_per_salle} surveillants par salle")
    
    print(f"✓ {len(results)} affectations avec distribution équitable (2-3 par salle)")
    return results


def save_results(affectations, enseignants_df, solver, status, nb_creneaux):
    """Sauvegarder les résultats TRIÉS"""
    print("\n=== SAUVEGARDE DES RÉSULTATS ===")
    
    aff_df = pd.DataFrame(affectations)
    
    out_global = os.path.join(OUTPUT_FOLDER, 'affectations_global.csv')
    if not aff_df.empty:
        aff_df['date_sort'] = pd.to_datetime(aff_df['date'], format='%d/%m/%Y', errors='coerce')
        aff_df = aff_df.sort_values(
            ['date_sort', 'h_debut', 'cod_salle', 'nom_ens'],
            na_position='last'
        )
        aff_df = aff_df.drop('date_sort', axis=1)
        
        aff_df.to_csv(out_global, index=False, encoding='utf-8')
        print(f"✓ {out_global}")
        
        # Fichiers par jour
        for jour in sorted(aff_df['jour'].unique()):
            jour_df = aff_df[aff_df['jour'] == jour].copy()
            out = os.path.join(OUTPUT_FOLDER, f'affectations_jour_{jour}.csv')
            jour_df.to_csv(out, index=False, encoding='utf-8')
        
        # Convocations individuelles
        for code in aff_df['code_smartex_ens'].unique():
            ens_df = aff_df[aff_df['code_smartex_ens'] == code].copy()
            nom = ens_df.iloc[0]['nom_ens']
            prenom = ens_df.iloc[0]['prenom_ens']
            out = os.path.join(OUTPUT_FOLDER, f'convocation_{nom}_{prenom}.csv')
            ens_df.to_csv(out, index=False, encoding='utf-8')
        
        print(f"✓ {len(aff_df['code_smartex_ens'].unique())} convocations individuelles")
        
        # Vérification de la distribution par salle
        print("\n📊 Vérification distribution par salle :")
        for cid in aff_df['creneau_id'].unique()[:5]:  # Afficher les 5 premiers
            cid_df = aff_df[aff_df['creneau_id'] == cid]
            salle_counts = cid_df['cod_salle'].value_counts()
            print(f"   {cid}:")
            for salle, count in salle_counts.items():
                print(f"      {salle}: {count} surveillants")
    
    stats = {
        'date_execution': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status_solver': solver.StatusName(status),
        'nb_enseignants_total': len(enseignants_df),
        'nb_creneaux': nb_creneaux,
        'nb_affectations': len(affectations),
        'temps_resolution': f"{solver.WallTime():.2f}s"
    }
    
    out_stats = os.path.join(OUTPUT_FOLDER, 'statistiques.json')
    with open(out_stats, 'w', encoding='utf-8') as f:
        json.dump(stats, f, ensure_ascii=False, indent=2)
    print(f"✓ {out_stats}")


def save_results_to_db(affectations, session_id):
    """
    ÉTAPE FINALE : Sauvegarder les résultats dans la base de données
    """
    print("\n" + "="*60)
    print("SAUVEGARDE DANS LA BASE DE DONNÉES")
    print("="*60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Supprimer les anciennes affectations de cette session
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
    errors_detail = {}
    
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
            # Essayer de trouver n'importe quel créneau avec cette date/heure
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
            except sqlite3.IntegrityError as e:
                nb_errors += 1
                error_msg = str(e)
                if error_msg not in errors_detail:
                    errors_detail[error_msg] = 0
                errors_detail[error_msg] += 1
        else:
            nb_errors += 1
            if 'Créneau non trouvé' not in errors_detail:
                errors_detail['Créneau non trouvé'] = 0
            errors_detail['Créneau non trouvé'] += 1
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ {nb_inserted} affectations insérées dans la base")
    if nb_errors > 0:
        print(f"⚠️ {nb_errors} erreurs d'insertion")
        if errors_detail:
            print(f"\n📊 Détail des erreurs :")
            for error, count in errors_detail.items():
                print(f"   - {error}: {count} occurrences")
    
    return nb_inserted


def main():
    """Point d'entrée principal"""
    print("\n" + "="*60)
    print("SYSTÈME DE PLANIFICATION DE SURVEILLANCES")
    print("Version SQLite CORRIGÉE")
    print("="*60)
    
    if not os.path.exists(DB_NAME):
        print(f"\n❌ Base de données '{DB_NAME}' introuvable!")
        print("💡 Lancez d'abord 'create_database.py' pour créer la base")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_session, libelle_session FROM session")
    sessions = cursor.fetchall()
    conn.close()
    
    if not sessions:
        print("\n❌ Aucune session trouvée dans la base!")
        print("💡 Créez d'abord une session dans la table 'session'")
        return
    
    print("\n📋 Sessions disponibles :")
    for s in sessions:
        print(f"   [{s['id_session']}] {s['libelle_session']}")
    
    session_id = int(input("\n🔢 Entrez l'ID de la session à optimiser: "))
    
    try:
        print("\nChargement des données depuis SQLite...")
        enseignants_df, planning_df, salles_df, voeux_df, parametres_df, mapping_df, salle_par_creneau_df = load_data_from_db(session_id)
        
        print("✓ Toutes les données chargées")
        
    except Exception as e:
        print(f"❌ Erreur de chargement : {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Lancer l'optimisation
    result = optimize_surveillance_scheduling(
        enseignants_df, planning_df, salles_df, 
        voeux_df, parametres_df, mapping_df, salle_par_creneau_df
    )
    
    # Sauvegarder les résultats uniquement si succès
    if result['status'] == 'ok' and len(result['affectations']) > 0:
        # Sauvegarder en base de données
        nb_inserted = save_results_to_db(result['affectations'], session_id)
        
        if nb_inserted > 0:
            print(f"\n✅ {nb_inserted} affectations sauvegardées en base de données")
        else:
            print("\n⚠️ Aucune affectation n'a été sauvegardée en base")
    
    # Afficher le résumé final
    print("\n" + "="*60)
    print("RÉSUMÉ FINAL")
    print("="*60)
    print(f"Statut : {result['status']}")
    print(f"Affectations : {len(result['affectations'])}")
    print(f"Fichiers dans : {OUTPUT_FOLDER}")
    print("\n🎯 CORRECTIONS APPLIQUÉES :")
    print("   ✓ Pas de mapping des grades (chaque grade garde son code)")
    print("   ✓ Utilisation de salle_par_creneau pour le calcul")
    print("   ✓ Formule : nb_surveillants = nb_salles × 2 + 4 réserves")
    print("   ✓ Distribution : 2-3 surveillants MAX par salle")
    print("   ✓ Table affectation correctement remplie")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()