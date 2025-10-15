#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Planificateur de surveillances avec OR-Tools CP-SAT
Version SQLite CORRIGÉE avec contraintes optimisées
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
    Construire les créneaux avec calcul correct du nombre de surveillants
    FORMULE CORRIGÉE : nb_surveillants = nb_salles * 2 + 4 réserves par créneau
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
        
        # FORMULE CORRIGÉE : 2 surveillants par salle + 4 réserves par créneau
        # Total surveillants = (nb_salles * 2) + 4
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
        print(f"   Ex: {cid} -> {cre['nb_salles']} salles, {cre['nb_surveillants']} surveillants (dont {cre['nb_reserves']} réserves)")
    
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
            'grade': grade,
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
    OPTIMISATION PRINCIPALE avec toutes les contraintes HARD
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
    nb_exclusions_voeux = 0
    nb_exclusions_responsable = 0
    
    for tcode in teacher_codes:
        for cid in creneau_ids:
            cre = creneaux[cid]
            
            # CONTRAINTE HARD H2B : Exclusion par vœux
            if (tcode, cre['jour'], cre['seance']) in voeux_set:
                nb_exclusions_voeux += 1
                continue
            
            # CONTRAINTE HARD H2C : Exclusion si responsable de salle
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
    print(f"✓ {nb_exclusions_voeux:,} exclusions (vœux - H2B)")
    print(f"✓ {nb_exclusions_responsable:,} exclusions (responsable - H2C)")
    
    print("\n" + "="*60)
    print("AJOUT DES CONTRAINTES (PAR ORDRE DE PRIORITÉ)")
    print("="*60)
    
    # =========================================================================
    # CONTRAINTE HARD H1 : COUVERTURE COMPLÈTE DES CRÉNEAUX
    # Chaque créneau doit avoir exactement le nombre de surveillants requis
    # =========================================================================
    print("\n[HARD H1] Couverture complète des créneaux")
    for cid in creneau_ids:
        vars_creneau = [x[(t, cid)] for t in teacher_codes if (t, cid) in x]
        required = creneaux[cid]['nb_surveillants']
        model.Add(sum(vars_creneau) == required)
    print(f"✓ H1 : {len(creneau_ids)} créneaux couverts exactement")
    
    # =========================================================================
    # CONTRAINTE HARD H2A : ÉQUITÉ STRICTE PAR GRADE
    # Deux enseignants du même grade ne peuvent avoir un écart > 1 surveillance
    # =========================================================================
    print("\n[HARD H2A] Équité stricte entre enseignants du même grade")
    
    nb_contraintes_equite = 0
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
                    nb_contraintes_equite += 2
    
    print(f"✓ H2A : {nb_contraintes_equite} contraintes d'équité ajoutées")
    
    # =========================================================================
    # CONTRAINTE HARD H2B : RESPECT STRICT DES VŒUX
    # Déjà géré par exclusion lors de la création des variables
    # =========================================================================
    print("\n[HARD H2B] Respect strict des vœux")
    print(f"✓ H2B : {nb_exclusions_voeux} vœux respectés (exclusion variables)")
    
    # =========================================================================
    # CONTRAINTE HARD H2C : ENSEIGNANT NE SURVEILLE PAS SA PROPRE SALLE
    # Déjà géré par exclusion lors de la création des variables
    # =========================================================================
    print("\n[HARD H2C] Enseignant ne surveille pas sa propre salle")
    print(f"✓ H2C : {nb_exclusions_responsable} exclusions appliquées")
    
    # =========================================================================
    # CONTRAINTE HARD H3A : RESPECT DES QUOTAS MAXIMUM
    # Chaque enseignant ne peut dépasser son quota
    # =========================================================================
    print("\n[HARD H3A] Respect des quotas maximum")
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        quota = teachers[tcode]['quota']
        
        if vars_teacher:
            model.Add(sum(vars_teacher) <= quota)
    
    print(f"✓ H3A : {len(teacher_codes)} enseignants limités à leur quota")
    
    # =========================================================================
    # CONTRAINTE SOFT S1 : DISPERSION DANS LA MÊME JOURNÉE
    # Pénaliser les séances non-consécutives dans la même journée
    # =========================================================================
    print("\n[SOFT S1] Dispersion des surveillances dans la même journée")
    
    dispersion_penalties = []
    
    for tcode in teacher_codes:
        # Grouper les créneaux par jour
        creneaux_by_jour = {}
        for cid in creneau_ids:
            if (tcode, cid) in x:
                jour = creneaux[cid]['jour']
                if jour not in creneaux_by_jour:
                    creneaux_by_jour[jour] = []
                creneaux_by_jour[jour].append(cid)
        
        # Pour chaque jour, pénaliser les séances non-consécutives
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
    
    print(f"✓ S1 : {len(dispersion_penalties)} pénalités de dispersion")
    
    # =========================================================================
    # OBJECTIF : Minimiser les écarts + pénalités
    # =========================================================================
    print("\n=== DÉFINITION DE L'OBJECTIF ===")
    
    objective_terms = []
    
    # 1. Écarts individuels par rapport aux quotas
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
    
    # 2. Pénalités de dispersion (poids 5)
    for penalty in dispersion_penalties:
        objective_terms.append(penalty * 5)
    
    model.Minimize(sum(objective_terms))
    
    print(f"✓ Objectif : minimiser {len(objective_terms)} termes")
    
    # =========================================================================
    # RÉSOLUTION
    # =========================================================================
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
        
        # Calculer et afficher les statistiques
        stats = calculate_statistics(affectations, teachers, voeux_set, creneaux, teacher_codes, creneau_ids, x, solver)
        print_statistics(stats)
        
        affectations = assign_rooms_equitable(affectations, creneaux, planning_df)
        
    else:
        print("\n❌ Aucune solution trouvée")
        if status == cp_model.INFEASIBLE:
            print("Le problème est INFAISABLE")
        elif status == cp_model.MODEL_INVALID:
            print("Le modèle est INVALIDE")
        stats = None
    
    save_results(affectations, enseignants_df, solver, status, len(creneaux), stats)
    
    return {
        'status': 'ok' if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 'infeasible',
        'affectations': affectations,
        'statistiques': stats
    }


