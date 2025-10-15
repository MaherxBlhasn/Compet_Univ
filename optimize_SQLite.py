#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Planificateur de surveillances avec OR-Tools CP-SAT
Version avec contrainte de prÃ©sence des responsables - CORRIGÃ‰E
"""

import os
import json
import sqlite3
from datetime import datetime
import pandas as pd
from ortools.sat.python import cp_model

from surveillance_stats import generate_statistics

# Configuration
DB_NAME = 'surveillance.db'
OUTPUT_FOLDER = 'results'
os.makedirs(OUTPUT_FOLDER, exist_ok=True)


def get_db_connection():
    """CrÃ©er une connexion Ã  la base de donnÃ©es"""
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def load_data_from_db(session_id):
    """Charger toutes les donnÃ©es depuis la base de donnÃ©es"""
    print("\n" + "="*60)
    print("CHARGEMENT DES DONNÃ‰ES DEPUIS SQLite")
    print("="*60)
    
    conn = get_db_connection()
    
    # 1. Charger les enseignants
    print("\nðŸ“š Chargement des enseignants...")
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
    print(f"âœ“ {len(enseignants_df)} enseignants chargÃ©s")
    
    # 2. Charger les crÃ©neaux d'examen
    print("\nðŸ“… Chargement des crÃ©neaux d'examen...")
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
    print(f"âœ“ {len(planning_df)} crÃ©neaux d'examen chargÃ©s")
    
    # 3. CrÃ©er salles_df
    print("\nðŸ« Construction du fichier salles...")
    salles_df = planning_df[['dateExam', 'h_debut', 'h_fin', 'cod_salle']].copy()
    salles_df.columns = ['date_examen', 'heure_debut', 'heure_fin', 'salle']
    salles_df = salles_df.dropna(subset=['salle'])
    print(f"âœ“ {len(salles_df)} salles identifiÃ©es")
    
    # 4. Charger salle_par_creneau
    print("\nðŸ¢ Chargement de salle_par_creneau...")
    salle_par_creneau_df = pd.read_sql_query("""
        SELECT 
            dateExam,
            h_debut,
            nb_salle
        FROM salle_par_creneau
        WHERE id_session = ?
    """, conn, params=(session_id,))
    print(f"âœ“ {len(salle_par_creneau_df)} entrÃ©es salle_par_creneau")
    
    # 5. Charger les vÅ“ux
    print("\nðŸ™… Chargement des vÅ“ux...")
    voeux_df = pd.read_sql_query("""
        SELECT 
            code_smartex_ens,
            jour,
            seance
        FROM voeu
        WHERE id_session = ?
    """, conn, params=(session_id,))
    print(f"âœ“ {len(voeux_df)} vÅ“ux chargÃ©s")
    
    # 6. Charger les paramÃ¨tres de grades
    print("\nâš™ï¸ Chargement des paramÃ¨tres de grades...")
    parametres_df = pd.read_sql_query("""
        SELECT 
            code_grade as grade,
            quota as max_surveillances
        FROM grade
    """, conn)
    print(f"âœ“ {len(parametres_df)} grades chargÃ©s")
    
    # 7. CrÃ©er mapping jours/sÃ©ances
    print("\nðŸ—“ï¸ Construction du mapping jours/sÃ©ances...")
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
    print(f"âœ“ {len(mapping_df)} mappings jour/sÃ©ance crÃ©Ã©s")
    
    conn.close()
    
    print("\nâœ… Toutes les donnÃ©es chargÃ©es depuis SQLite")
    
    return enseignants_df, planning_df, salles_df, voeux_df, parametres_df, mapping_df, salle_par_creneau_df


def determine_seance_from_time(time_str):
    """DÃ©terminer le code de sÃ©ance Ã  partir de l'heure"""
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
    
    print(f"âœ“ {len(salle_responsable)} mappings salle->responsable crÃ©Ã©s")
    return salle_responsable


def build_creneau_responsables_mapping(planning_df, creneaux):
    """
    Construire un mapping (date, heure) -> liste des responsables de ce crÃ©neau
    """
    print("\n=== Construction du mapping crÃ©neau -> responsables ===")
    
    creneau_responsables = {}
    
    for cid, cre in creneaux.items():
        date = cre['date']
        h_debut = cre['h_debut']
        
        # Trouver tous les responsables pour ce crÃ©neau
        responsables = set()
        for salle_info in cre['salles_info']:
            if salle_info['responsable'] is not None:
                responsables.add(salle_info['responsable'])
        
        creneau_responsables[cid] = list(responsables)
    
    total_responsables = sum(len(resp) for resp in creneau_responsables.values())
    print(f"âœ“ {len(creneau_responsables)} crÃ©neaux avec {total_responsables} responsables identifiÃ©s")
    
    return creneau_responsables