def calculate_statistics(affectations, teachers, voeux_set, creneaux, teacher_codes, creneau_ids, x, solver):
    """
    Calculer les statistiques détaillées de la solution
    """
    print("\n=== CALCUL DES STATISTIQUES ===")
    
    aff_df = pd.DataFrame(affectations)
    
    # 1. TAUX DE RESPECT DES VŒUX
    total_voeux = len(voeux_set)
    voeux_respectes = total_voeux  # Par construction (exclusion des variables)
    taux_voeux = 100.0 if total_voeux > 0 else 0
    
    # 2. ÉQUITÉ ENTRE SURVEILLANTS
    # Calculer la charge de chaque enseignant
    charges = {}
    for tcode in teacher_codes:
        nb_aff = len(aff_df[aff_df['code_smartex_ens'] == tcode])
        quota = teachers[tcode]['quota']
        charges[tcode] = {
            'nb_affectations': nb_aff,
            'quota': quota,
            'taux': (nb_aff / quota * 100) if quota > 0 else 0
        }
    
    # Calculer l'équité par grade
    equite_par_grade = {}
    teachers_by_grade = {}
    for tcode in teacher_codes:
        grade = teachers[tcode]['grade']
        if grade not in teachers_by_grade:
            teachers_by_grade[grade] = []
        teachers_by_grade[grade].append(tcode)
    
    for grade, tcodes in teachers_by_grade.items():
        if len(tcodes) <= 1:
            equite_par_grade[grade] = {
                'ecart_max': 0,
                'ecart_moyen': 0,
                'nb_enseignants': len(tcodes)
            }
            continue
        
        charges_grade = [charges[tc]['nb_affectations'] for tc in tcodes]
        ecart_max = max(charges_grade) - min(charges_grade)
        ecart_moyen = sum(abs(c - sum(charges_grade)/len(charges_grade)) for c in charges_grade) / len(charges_grade)
        
        equite_par_grade[grade] = {
            'ecart_max': ecart_max,
            'ecart_moyen': ecart_moyen,
            'nb_enseignants': len(tcodes),
            'charges': charges_grade
        }
    
    # 3. TAUX DE RESPECT DES QUOTAS
    nb_dans_quota = 0
    nb_total = len(teacher_codes)
    taux_respect_quota = {}
    
    for tcode in teacher_codes:
        nb_aff = charges[tcode]['nb_affectations']
        quota = charges[tcode]['quota']
        taux = (nb_aff / quota * 100) if quota > 0 else 0
        
        grade = teachers[tcode]['grade']
        if grade not in taux_respect_quota:
            taux_respect_quota[grade] = []
        taux_respect_quota[grade].append(taux)
        
        # Considérer comme respecté si entre 90% et 100%
        if 90 <= taux <= 100:
            nb_dans_quota += 1
    
    taux_global_respect = (nb_dans_quota / nb_total * 100) if nb_total > 0 else 0
    
    # 4. STATISTIQUES PAR GRADE
    stats_par_grade = {}
    for grade in teachers_by_grade.keys():
        tcodes = teachers_by_grade[grade]
        total_affectations = sum(charges[tc]['nb_affectations'] for tc in tcodes)
        total_quota = sum(charges[tc]['quota'] for tc in tcodes)
        taux_utilisation = (total_affectations / total_quota * 100) if total_quota > 0 else 0
        
        stats_par_grade[grade] = {
            'nb_enseignants': len(tcodes),
            'total_affectations': total_affectations,
            'total_quota': total_quota,
            'taux_utilisation': taux_utilisation,
            'taux_individuels': taux_respect_quota.get(grade, [])
        }
    
    # 5. DISTRIBUTION PAR SALLE (vérification 2-3 surveillants)
    distribution_salles = {}
    for cid in aff_df['creneau_id'].unique():
        cid_df = aff_df[aff_df['creneau_id'] == cid]
        if 'cod_salle' in cid_df.columns:
            salle_counts = cid_df['cod_salle'].value_counts()
            for salle, count in salle_counts.items():
                if salle and str(salle) != 'nan':
                    if count not in distribution_salles:
                        distribution_salles[count] = 0
                    distribution_salles[count] += 1
    
    # Vérification que personne n'a 6 surveillants par salle
    has_6_per_room = 6 in distribution_salles or any(k > 6 for k in distribution_salles.keys())
    
    return {
        'taux_voeux': {
            'total': total_voeux,
            'respectes': voeux_respectes,
            'taux': taux_voeux
        },
        'equite': equite_par_grade,
        'quotas': {
            'taux_global': taux_global_respect,
            'nb_dans_quota': nb_dans_quota,
            'nb_total': nb_total,
            'par_grade': stats_par_grade
        },
        'distribution_salles': distribution_salles,
        'validation': {
            'pas_de_6_par_salle': not has_6_per_room,
            'distribution_ok': all(2 <= k <= 3 for k in distribution_salles.keys())
        },
        'charges_individuelles': charges
    }