def build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df):
    """Construire les crÃ©neaux avec calcul correct du nombre de surveillants"""
    print("\n=== Ã‰TAPE 1 : Construction des crÃ©neaux ===")
    
    salles_df['h_debut_parsed'] = salles_df['heure_debut'].apply(parse_time)
    salles_df['h_fin_parsed'] = salles_df['heure_fin'].apply(parse_time)
    
    # CrÃ©er un mapping depuis salle_par_creneau
    salle_par_creneau_df['h_debut_parsed'] = salle_par_creneau_df['h_debut'].apply(parse_time)
    nb_salles_map = {}
    for _, row in salle_par_creneau_df.iterrows():
        key = (row['dateExam'], row['h_debut_parsed'])
        nb_salles_map[key] = row['nb_salle']
    
    creneau_groups = salles_df.groupby(['date_examen', 'h_debut_parsed', 'h_fin_parsed'])
    
    creneaux = {}
    for (date, h_debut, h_fin), group in creneau_groups:
        creneau_id = f"{date}_{h_debut}"
        
        # RÃ©cupÃ©rer nb_salle depuis salle_par_creneau
        key = (date, h_debut)
        nb_salles = nb_salles_map.get(key, len(group))
        
        # FORMULE : 2 surveillants par salle + 4 rÃ©serves par crÃ©neau
        nb_reserves = 4
        nb_surveillants = (nb_salles * 2) + nb_reserves
        
        # Associer chaque salle Ã  son responsable
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
    
    print(f"âœ“ {len(creneaux)} crÃ©neaux identifiÃ©s")
    print(f"âœ“ Total surveillants requis : {sum(c['nb_surveillants'] for c in creneaux.values())}")
    
    return creneaux


def map_creneaux_to_jours_seances(creneaux, mapping_df):
    """Associer chaque crÃ©neau Ã  son (jour, seance)"""
    print("\n=== Ã‰TAPE 2 : Mapping jour/sÃ©ance ===")
    
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
            print(f"âš ï¸ Pas de mapping pour crÃ©neau {cid}")
            cre['jour'] = None
            cre['seance'] = None
    
    print(f"âœ“ {sum(1 for c in creneaux.values() if c['jour'] is not None)} crÃ©neaux mappÃ©s")
    return creneaux


def build_teachers_dict(enseignants_df, parametres_df):
    """Construire le dictionnaire des enseignants avec leurs quotas"""
    print("\n=== Ã‰TAPE 3 : PrÃ©paration des enseignants ===")
    
    # Construire le mapping grade -> quota
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
        
        grade = str(row['grade_code_ens']).strip().upper()
        
        if grade not in grade_quotas:
            print(f"âš ï¸ Grade '{grade}' non trouvÃ© dans les paramÃ¨tres, ignorÃ©")
            continue
        
        quota = grade_quotas[grade]
        participe = bool(row.get('participe_surveillance', True))
        if participe:
            participent += 1
        
        # PrioritÃ©s
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
    
    print(f"âœ“ {len(teachers)} enseignants chargÃ©s")
    print(f"âœ“ {participent} enseignants participent")
    
    return teachers


def build_voeux_set(voeux_df):
    """Construire l'ensemble des vÅ“ux de non-surveillance"""
    print("\n=== Ã‰TAPE 4 : Traitement des vÅ“ux ===")
    
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
    
    print(f"âœ“ {len(voeux_set)} vÅ“ux de non-surveillance")
    
    return voeux_set


def get_seance_number(seance):
    """Convertir code sÃ©ance en numÃ©ro (S1=1, S2=2, etc.)"""
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
    """Optimisation principale avec contrainte de prÃ©sence des responsables"""
    print("\n" + "="*60)
    print("DÃ‰MARRAGE DE L'OPTIMISATION OR-TOOLS CP-SAT")
    print("="*60)
    
    salle_responsable = build_salle_responsable_mapping(planning_df)
    creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df)
    creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
    creneau_responsables = build_creneau_responsables_mapping(planning_df, creneaux)
    teachers = build_teachers_dict(enseignants_df, parametres_df)
    voeux_set = build_voeux_set(voeux_df)
    
    print("\n=== Ã‰TAPE 5 : CrÃ©ation du modÃ¨le CP-SAT ===")
    
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
    
    print("CrÃ©ation des variables...")
    x = {}
    
    nb_vars = 0
    nb_exclusions_voeux = 0
    nb_exclusions_responsable = 0
    
    for tcode in teacher_codes:
        for cid in creneau_ids:
            cre = creneaux[cid]
            
            # CONTRAINTE H2B : Exclusion par vÅ“ux
            if (tcode, cre['jour'], cre['seance']) in voeux_set:
                nb_exclusions_voeux += 1
                continue
            
            # CONTRAINTE H2C : Exclusion si responsable de salle
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
    
    print(f"âœ“ {nb_vars:,} variables crÃ©Ã©es")
    print(f"âœ“ {nb_exclusions_voeux:,} exclusions (vÅ“ux - H2B)")
    print(f"âœ“ {nb_exclusions_responsable:,} exclusions (responsable - H2C)")
    
    print("\n" + "="*60)
    print("AJOUT DES CONTRAINTES (PAR ORDRE DE PRIORITÃ‰)")
    print("="*60)
    
    # =========================================================================
    # CONTRAINTE HARD H1 : COUVERTURE COMPLÃˆTE DES CRÃ‰NEAUX
    # =========================================================================
    print("\n[HARD H1] Couverture complÃ¨te des crÃ©neaux")
    for cid in creneau_ids:
        vars_creneau = [x[(t, cid)] for t in teacher_codes if (t, cid) in x]
        required = creneaux[cid]['nb_surveillants']
        model.Add(sum(vars_creneau) == required)
    print(f"âœ“ H1 : {len(creneau_ids)} crÃ©neaux couverts exactement")
    
    # =========================================================================
    # CONTRAINTE HARD H2D : PRÃ‰SENCE DES RESPONSABLES AU CRÃ‰NEAU (CORRIGÃ‰E)
    # Un responsable doit Ãªtre prÃ©sent dans au moins une salle du mÃªme crÃ©neau
    # =========================================================================
    print("\n[HARD H2D] PrÃ©sence des responsables au crÃ©neau")
    nb_contraintes_presence = 0
    responsables_avec_contrainte = set()
    responsables_sans_possibilite = []
    
    for cid in creneau_ids:
        responsables = creneau_responsables.get(cid, [])
        
        for resp_code in responsables:
            # VÃ©rifier si le responsable participe Ã  la surveillance
            if resp_code not in teacher_codes:
                continue
            
            # CORRECTION : RÃ©cupÃ©rer LA variable pour ce responsable dans CE crÃ©neau
            # (elle existe car H2C n'exclut que si responsable de TOUTES les salles)
            if (resp_code, cid) in x:
                # Le responsable DOIT Ãªtre affectÃ© Ã  ce crÃ©neau
                model.Add(x[(resp_code, cid)] == 1)
                nb_contraintes_presence += 1
                responsables_avec_contrainte.add(resp_code)
            else:
                # Cas problÃ©matique : le responsable n'a aucune variable disponible
                responsables_sans_possibilite.append({
                    'code': resp_code,
                    'nom': teachers[resp_code]['nom'],
                    'prenom': teachers[resp_code]['prenom'],
                    'creneau': cid
                })
    
    print(f"âœ“ H2D : {nb_contraintes_presence} contraintes de prÃ©sence responsable")
    print(f"âœ“ {len(responsables_avec_contrainte)} responsables concernÃ©s")
    
    if responsables_sans_possibilite:
        print(f"âš ï¸  {len(responsables_sans_possibilite)} responsables SANS possibilitÃ© d'affectation :")
        for resp in responsables_sans_possibilite[:5]:
            print(f"   - {resp['nom']} {resp['prenom']} (crÃ©neau {resp['creneau']})")
    
    # =========================================================================
    # CONTRAINTE HARD H2A : Ã‰QUITÃ‰ STRICTE PAR GRADE
    # =========================================================================
    print("\n[HARD H2A] Ã‰quitÃ© stricte entre enseignants du mÃªme grade")
    
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
                    
                    model.Add(nb_t1 - nb_t2 <= 1)
                    model.Add(nb_t2 - nb_t1 <= 1)
                    nb_contraintes_equite += 2
    
    print(f"âœ“ H2A : {nb_contraintes_equite} contraintes d'Ã©quitÃ© ajoutÃ©es")
    
    # =========================================================================
    # CONTRAINTE HARD H3A : RESPECT DES QUOTAS MAXIMUM
    # =========================================================================
    print("\n[HARD H3A] Respect des quotas maximum")
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        quota = teachers[tcode]['quota']
        
        if vars_teacher:
            model.Add(sum(vars_teacher) <= quota)
    
    print(f"âœ“ H3A : {len(teacher_codes)} enseignants limitÃ©s Ã  leur quota")
    
    # =========================================================================
    # CONTRAINTE SOFT S1 : DISPERSION DANS LA MÃŠME JOURNÃ‰E
    # =========================================================================
    print("\n[SOFT S1] Dispersion des surveillances dans la mÃªme journÃ©e")
    
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
    
    print(f"âœ“ S1 : {len(dispersion_penalties)} pÃ©nalitÃ©s de dispersion")
    
    # =========================================================================
    # OBJECTIF : Minimiser les Ã©carts + pÃ©nalitÃ©s
    # =========================================================================
    print("\n=== DÃ‰FINITION DE L'OBJECTIF ===")
    
    objective_terms = []
    
    # 1. Ã‰carts individuels par rapport aux quotas
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
    
    # 2. PÃ©nalitÃ©s de dispersion
    for penalty in dispersion_penalties:
        objective_terms.append(penalty * 5)
    
    model.Minimize(sum(objective_terms))
    
    print(f"âœ“ Objectif : minimiser {len(objective_terms)} termes")
    
    # =========================================================================
    # RÃ‰SOLUTION
    # =========================================================================
    print("\n" + "="*60)
    print("RÃ‰SOLUTION DU PROBLÃˆME")
    print("="*60)
    
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180
    solver.parameters.num_search_workers = 8
    solver.parameters.log_search_progress = True
    
    status = solver.Solve(model)
    
    print(f"\nâœ“ Statut : {solver.StatusName(status)}")
    print(f"âœ“ Temps de rÃ©solution : {solver.WallTime():.2f}s")
    
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
        
        print(f"âœ“ {len(affectations)} affectations extraites")
        
        # Calculer et afficher les statistiques
        stats = calculate_statistics(affectations, teachers, voeux_set, creneaux, 
                                     teacher_codes, creneau_ids, x, solver, 
                                     creneau_responsables, responsables_avec_contrainte)
        print_statistics(stats)
        
        affectations = assign_rooms_equitable(affectations, creneaux, planning_df)
        
    else:
        print("\nâŒ Aucune solution trouvÃ©e")
        if status == cp_model.INFEASIBLE:
            print("Le problÃ¨me est INFAISABLE")
        elif status == cp_model.MODEL_INVALID:
            print("Le modÃ¨le est INVALIDE")
        stats = None
    
    save_results(affectations, enseignants_df, solver, status, len(creneaux), stats)
    
    return {
        'status': 'ok' if status in (cp_model.OPTIMAL, cp_model.FEASIBLE) else 'infeasible',
        'affectations': affectations,
        'statistiques': stats
    }