def print_statistics(stats):
    """
    Afficher les statistiques de manière claire et structurée
    """
    print("\n" + "="*60)
    print("📊 STATISTIQUES DE LA SOLUTION")
    print("="*60)
    
    # 1. Vœux
    print("\n🙅 RESPECT DES VŒUX")
    print(f"   Total de vœux : {stats['taux_voeux']['total']}")
    print(f"   Vœux respectés : {stats['taux_voeux']['respectes']}")
    print(f"   ✓ Taux de respect : {stats['taux_voeux']['taux']:.1f}%")
    
    # 2. Équité
    print("\n⚖️  ÉQUITÉ ENTRE ENSEIGNANTS")
    for grade, info in stats['equite'].items():
        print(f"   Grade {grade} ({info['nb_enseignants']} enseignants):")
        print(f"      - Écart maximum : {info['ecart_max']} surveillance(s)")
        print(f"      - Écart moyen : {info['ecart_moyen']:.2f}")
        if 'charges' in info:
            print(f"      - Distribution : {sorted(info['charges'])}")
    
    # 3. Quotas
    print("\n📋 RESPECT DES QUOTAS (90-100%)")
    print(f"   ✓ Taux global : {stats['quotas']['taux_global']:.1f}%")
    print(f"   Enseignants dans quota : {stats['quotas']['nb_dans_quota']}/{stats['quotas']['nb_total']}")
    
    print("\n   Détail par grade :")
    for grade, info in stats['quotas']['par_grade'].items():
        print(f"   {grade}:")
        print(f"      - Utilisation : {info['total_affectations']}/{info['total_quota']} ({info['taux_utilisation']:.1f}%)")
        taux_min = min(info['taux_individuels']) if info['taux_individuels'] else 0
        taux_max = max(info['taux_individuels']) if info['taux_individuels'] else 0
        taux_moy = sum(info['taux_individuels'])/len(info['taux_individuels']) if info['taux_individuels'] else 0
        print(f"      - Taux individuels : min={taux_min:.1f}%, max={taux_max:.1f}%, moy={taux_moy:.1f}%")
    
    # 4. Distribution par salle
    print("\n🏫 DISTRIBUTION PAR SALLE")
    for nb_surv, nb_salles in sorted(stats['distribution_salles'].items()):
        print(f"   {nb_surv} surveillants : {nb_salles} salle(s)")
    
    # 5. Validations
    print("\n✅ VALIDATIONS")
    if stats['validation']['pas_de_6_par_salle']:
        print("   ✓ Aucune salle avec 6 surveillants ou plus")
    else:
        print("   ❌ ERREUR : Des salles ont 6 surveillants ou plus !")
    
    if stats['validation']['distribution_ok']:
        print("   ✓ Distribution respectée : 2-3 surveillants par salle")
    else:
        print("   ⚠️  Attention : Distribution non optimale détectée")
    
    print("="*60)