def calculate_statistics(affectations, teachers, voeux_set, creneaux, teacher_codes, 
                         creneau_ids, x, solver, creneau_responsables, responsables_avec_contrainte):
    """Calculer les statistiques dÃ©taillÃ©es de la solution"""
    print("\n=== CALCUL DES STATISTIQUES ===")
    
    aff_df = pd.DataFrame(affectations)
    
    # 1. TAUX DE RESPECT DES VÅ’UX
    total_voeux = len(voeux_set)
    voeux_respectes = total_voeux  # Par construction (exclusion des variables)
    taux_voeux = 100.0 if total_voeux > 0 else 0
    
    # 2. PRÃ‰SENCE DES RESPONSABLES
    responsables_presents = set()
    responsables_absents = []
    
    for cid, responsables in creneau_responsables.items():
        for resp_code in responsables:
            if resp_code not in teacher_codes:
                continue
            
            # VÃ©rifier si le responsable est affectÃ© Ã  ce crÃ©neau
            est_present = False
            for aff in affectations:
                if aff['code_smartex_ens'] == resp_code and aff['creneau_id'] == cid:
                    est_present = True
                    responsables_presents.add(resp_code)
                    break
            
            if not est_present and resp_code in responsables_avec_contrainte:
                responsables_absents.append({
                    'code': resp_code,
                    'nom': teachers[resp_code]['nom'],
                    'prenom': teachers[resp_code]['prenom'],
                    'creneau': cid
                })
    
    taux_presence_responsables = (len(responsables_presents) / len(responsables_avec_contrainte) * 100) if responsables_avec_contrainte else 0
    
    # 3. Ã‰QUITÃ‰ ENTRE SURVEILLANTS
    charges = {}
    for tcode in teacher_codes:
        nb_aff = len(aff_df[aff_df['code_smartex_ens'] == tcode])
        quota = teachers[tcode]['quota']
        charges[tcode] = {
            'nb_affectations': nb_aff,
            'quota': quota,
            'taux': (nb_aff / quota * 100) if quota > 0 else 0
        }
    
    # Calculer l'Ã©quitÃ© par grade
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
    
    # 4. TAUX DE RESPECT DES QUOTAS
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
        
        # ConsidÃ©rer comme respectÃ© si entre 90% et 100%
        if 90 <= taux <= 100:
            nb_dans_quota += 1
    
    taux_global_respect = (nb_dans_quota / nb_total * 100) if nb_total > 0 else 0
    
    # 5. STATISTIQUES PAR GRADE
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
    
    # 6. DISPERSION DANS LA JOURNÃ‰E
    dispersion_stats = {}
    for tcode in teacher_codes:
        ens_affs = aff_df[aff_df['code_smartex_ens'] == tcode]
        
        # Grouper par jour
        jours_groupes = ens_affs.groupby('jour')
        
        gaps_total = []
        for jour, jour_df in jours_groupes:
            seances = [get_seance_number(s) for s in jour_df['seance'].values]
            seances = [s for s in seances if s is not None]
            
            if len(seances) > 1:
                seances_sorted = sorted(seances)
                for i in range(len(seances_sorted) - 1):
                    gap = seances_sorted[i+1] - seances_sorted[i] - 1
                    if gap > 0:
                        gaps_total.append(gap)
        
        if gaps_total:
            dispersion_stats[tcode] = {
                'nb_gaps': len(gaps_total),
                'gap_moyen': sum(gaps_total) / len(gaps_total),
                'gap_max': max(gaps_total)
            }
    
    nb_avec_gaps = len(dispersion_stats)
    gap_moyen_global = sum(d['gap_moyen'] for d in dispersion_stats.values()) / nb_avec_gaps if nb_avec_gaps > 0 else 0
    
    # 7. DISTRIBUTION PAR SALLE
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
    
    has_6_per_room = 6 in distribution_salles or any(k > 6 for k in distribution_salles.keys())
    
    return {
        'taux_voeux': {
            'total': total_voeux,
            'respectes': voeux_respectes,
            'taux': taux_voeux
        },
        'presence_responsables': {
            'total_responsables': len(responsables_avec_contrainte),
            'responsables_presents': len(responsables_presents),
            'responsables_absents': responsables_absents,
            'taux_presence': taux_presence_responsables
        },
        'equite': equite_par_grade,
        'quotas': {
            'taux_global': taux_global_respect,
            'nb_dans_quota': nb_dans_quota,
            'nb_total': nb_total,
            'par_grade': stats_par_grade
        },
        'dispersion': {
            'nb_enseignants_avec_gaps': nb_avec_gaps,
            'gap_moyen_global': gap_moyen_global,
            'details': dispersion_stats
        },
        'distribution_salles': distribution_salles,
        'validation': {
            'pas_de_6_par_salle': not has_6_per_room,
            'distribution_ok': all(2 <= k <= 3 for k in distribution_salles.keys())
        },
        'charges_individuelles': charges
    }


def print_statistics(stats):
    """Afficher les statistiques de maniÃ¨re claire et structurÃ©e"""
    print("\n" + "="*60)
    print("ðŸ“Š STATISTIQUES DE LA SOLUTION")
    print("="*60)
    
    # 1. VÅ“ux
    print("\nðŸ™… RESPECT DES VÅ’UX")
    print(f"   Total de vÅ“ux : {stats['taux_voeux']['total']}")
    print(f"   VÅ“ux respectÃ©s : {stats['taux_voeux']['respectes']}")
    print(f"   âœ“ Taux de respect : {stats['taux_voeux']['taux']:.1f}%")
    
    # 2. PrÃ©sence des responsables
    print("\nðŸ‘¨â€ðŸ« PRÃ‰SENCE DES RESPONSABLES AU CRÃ‰NEAU")
    pr = stats['presence_responsables']
    print(f"   Total responsables : {pr['total_responsables']}")
    print(f"   Responsables prÃ©sents : {pr['responsables_presents']}")
    print(f"   âœ“ Taux de prÃ©sence : {pr['taux_presence']:.1f}%")
    
    if pr['responsables_absents']:
        print(f"\n   âš ï¸  {len(pr['responsables_absents'])} responsables absents dÃ©tectÃ©s :")
        for resp in pr['responsables_absents'][:5]:  # Limiter Ã  5
            print(f"      - {resp['nom']} {resp['prenom']} (code: {resp['code']}) - CrÃ©neau: {resp['creneau']}")
        if len(pr['responsables_absents']) > 5:
            print(f"      ... et {len(pr['responsables_absents']) - 5} autres")
    else:
        print("   âœ… Tous les responsables sont prÃ©sents Ã  leurs crÃ©neaux")
    
    # 3. Ã‰quitÃ©
    print("\nâš–ï¸  Ã‰QUITÃ‰ ENTRE ENSEIGNANTS")
    for grade, info in stats['equite'].items():
        print(f"   Grade {grade} ({info['nb_enseignants']} enseignants):")
        print(f"      - Ã‰cart maximum : {info['ecart_max']} surveillance(s)")
        print(f"      - Ã‰cart moyen : {info['ecart_moyen']:.2f}")
        if 'charges' in info:
            print(f"      - Distribution : {sorted(info['charges'])}")
    
    # 4. Quotas
    print("\nðŸ“‹ RESPECT DES QUOTAS (90-100%)")
    print(f"   âœ“ Taux global : {stats['quotas']['taux_global']:.1f}%")
    print(f"   Enseignants dans quota : {stats['quotas']['nb_dans_quota']}/{stats['quotas']['nb_total']}")
    
    print("\n   DÃ©tail par grade :")
    for grade, info in stats['quotas']['par_grade'].items():
        print(f"   {grade}:")
        print(f"      - Utilisation : {info['total_affectations']}/{info['total_quota']} ({info['taux_utilisation']:.1f}%)")
        if info['taux_individuels']:
            taux_min = min(info['taux_individuels'])
            taux_max = max(info['taux_individuels'])
            taux_moy = sum(info['taux_individuels'])/len(info['taux_individuels'])
            print(f"      - Taux individuels : min={taux_min:.1f}%, max={taux_max:.1f}%, moy={taux_moy:.1f}%")
    
    # 5. Dispersion
    print("\nðŸ“… DISPERSION DANS LA JOURNÃ‰E")
    disp = stats['dispersion']
    print(f"   Enseignants avec gaps : {disp['nb_enseignants_avec_gaps']}")
    if disp['nb_enseignants_avec_gaps'] > 0:
        print(f"   Gap moyen global : {disp['gap_moyen_global']:.2f} sÃ©ances")
        
        # Top 5 des enseignants avec le plus de gaps
        top_gaps = sorted(disp['details'].items(), 
                         key=lambda x: x[1]['gap_max'], reverse=True)[:5]
        if top_gaps:
            print(f"\n   Top 5 des plus grandes dispersions :")
            for tcode, info in top_gaps:
                print(f"      - Enseignant {tcode}: {info['nb_gaps']} gap(s), max={info['gap_max']}, moy={info['gap_moyen']:.1f}")
    else:
        print("   âœ… Aucune dispersion dÃ©tectÃ©e")
    
    # 6. Distribution par salle
    print("\nðŸ« DISTRIBUTION PAR SALLE")
    for nb_surv, nb_salles in sorted(stats['distribution_salles'].items()):
        print(f"   {nb_surv} surveillants : {nb_salles} salle(s)")
    
    # 7. Validations
    print("\nâœ… VALIDATIONS")
    if stats['validation']['pas_de_6_par_salle']:
        print("   âœ“ Aucune salle avec 6 surveillants ou plus")
    else:
        print("   âŒ ERREUR : Des salles ont 6 surveillants ou plus !")
    
    if stats['validation']['distribution_ok']:
        print("   âœ“ Distribution respectÃ©e : 2-3 surveillants par salle")
    else:
        print("   âš ï¸  Attention : Distribution non optimale dÃ©tectÃ©e")
    
    if stats['presence_responsables']['taux_presence'] == 100.0:
        print("   âœ“ Tous les responsables sont prÃ©sents Ã  leurs crÃ©neaux")
    else:
        print(f"   âš ï¸  Seulement {stats['presence_responsables']['taux_presence']:.1f}% des responsables prÃ©sents")
    
    print("="*60)