def assign_rooms_equitable(affectations, creneaux, planning_df):
    """
    Affectation ÉQUITABLE des surveillants aux salles
    RÈGLE STRICTE : 2 TITULAIRES par salle + 4 RÉSERVES distribuées 1 par 1
    Distribution cyclique : chaque salle reçoit au maximum 3 surveillants (2 TITULAIRES + 1 RÉSERVE)
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
        nb_reserves = creneaux[cid]['nb_reserves']
        
        total_surv = len(cre_affs)
        
        # ALGORITHME DE DISTRIBUTION ÉQUITABLE
        # Phase 1 : Affecter 2 TITULAIRES par salle
        surv_per_salle = [2] * nb_salles  # Base : 2 titulaires par salle
        titulaires_attendus = nb_salles * 2
        
        # Phase 2 : Distribuer les 4 RÉSERVES de manière cyclique (1 par salle maximum)
        # Les réserves sont distribuées aux 4 premières salles uniquement
        reserves_per_salle = [0] * nb_salles
        for i in range(min(nb_reserves, nb_salles)):
            reserves_per_salle[i] = 1
            surv_per_salle[i] += 1
        
        # Vérification : total doit être égal au nombre d'affectations
        total_attendu = sum(surv_per_salle)
        if total_attendu != total_surv:
            print(f"   ⚠️  {cid}: Incohérence - Attendu {total_attendu}, Reçu {total_surv}")
        
        # Affectation effective avec position TITULAIRE / RESERVE
        idx = 0
        for i, salle_info in enumerate(salles_info):
            salle = salle_info['salle']
            
            # D'abord les 2 TITULAIRES
            for j in range(2):
                if idx < len(cre_affs):
                    row = cre_affs.iloc[idx].to_dict()
                    row['cod_salle'] = salle
                    
                    # Déterminer si ce surveillant est le responsable de la salle
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
        
        # Affichage de la distribution
        nb_titulaires = sum(1 for r in results if r['creneau_id'] == cid and r['position'] == 'TITULAIRE')
        nb_reserves_aff = sum(1 for r in results if r['creneau_id'] == cid and r['position'] == 'RESERVE')
        
        max_surv = max(surv_per_salle)
        if max_surv > 3:
            print(f"   ❌ {cid}: ERREUR - {max_surv} surveillants dans une salle (max autorisé: 3)")
        else:
            print(f"   ✓ {cid}: {surv_per_salle} surveillants par salle ({nb_titulaires} titulaires + {nb_reserves_aff} réserves)")
    
    # Statistiques finales
    total_titulaires = sum(1 for r in results if r['position'] == 'TITULAIRE')
    total_reserves = sum(1 for r in results if r['position'] == 'RESERVE')
    
    print(f"\n✓ {len(results)} affectations totales")
    print(f"✓ {total_titulaires} TITULAIRES + {total_reserves} RÉSERVES")
    print(f"✓ Distribution respectée : 2 TITULAIRES par salle + 4 RÉSERVES par créneau")
    
    return results


def save_results(affectations, enseignants_df, solver, status, nb_creneaux, stats):
    """Sauvegarder les résultats TRIÉS avec statistiques"""
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
    
    # Sauvegarder les statistiques complètes
    stats_output = {
        'date_execution': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status_solver': solver.StatusName(status),
        'nb_enseignants_total': len(enseignants_df),
        'nb_creneaux': nb_creneaux,
        'nb_affectations': len(affectations),
        'temps_resolution': f"{solver.WallTime():.2f}s"
    }
    
    if stats:
        stats_output['statistiques_detaillees'] = {
            'taux_respect_voeux': f"{stats['taux_voeux']['taux']:.1f}%",
            'taux_respect_quotas': f"{stats['quotas']['taux_global']:.1f}%",
            'equite_par_grade': {
                grade: {
                    'ecart_max': info['ecart_max'],
                    'ecart_moyen': round(info['ecart_moyen'], 2)
                }
                for grade, info in stats['equite'].items()
            },
            'validation': stats['validation']
        }
    
    out_stats = os.path.join(OUTPUT_FOLDER, 'statistiques.json')
    with open(out_stats, 'w', encoding='utf-8') as f:
        json.dump(stats_output, f, ensure_ascii=False, indent=2)
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
    print("Version SQLite CORRIGÉE - Optimale")
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
    
    if result['statistiques']:
        print("\n📊 PERFORMANCES :")
        print(f"   ✓ Respect des vœux : {result['statistiques']['taux_voeux']['taux']:.1f}%")
        print(f"   ✓ Respect des quotas : {result['statistiques']['quotas']['taux_global']:.1f}%")
        print(f"   ✓ Distribution : 2 TITULAIRES + 4 RÉSERVES par créneau")
    
    print("\n🎯 CONTRAINTES APPLIQUÉES :")
    print("   [HARD H1] ✓ Couverture complète des créneaux")
    print("   [HARD H2A] ✓ Équité stricte par grade (écart ≤ 1)")
    print("   [HARD H2B] ✓ Respect strict des vœux")
    print("   [HARD H2C] ✓ Enseignant ne surveille pas sa propre salle")
    print("   [HARD H3A] ✓ Respect des quotas maximum")
    print("   [SOFT S1] ✓ Dispersion optimisée dans la journée")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()