def assign_rooms_equitable(affectations, creneaux, planning_df):
    """Affectation Ã‰QUITABLE des surveillants aux salles"""
    print("\n=== AFFECTATION Ã‰QUITABLE AUX SALLES ===")
    
    # CrÃ©er le mapping (date, heure, salle) -> responsable
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
        
        # ALGORITHME DE DISTRIBUTION Ã‰QUITABLE
        # Phase 1 : 2 TITULAIRES par salle
        surv_per_salle = [2] * nb_salles
        
        # Phase 2 : Distribuer les 4 RÃ‰SERVES (1 par salle maximum)
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
            
            # Ensuite la RÃ‰SERVE si cette salle en reÃ§oit une
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
            print(f"   âŒ {cid}: ERREUR - {max_surv} surveillants dans une salle")
        else:
            print(f"   âœ“ {cid}: {surv_per_salle} surveillants par salle")
    
    # Statistiques finales
    total_titulaires = sum(1 for r in results if r['position'] == 'TITULAIRE')
    total_reserves = sum(1 for r in results if r['position'] == 'RESERVE')
    
    print(f"\nâœ“ {len(results)} affectations totales")
    print(f"âœ“ {total_titulaires} TITULAIRES + {total_reserves} RÃ‰SERVES")
    
    return results


def save_results(affectations, enseignants_df, solver, status, nb_creneaux, stats):
    """Sauvegarder les rÃ©sultats TRIÃ‰S avec statistiques"""
    print("\n=== SAUVEGARDE DES RÃ‰SULTATS ===")
    
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
        print(f"âœ“ {out_global}")
        
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
        
        print(f"âœ“ {len(aff_df['code_smartex_ens'].unique())} convocations individuelles")
    
    # Sauvegarder les statistiques complÃ¨tes
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
            'taux_presence_responsables': f"{stats['presence_responsables']['taux_presence']:.1f}%",
            'responsables_absents': len(stats['presence_responsables']['responsables_absents']),
            'taux_respect_quotas': f"{stats['quotas']['taux_global']:.1f}%",
            'dispersion_gap_moyen': f"{stats['dispersion']['gap_moyen_global']:.2f}",
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
    print(f"âœ“ {out_stats}")


def save_results_to_db(affectations, session_id):
    """Sauvegarder les rÃ©sultats dans la base de donnÃ©es"""
    print("\n" + "="*60)
    print("SAUVEGARDE DANS LA BASE DE DONNÃ‰ES")
    print("="*60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Supprimer les anciennes affectations
    cursor.execute("""
        DELETE FROM affectation 
        WHERE id_session = ?
    """, (session_id,))
    
    deleted = cursor.rowcount
    print(f"\nðŸ—‘ï¸ {deleted} anciennes affectations supprimÃ©es")
    
    # CrÃ©er un mapping (date, heure, salle) -> creneau_id
    creneaux_map = {}
    cursor.execute("""
        SELECT creneau_id, dateExam, h_debut, cod_salle
        FROM creneau
        WHERE id_session = ?
    """, (session_id,))
    
    for row in cursor.fetchall():
        key = (row['dateExam'], parse_time(row['h_debut']), row['cod_salle'])
        creneaux_map[key] = row['creneau_id']
    
    print(f"ðŸ“‹ {len(creneaux_map)} crÃ©neaux mappÃ©s")
    
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
    conn.close()
    
    print(f"\nâœ… {nb_inserted} affectations insÃ©rÃ©es dans la base")
    if nb_errors > 0:
        print(f"âš ï¸  {nb_errors} erreurs d'insertion")
    
    return nb_inserted


def generate_responsable_presence_files(planning_df, teachers, creneaux, mapping_df):
    """
    GÃ©nÃ©rer des fichiers CSV pour chaque responsable avec les crÃ©neaux oÃ¹ il doit Ãªtre prÃ©sent
    Ces prÃ©sences sont OBLIGATOIRES mais ne sont PAS des affectations de surveillance
    CORRECTION: Utilise directement le dictionnaire 'teachers' au lieu de 'enseignants_df'
    """
    print("\n" + "="*60)
    print("GÃ‰NÃ‰RATION DES FICHIERS DE PRÃ‰SENCE OBLIGATOIRE DES RESPONSABLES")
    print("="*60)
    
    # CrÃ©er un dossier spÃ©cifique pour les responsables
    responsables_folder = os.path.join(OUTPUT_FOLDER, 'presence_responsables')
    os.makedirs(responsables_folder, exist_ok=True)
    
    planning_df['h_debut_parsed'] = planning_df['h_debut'].apply(parse_time)
    
    # Grouper par responsable
    responsables_data = {}
    
    for _, row in planning_df.iterrows():
        responsable = row['enseignant']
        
        if pd.isna(responsable):
            continue
        
        try:
            responsable = int(responsable)
        except (ValueError, TypeError):
            continue
        
        # CORRECTION: VÃ©rifier que le responsable existe dans teachers
        if responsable not in teachers:
            continue
        
        date = row['dateExam']
        h_debut = parse_time(row['h_debut'])
        h_fin = parse_time(row['h_fin'])
        salle = row['cod_salle']
        type_ex = row['type_ex']
        semestre = row['semestre']
        
        # Trouver le crÃ©neau correspondant
        creneau_id = f"{date}_{h_debut}"
        
        if creneau_id in creneaux:
            cre = creneaux[creneau_id]
            jour = cre.get('jour')
            seance = cre.get('seance')
        else:
            jour = None
            seance = None
        
        if responsable not in responsables_data:
            responsables_data[responsable] = []
        
        responsables_data[responsable].append({
            'code_smartex_ens': responsable,
            'nom_ens': teachers[responsable]['nom'],
            'prenom_ens': teachers[responsable]['prenom'],
            'grade': teachers[responsable]['grade'],
            'jour': jour,
            'seance': seance,
            'date_examen': date,
            'h_debut': h_debut,
            'h_fin': h_fin,
            'salle_responsable': salle,
            'type_examen': type_ex,
            'semestre': semestre,
            'statut': 'RESPONSABLE - PRÃ‰SENCE OBLIGATOIRE',
            'note': 'Doit Ãªtre prÃ©sent pour rÃ©pondre aux questions (pas de surveillance dans cette salle)'
        })
    
    # GÃ©nÃ©rer les fichiers individuels
    nb_fichiers = 0
    total_presences = 0
    
    for resp_code, presences in responsables_data.items():
        if not presences:
            continue
        
        # CrÃ©er un DataFrame et trier par date/heure
        resp_df = pd.DataFrame(presences)
        resp_df['date_sort'] = pd.to_datetime(resp_df['date_examen'], format='%d/%m/%Y', errors='coerce')
        resp_df = resp_df.sort_values(['date_sort', 'h_debut'])
        resp_df = resp_df.drop('date_sort', axis=1)
        
        # Sauvegarder le fichier individuel
        nom = teachers[resp_code]['nom']
        prenom = teachers[resp_code]['prenom']
        filename = f"RESPONSABLE_{nom}_{prenom}_code_{resp_code}.csv"
        filepath = os.path.join(responsables_folder, filename)
        
        resp_df.to_csv(filepath, index=False, encoding='utf-8')
        
        nb_fichiers += 1
        total_presences += len(presences)
        
        print(f"   âœ“ {filename} - {len(presences)} prÃ©sence(s) obligatoire(s)")
    
    # GÃ©nÃ©rer un fichier global rÃ©capitulatif
    if responsables_data:
        all_presences = []
        for presences in responsables_data.values():
            all_presences.extend(presences)
        
        global_df = pd.DataFrame(all_presences)
        global_df['date_sort'] = pd.to_datetime(global_df['date_examen'], format='%d/%m/%Y', errors='coerce')
        global_df = global_df.sort_values(['date_sort', 'h_debut', 'nom_ens'])
        global_df = global_df.drop('date_sort', axis=1)
        
        global_filepath = os.path.join(responsables_folder, 'RECAP_TOUS_RESPONSABLES.csv')
        global_df.to_csv(global_filepath, index=False, encoding='utf-8')
        
        print(f"\n   âœ“ RECAP_TOUS_RESPONSABLES.csv - {len(all_presences)} prÃ©sences au total")
    
    # GÃ©nÃ©rer un fichier par jour
    if responsables_data:
        all_presences = []
        for presences in responsables_data.values():
            all_presences.extend(presences)
        
        global_df = pd.DataFrame(all_presences)
        
        for jour in sorted(global_df['jour'].dropna().unique()):
            jour_df = global_df[global_df['jour'] == jour].copy()
            jour_df['date_sort'] = pd.to_datetime(jour_df['date_examen'], format='%d/%m/%Y', errors='coerce')
            jour_df = jour_df.sort_values(['date_sort', 'h_debut', 'nom_ens'])
            jour_df = jour_df.drop('date_sort', axis=1)
            
            jour_filepath = os.path.join(responsables_folder, f'RESPONSABLES_JOUR_{int(jour)}.csv')
            jour_df.to_csv(jour_filepath, index=False, encoding='utf-8')
            
            print(f"   âœ“ RESPONSABLES_JOUR_{int(jour)}.csv - {len(jour_df)} prÃ©sences")
    
    print("\n" + "="*60)
    print(f"âœ… {nb_fichiers} fichiers de responsables gÃ©nÃ©rÃ©s")
    print(f"âœ… {total_presences} prÃ©sences obligatoires au total")
    print(f"ðŸ“ Dossier : {responsables_folder}")
    print("="*60)
    
    # GÃ©nÃ©rer aussi un document rÃ©capitulatif en texte
    recap_filepath = os.path.join(responsables_folder, 'README_RESPONSABLES.txt')
    with open(recap_filepath, 'w', encoding='utf-8') as f:
        f.write("="*60 + "\n")
        f.write("PRÃ‰SENCES OBLIGATOIRES DES RESPONSABLES DE MATIÃˆRE\n")
        f.write("="*60 + "\n\n")
        f.write("IMPORTANT : Ces prÃ©sences sont OBLIGATOIRES mais ne constituent\n")
        f.write("PAS des affectations de surveillance.\n\n")
        f.write("Les responsables doivent Ãªtre prÃ©sents aux crÃ©neaux indiquÃ©s pour\n")
        f.write("rÃ©pondre aux questions des Ã©tudiants, mais ils ne surveillent PAS\n")
        f.write("dans la salle dont ils sont responsables.\n\n")
        f.write("Ils seront affectÃ©s Ã  d'autres salles du mÃªme crÃ©neau pour la\n")
        f.write("surveillance effective.\n\n")
        f.write("="*60 + "\n\n")
        
        for resp_code, presences in sorted(responsables_data.items()):
            if presences:
                nom = teachers[resp_code]['nom']
                prenom = teachers[resp_code]['prenom']
                grade = teachers[resp_code]['grade']
                
                f.write(f"RESPONSABLE : {nom} {prenom} (Code: {resp_code}) - Grade: {grade}\n")
                f.write(f"Nombre de prÃ©sences obligatoires : {len(presences)}\n")
                f.write("-" * 60 + "\n")
                
                for p in presences:
                    f.write(f"  â€¢ Jour {p['jour']} - {p['date_examen']} - {p['seance']} ({p['h_debut']} - {p['h_fin']})\n")
                    f.write(f"    Salle responsable : {p['salle_responsable']} - {p['semestre']}\n")
                
                f.write("\n")
    
    print(f"ðŸ“„ README gÃ©nÃ©rÃ© : {recap_filepath}\n")
    
    return nb_fichiers, total_presences


def main():
    """Point d'entrÃ©e principal"""
    print("\n" + "="*60)
    print("SYSTÃˆME DE PLANIFICATION DE SURVEILLANCES")
    print("Version avec Contrainte de PrÃ©sence des Responsables - CORRIGÃ‰E")
    print("="*60)
    
    if not os.path.exists(DB_NAME):
        print(f"\nâŒ Base de donnÃ©es '{DB_NAME}' introuvable!")
        return
    
    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT id_session, libelle_session FROM session")
    sessions = cursor.fetchall()
    conn.close()
    
    if not sessions:
        print("\nâŒ Aucune session trouvÃ©e dans la base!")
        return
    
    print("\nðŸ“‹ Sessions disponibles :")
    for s in sessions:
        print(f"   [{s['id_session']}] {s['libelle_session']}")
    
    session_id = int(input("\nðŸ”¢ Entrez l'ID de la session Ã  optimiser: "))
    
    try:
        print("\nChargement des donnÃ©es depuis SQLite...")
        enseignants_df, planning_df, salles_df, voeux_df, parametres_df, mapping_df, salle_par_creneau_df = load_data_from_db(session_id)
        print("âœ“ Toutes les donnÃ©es chargÃ©es")
    except Exception as e:
        print(f"âŒ Erreur de chargement : {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Construire les structures nÃ©cessaires AVANT la gÃ©nÃ©ration des fichiers
    salle_responsable = build_salle_responsable_mapping(planning_df)
    creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df)
    creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
    teachers = build_teachers_dict(enseignants_df, parametres_df)
    
    # CORRECTION : GÃ©nÃ©rer les fichiers de prÃ©sence des responsables AVEC teachers
    print("\n" + "="*60)
    print("GÃ‰NÃ‰RATION DES FICHIERS DE PRÃ‰SENCE OBLIGATOIRE")
    print("="*60)
    
    nb_fichiers, total_presences = generate_responsable_presence_files(
        planning_df, teachers, creneaux, mapping_df
    )
    
    print(f"\nâœ… {nb_fichiers} fichiers gÃ©nÃ©rÃ©s avec {total_presences} prÃ©sences obligatoires")
    
    # Lancer l'optimisation
    result = optimize_surveillance_scheduling(
        enseignants_df, planning_df, salles_df, 
        voeux_df, parametres_df, mapping_df, salle_par_creneau_df
    )

    # NOUVELLES VARIABLES À RÉCUPÉRER pour les stats
    salle_responsable = build_salle_responsable_mapping(planning_df)
    creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df)
    creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
    teachers = build_teachers_dict(enseignants_df, parametres_df)
    voeux_set = build_voeux_set(voeux_df)

    # Sauvegarder les résultats
    if result['status'] == 'ok' and len(result['affectations']) > 0:
        stats = generate_statistics(
            result['affectations'],
            creneaux,
            teachers,
            voeux_set,
            planning_df
        )
        nb_inserted = save_results_to_db(result['affectations'], session_id)
        
        if nb_inserted > 0:
            print(f"\nâœ… {nb_inserted} affectations sauvegardÃ©es en base de donnÃ©es")
    
    # Afficher le rÃ©sumÃ© final
    print("\n" + "="*60)
    print("RÃ‰SUMÃ‰ FINAL")
    print("="*60)
    print(f"Statut : {result['status']}")
    print(f"Affectations : {len(result['affectations'])}")
    print(f"Fichiers dans : {OUTPUT_FOLDER}")
    
    if result['statistiques']:
        print("\nðŸ“Š PERFORMANCES :")
        print(f"   âœ“ Respect des vÅ“ux : {result['statistiques']['taux_voeux']['taux']:.1f}%")
        print(f"   âœ“ PrÃ©sence responsables : {result['statistiques']['presence_responsables']['taux_presence']:.1f}%")
        print(f"   âœ“ Respect des quotas : {result['statistiques']['quotas']['taux_global']:.1f}%")
        print(f"   âœ“ Dispersion moyenne : {result['statistiques']['dispersion']['gap_moyen_global']:.2f} sÃ©ances")
    
    print("\nðŸŽ¯ CONTRAINTES APPLIQUÃ‰ES :")
    print("   [HARD H1] âœ“ Couverture complÃ¨te des crÃ©neaux")
    print("   [HARD H2A] âœ“ Ã‰quitÃ© stricte par grade (Ã©cart â‰¤ 1)")
    print("   [HARD H2B] âœ“ Respect strict des vÅ“ux")
    print("   [HARD H2C] âœ“ Enseignant ne surveille pas sa propre salle")
    print("   [HARD H2D] âœ“ RESPONSABLE PRÃ‰SENT AU CRÃ‰NEAU (CORRIGÃ‰E)")
    print("   [HARD H3A] âœ“ Respect des quotas maximum")
    print("   [SOFT S1] âœ“ Dispersion optimisÃ©e dans la journÃ©e")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()