#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Planificateur de surveillances avec OR-Tools CP-SAT
Version SQLite avec TOUTES les contraintes du CSV
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
    
    # 1. Charger les enseignants avec leurs grades
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
    
    # 4. Charger les vœux de non-surveillance
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
    
    # 5. Charger les paramètres de grades DIRECTEMENT depuis la base
    print("\n⚙️ Chargement des paramètres de grades...")
    parametres_df = pd.read_sql_query("""
        SELECT 
            code_grade as grade,
            quota as max_surveillances
        FROM grade
    """, conn)
    print(f"✓ {len(parametres_df)} grades chargés")
    
    # 6. Créer mapping jours/séances depuis les créneaux
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
    
    return enseignants_df, planning_df, salles_df, voeux_df, parametres_df, mapping_df


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


def build_creneaux_from_salles(salles_df, salle_responsable):
    """
    Construire les créneaux avec distribution équitable des surveillants
    et inclure les informations sur les responsables de salle
    """
    print("\n=== ÉTAPE 1 : Construction des créneaux ===")
    
    salles_df['h_debut_parsed'] = salles_df['heure_debut'].apply(parse_time)
    salles_df['h_fin_parsed'] = salles_df['heure_fin'].apply(parse_time)
    
    creneau_groups = salles_df.groupby(['date_examen', 'h_debut_parsed', 'h_fin_parsed'])
    
    creneaux = {}
    for (date, h_debut, h_fin), group in creneau_groups:
        creneau_id = f"{date}_{h_debut}"
        nb_salles = len(group)
        
        # Distribution équitable : 2 par salle + réserves distribuées
        nb_reserves = max(2, nb_salles // 4)
        nb_surveillants = 2 * nb_salles + nb_reserves
        
        # Associer chaque salle à son responsable
        salles_info = []
        for salle in group['salle'].tolist():
            key = (date, h_debut, salle)
            responsable = salle_responsable.get(key, None)
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
            print(f"⚠️ Pas de mapping pour créneau {cid}")
            cre['jour'] = None
            cre['seance'] = None
    
    print(f"✓ {sum(1 for c in creneaux.values() if c['jour'] is not None)} créneaux mappés")
    return creneaux


def build_teachers_dict(enseignants_df, parametres_df):
    """Construire le dictionnaire des enseignants avec leurs quotas"""
    print("\n=== ÉTAPE 3 : Préparation des enseignants ===")
    
    # Construire le mapping grade -> quota depuis parametres_df
    grade_quotas = {}
    for _, row in parametres_df.iterrows():
        grade = str(row['grade']).strip().upper()
        quota = int(row['max_surveillances'])
        grade_quotas[grade] = quota
    
    print(f"📋 Quotas disponibles pour {len(grade_quotas)} grades:")
    for grade in sorted(grade_quotas.keys()):
        print(f"   {grade}: {grade_quotas[grade]} surveillances max")
    
    teachers = {}
    participent = 0
    grades_manquants = set()
    
    # PLUS DE MAPPING - On garde les grades ORIGINAUX
    # Définir les priorités pour tous les grades
    priorite_map = {
        'PR': 1,
        'MA': 2, 'MC': 2,
        'PTC': 3,
        'AC': 4, 'AS': 4, 'PES': 4, 'EX': 4,
        'VA': 5, 'V': 5
    }
    
    for _, row in enseignants_df.iterrows():
        code = row['code_smartex_ens']
        
        if pd.isna(code):
            continue
        
        try:
            code = int(code)
        except (ValueError, TypeError):
            continue
        
        grade = str(row['grade_code_ens']).strip().upper()
        
        # Vérifier que le grade existe dans parametres_df
        if grade not in grade_quotas:
            if grade not in grades_manquants:
                print(f"   ⚠️ Grade '{grade}' non trouvé dans parametres - IGNORÉ")
                grades_manquants.add(grade)
            continue
        
        quota = grade_quotas[grade]
        
        # Vérifier participe_surveillance
        participe = row.get('participe_surveillance')
        if pd.isna(participe):
            participe = True
        else:
            participe = bool(int(participe))
        
        if participe:
            participent += 1
        
        # Obtenir la priorité
        priorite = priorite_map.get(grade, 3)
        
        teachers[code] = {
            'code': code,
            'nom': row['nom_ens'],
            'prenom': row['prenom_ens'],
            'grade': grade,  # GRADE ORIGINAL, pas mappé
            'quota': quota,
            'priorite': priorite,
            'participe': participe
        }
    
    print(f"\n✓ {len(teachers)} enseignants chargés")
    print(f"✓ {participent} enseignants participent")
    print(f"✓ Répartition par grade :")
    
    # Afficher TOUS les grades présents
    grades_stats = {}
    for t in teachers.values():
        if t['participe']:
            grade = t['grade']
            if grade not in grades_stats:
                grades_stats[grade] = {'count': 0, 'capacity': 0}
            grades_stats[grade]['count'] += 1
            grades_stats[grade]['capacity'] += t['quota']
    
    total_capacity = 0
    for grade in sorted(grades_stats.keys()):
        stats = grades_stats[grade]
        quota_moy = stats['capacity'] / stats['count'] if stats['count'] > 0 else 0
        print(f"     {grade}: {stats['count']} enseignants × quota moy {quota_moy:.1f} = {stats['capacity']} surveillances max")
        total_capacity += stats['capacity']
    
    print(f"\n💪 CAPACITÉ TOTALE : {total_capacity} surveillances")
    
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


def check_feasibility_detailed(teachers, creneaux, voeux_set):
    """
    DIAGNOSTIC DÉTAILLÉ de faisabilité
    """
    print("\n" + "="*60)
    print("🔍 DIAGNOSTIC DE FAISABILITÉ DÉTAILLÉ")
    print("="*60)
    
    teacher_codes = [c for c, t in teachers.items() if t['participe']]
    creneau_ids = [cid for cid, c in creneaux.items() if c['jour'] is not None]
    
    # 1. CAPACITÉ GLOBALE
    print("\n📊 1. VÉRIFICATION DE LA CAPACITÉ GLOBALE")
    print("-" * 60)
    
    capacite_totale = sum(teachers[c]['quota'] for c in teacher_codes)
    surveillances_requises = sum(c['nb_surveillants'] for c in creneaux.values() if c['jour'] is not None)
    
    print(f"👥 Enseignants participants : {len(teacher_codes)}")
    print(f"💪 Capacité totale : {capacite_totale} surveillances")
    print(f"📋 Surveillances requises : {surveillances_requises}")
    
    ratio_global = (capacite_totale / surveillances_requises * 100) if surveillances_requises > 0 else 0
    print(f"📈 Ratio capacité/besoin : {ratio_global:.1f}%")
    
    if capacite_totale < surveillances_requises:
        deficit = surveillances_requises - capacite_totale
        print(f"\n❌ CAPACITÉ INSUFFISANTE!")
        print(f"   Manque : {deficit} surveillances ({deficit/surveillances_requises*100:.1f}%)")
        print(f"\n💡 SOLUTIONS :")
        print(f"   1. Augmenter les quotas dans la table 'grade'")
        print(f"   2. Mettre participe_surveillance=1 pour plus d'enseignants")
        print(f"   3. Réduire la formule : nb_surveillants = 2 * nb_salles + 2")
        return False
    else:
        print(f"✅ Capacité globale suffisante (marge: {capacite_totale - surveillances_requises})")
    
    # 2. ANALYSE PAR GRADE
    print("\n📊 2. ANALYSE PAR GRADE")
    print("-" * 60)
    
    teachers_by_grade = {}
    for tcode in teacher_codes:
        grade = teachers[tcode]['grade']
        if grade not in teachers_by_grade:
            teachers_by_grade[grade] = []
        teachers_by_grade[grade].append(tcode)
    
    for grade in sorted(teachers_by_grade.keys()):
        tcodes = teachers_by_grade[grade]
        capacity = sum(teachers[tc]['quota'] for tc in tcodes)
        print(f"   {grade}: {len(tcodes)} enseignants × quota moy {capacity/len(tcodes):.1f} = {capacity} surveillances")
    
    # 3. VÉRIFICATION CRÉNEAU PAR CRÉNEAU
    print("\n📊 3. VÉRIFICATION CRÉNEAU PAR CRÉNEAU")
    print("-" * 60)
    
    problemes = []
    
    for cid in creneau_ids:
        cre = creneaux[cid]
        
        # Compter les enseignants disponibles pour ce créneau
        disponibles = 0
        exclus_voeux = 0
        exclus_responsable = 0
        
        for tcode in teacher_codes:
            # Vérifier les vœux
            if (tcode, cre['jour'], cre['seance']) in voeux_set:
                exclus_voeux += 1
                continue
            
            # Vérifier responsable de salle
            est_responsable = False
            for salle_info in cre.get('salles_info', []):
                if salle_info['responsable'] == tcode:
                    est_responsable = True
                    exclus_responsable += 1
                    break
            
            if est_responsable:
                continue
            
            disponibles += 1
        
        requis = cre['nb_surveillants']
        
        if disponibles < requis:
            problemes.append({
                'creneau': cid,
                'date': cre['date'],
                'heure': cre['h_debut'],
                'jour': cre['jour'],
                'seance': cre['seance'],
                'nb_salles': cre['nb_salles'],
                'requis': requis,
                'disponibles': disponibles,
                'manque': requis - disponibles,
                'exclus_voeux': exclus_voeux,
                'exclus_responsable': exclus_responsable
            })
    
    if problemes:
        print(f"\n❌ {len(problemes)} CRÉNEAUX PROBLÉMATIQUES trouvés :")
        print("-" * 60)
        
        for i, p in enumerate(problemes[:10], 1):
            print(f"\n{i}. Créneau : {p['creneau']}")
            print(f"   Date : {p['date']} {p['heure']} (Jour {p['jour']}, {p['seance']})")
            print(f"   Salles : {p['nb_salles']}")
            print(f"   Besoin : {p['requis']} surveillants")
            print(f"   Disponibles : {p['disponibles']}")
            print(f"   MANQUE : {p['manque']} surveillants")
            print(f"   Exclusions : {p['exclus_voeux']} vœux + {p['exclus_responsable']} responsables")
        
        if len(problemes) > 10:
            print(f"\n   ... et {len(problemes) - 10} autres créneaux problématiques")
        
        print(f"\n💡 SOLUTIONS POSSIBLES :")
        print(f"   1. Réduire les vœux de non-surveillance pour ces créneaux")
        print(f"   2. Modifier la formule de calcul des surveillants requis :")
        print(f"      Actuellement : nb_surveillants = 2 * nb_salles + max(2, nb_salles//4)")
        print(f"      Proposition : nb_surveillants = 2 * nb_salles + 1")
        print(f"   3. Augmenter les quotas des enseignants")
        print(f"   4. Vérifier les responsables d'examen (enseignant dans la table creneau)")
        
        return False
    else:
        print(f"✅ Tous les créneaux ont suffisamment d'enseignants disponibles")
    
    # 4. VÉRIFICATION ÉQUITÉ PAR GRADE
    print("\n📊 4. VÉRIFICATION ÉQUITÉ PAR GRADE")
    print("-" * 60)
    
    for grade, tcodes in teachers_by_grade.items():
        if len(tcodes) <= 1:
            continue
        
        quotas = [teachers[tc]['quota'] for tc in tcodes]
        min_q = min(quotas)
        max_q = max(quotas)
        
        if max_q - min_q > 1:
            print(f"   ⚠️ {grade}: écart de quotas = {max_q - min_q} (min={min_q}, max={max_q})")
            print(f"      Avec contrainte d'équité stricte (écart max 1), cela peut poser problème")
        else:
            print(f"   ✅ {grade}: quotas homogènes (min={min_q}, max={max_q})")
    
    print("\n✅ DIAGNOSTIC : Problème FAISABLE a priori")
    print("=" * 60)
    return True


def optimize_surveillance_scheduling(
    enseignants_df,
    planning_df,
    salles_df,
    voeux_df,
    parametres_df,
    mapping_df
):
    """
    OPTIMISATION PRINCIPALE avec contrainte responsable de salle
    """
    print("\n" + "="*60)
    print("DÉMARRAGE DE L'OPTIMISATION OR-TOOLS CP-SAT")
    print("="*60)
    
    salle_responsable = build_salle_responsable_mapping(planning_df)
    creneaux = build_creneaux_from_salles(salles_df, salle_responsable)
    creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
    teachers = build_teachers_dict(enseignants_df, parametres_df)
    voeux_set = build_voeux_set(voeux_df)
    
    # DIAGNOSTIC AVANT OPTIMISATION
    if not check_feasibility_detailed(teachers, creneaux, voeux_set):
        print("\n❌ Problème détecté INFAISABLE - Arrêt")
        return {
            'status': 'infeasible',
            'affectations': [],
            'statistiques': {
                'status_solver': 'INFEASIBLE_DETECTED',
                'nb_affectations': 0,
                'temps_resolution': 0
            }
        }
    
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
    
    # ========================================================================
    # PRIORITÉ 1 : COUVERTURE COMPLÈTE (CONTRAINTE HARD)
    # ========================================================================
    print("\n[PRIORITÉ 1] Contrainte de couverture complète des créneaux")
    for cid in creneau_ids:
        vars_creneau = [x[(t, cid)] for t in teacher_codes if (t, cid) in x]
        required = creneaux[cid]['nb_surveillants']
        model.Add(sum(vars_creneau) == required)
    print(f"✓ H1 : {len(creneau_ids)} créneaux doivent être couverts exactement")
    
    # ========================================================================
    # PRIORITÉ 2A : ÉQUITÉ STRICTE PAR GRADE (CONTRAINTE HARD)
    # ========================================================================
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
    
    # ========================================================================
    # PRIORITÉ 2B : RESPECT STRICT DES VŒUX (CONTRAINTE HARD - déjà géré)
    # ========================================================================
    print("\n[PRIORITÉ 2B] Respect strict des vœux de non-surveillance")
    print(f"✓ H2B : {nb_exclusions} vœux respectés par construction des variables")
    
    # ========================================================================
    # PRIORITÉ 2C : RESPECT RESPONSABLE DE SALLE (CONTRAINTE HARD - déjà géré)
    # ========================================================================
    print("\n[PRIORITÉ 2C] Respect de la contrainte responsable de salle")
    print(f"✓ H2C : {nb_exclusions_responsable} exclusions (enseignant ne surveille pas sa propre salle)")
    
    # ========================================================================
    # PRIORITÉ 3A : QUOTAS MAXIMUM (CONTRAINTE HARD)
    # ========================================================================
    print("\n[PRIORITÉ 3A] Respect des quotas maximum par enseignant")
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        quota = teachers[tcode]['quota']
        
        if vars_teacher:
            model.Add(sum(vars_teacher) <= quota)
    
    print(f"✓ H3A : {len(teacher_codes)} enseignants limités à leur quota")
    
    # ========================================================================
    # PRIORITÉ 3B : TAUX DE SURVEILLANCE PAR GRADE ÉQUILIBRÉ (OBJECTIF)
    # ========================================================================
    print("\n[PRIORITÉ 3B] Taux de surveillance équilibré entre grades")
    
    # Calculer le taux de surveillance pour chaque grade
    grade_usage_vars = {}
    grade_capacity = {}
    
    for grade, tcodes_grade in teachers_by_grade.items():
        # Capacité totale du grade
        capacity = sum(teachers[tc]['quota'] for tc in tcodes_grade)
        grade_capacity[grade] = capacity
        
        # Nombre total d'affectations du grade
        all_vars = []
        for tc in tcodes_grade:
            vars_teacher = [x[(tc, cid)] for cid in creneau_ids if (tc, cid) in x]
            all_vars.extend(vars_teacher)
        
        if all_vars and capacity > 0:
            usage = model.NewIntVar(0, len(all_vars), f"usage_{grade}")
            model.Add(usage == sum(all_vars))
            grade_usage_vars[grade] = usage
    
    print(f"✓ S3B : Taux d'utilisation calculé pour {len(grade_usage_vars)} grades")
    
    # ========================================================================
    # PRIORITÉ 4 : DISPERSION DANS LA MÊME JOURNÉE (CONTRAINTE SOFT)
    # ========================================================================
    print("\n[PRIORITÉ 4] Dispersion des surveillances dans la même journée")
    
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
            
            # Obtenir les numéros de séance pour ce jour
            seances_info = []
            for cid in cids_jour:
                seance_num = get_seance_number(creneaux[cid]['seance'])
                if seance_num is not None:
                    seances_info.append((cid, seance_num))
            
            # Si un enseignant a S1 et S3, c'est une pénalité
            # Si un enseignant a S1 et S4, c'est une pénalité
            for i in range(len(seances_info)):
                for j in range(i + 1, len(seances_info)):
                    cid1, s1 = seances_info[i]
                    cid2, s2 = seances_info[j]
                    
                    gap = abs(s2 - s1)
                    if gap > 1:  # Non consécutif
                        # Pénalité proportionnelle à l'écart
                        both_assigned = model.NewBoolVar(f"both_{tcode}_{cid1}_{cid2}")
                        model.Add(both_assigned == 1).OnlyEnforceIf([x[(tcode, cid1)], x[(tcode, cid2)]])
                        model.Add(both_assigned == 0).OnlyEnforceIf([x[(tcode, cid1)].Not()])
                        model.Add(both_assigned == 0).OnlyEnforceIf([x[(tcode, cid2)].Not()])
                        
                        penalty = model.NewIntVar(0, gap * 10, f"penalty_{tcode}_{cid1}_{cid2}")
                        model.Add(penalty == gap * 10).OnlyEnforceIf(both_assigned)
                        model.Add(penalty == 0).OnlyEnforceIf(both_assigned.Not())
                        
                        dispersion_penalties.append(penalty)
    
    print(f"✓ S4 : {len(dispersion_penalties)} pénalités de dispersion possibles")
    
    # ========================================================================
    # OBJECTIF GLOBAL : Minimiser les déviations + pénalités
    # ========================================================================
    print("\n" + "="*60)
    print("DÉFINITION DE L'OBJECTIF")
    print("="*60)
    
    objective_terms = []
    
    # 1. Écarts individuels par rapport aux quotas (poids faible)
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
    
    # 2. Écarts de taux entre grades (poids élevé)
    if len(grade_usage_vars) > 1:
        grades_list = list(grade_usage_vars.keys())
        for i in range(len(grades_list)):
            for j in range(i + 1, len(grades_list)):
                g1, g2 = grades_list[i], grades_list[j]
                
                cap1 = max(1, grade_capacity[g1])
                cap2 = max(1, grade_capacity[g2])
                
                taux1 = model.NewIntVar(0, 1000, f"taux_{g1}")
                model.AddMultiplicationEquality(
                    grade_usage_vars[g1] * 1000,
                    [taux1, cap1]
                )
                
                taux2 = model.NewIntVar(0, 1000, f"taux_{g2}")
                model.AddMultiplicationEquality(
                    grade_usage_vars[g2] * 1000,
                    [taux2, cap2]
                )
                
                diff_taux = model.NewIntVar(-1000, 1000, f"diff_{g1}_{g2}")
                model.Add(diff_taux == taux1 - taux2)
                
                abs_diff_taux = model.NewIntVar(0, 1000, f"abs_diff_{g1}_{g2}")
                model.AddAbsEquality(abs_diff_taux, diff_taux)
                
                # Poids x100 pour priorité élevée
                objective_terms.append(abs_diff_taux * 100)
    
    # 3. Pénalités de dispersion (poids moyen)
    for penalty in dispersion_penalties:
        objective_terms.append(penalty * 5)
    
    model.Minimize(sum(objective_terms))
    
    print(f"✓ Objectif : minimiser {len(objective_terms)} termes")
    print(f"   - {len(teacher_codes)} écarts individuels (poids 1)")
    print(f"   - Écarts de taux entre grades (poids 100)")
    print(f"   - {len(dispersion_penalties)} pénalités de dispersion (poids 5)")
    
    # ========================================================================
    # RÉSOLUTION
    # ========================================================================
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
        print("\n📊 Taux d'utilisation par grade :")
        grade_capacity = {}
        for grade in teachers_by_grade:
            capacity = sum(teachers[tc]['quota'] for tc in teachers_by_grade[grade])
            grade_capacity[grade] = capacity
        
        # Afficher TOUS les grades présents
        for grade in sorted(teachers_by_grade.keys()):
            count = len(aff_temp_df[aff_temp_df['grade_code_ens'] == grade])
            capacity = grade_capacity.get(grade, 0)
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
    avec détermination du responsable_salle
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
        base_per_salle = 2
        
        # Distribution équitable des réserves
        surv_per_salle = [base_per_salle] * nb_salles
        
        # Distribuer les réserves de façon cyclique
        remaining = total_surv - (base_per_salle * nb_salles)
        idx = 0
        while remaining > 0:
            surv_per_salle[idx % nb_salles] += 1
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
        
        # Extras (si reste)
        while idx < len(cre_affs):
            row = cre_affs.iloc[idx].to_dict()
            row['cod_salle'] = 'EXTRA'
            row['responsable_salle'] = False
            row['position'] = 'EXTRA'
            results.append(row)
            idx += 1
        
        # Afficher la distribution
        print(f"   {cid}: {surv_per_salle} surveillants par salle (équilibré)")
    
    print(f"✓ {len(results)} affectations avec distribution équitable")
    return results


def save_results(affectations, enseignants_df, solver, status, nb_creneaux):
    """Sauvegarder les résultats TRIÉS en CSV uniquement"""
    print("\n=== SAUVEGARDE DES RÉSULTATS CSV ===")
    
    aff_df = pd.DataFrame(affectations)
    
    if aff_df.empty:
        print("⚠️ Aucune affectation à sauvegarder")
        return
    
    # Trier par date, heure, salle, nom
    aff_df['date_sort'] = pd.to_datetime(aff_df['date'], format='%d/%m/%Y', errors='coerce')
    aff_df = aff_df.sort_values(
        ['date_sort', 'h_debut', 'cod_salle', 'nom_ens'],
        na_position='last'
    )
    aff_df = aff_df.drop('date_sort', axis=1)
    
    # 1. Fichier global
    out_global = os.path.join(OUTPUT_FOLDER, 'affectations_global.csv')
    aff_df.to_csv(out_global, index=False, encoding='utf-8')
    print(f"✓ {out_global} ({len(aff_df)} affectations)")
    
    # 2. Par jour
    for jour in sorted(aff_df['jour'].unique()):
        jour_df = aff_df[aff_df['jour'] == jour].copy()
        out = os.path.join(OUTPUT_FOLDER, f'affectations_jour_{jour}.csv')
        jour_df.to_csv(out, index=False, encoding='utf-8')
    print(f"✓ {len(aff_df['jour'].unique())} fichiers par jour")
    
    # 3. Convocations individuelles
    for code in aff_df['code_smartex_ens'].unique():
        ens_df = aff_df[aff_df['code_smartex_ens'] == code].copy()
        nom = ens_df.iloc[0]['nom_ens']
        prenom = ens_df.iloc[0]['prenom_ens']
        out = os.path.join(OUTPUT_FOLDER, f'convocation_{nom}_{prenom}.csv')
        ens_df.to_csv(out, index=False, encoding='utf-8')
    print(f"✓ {len(aff_df['code_smartex_ens'].unique())} convocations individuelles")
    
    # 4. Rapport d'équité
    rapport_equite = aff_df.groupby(['code_smartex_ens', 'nom_ens', 'prenom_ens', 'grade_code_ens']).size().reset_index(name='nb_surveillances')
    
    # Ajouter les quotas
    quotas_dict = {}
    for _, row in enseignants_df.iterrows():
        code = row['code_smartex_ens']
        if pd.notna(code):
            try:
                code = int(code)
                quotas_dict[code] = row.get('quota', 0)
            except:
                pass
    
    rapport_equite['quota'] = rapport_equite['code_smartex_ens'].map(quotas_dict)
    rapport_equite['ecart_quota'] = rapport_equite['nb_surveillances'] - rapport_equite['quota']
    rapport_equite = rapport_equite.sort_values(['grade_code_ens', 'nb_surveillances'])
    
    out_rapport = os.path.join(OUTPUT_FOLDER, 'rapport_equite.csv')
    rapport_equite.to_csv(out_rapport, index=False, encoding='utf-8')
    print(f"✓ {out_rapport}")
    
    print(f"\n📊 Statistiques d'équité par grade :")
    for grade in sorted(rapport_equite['grade_code_ens'].unique()):
        grade_data = rapport_equite[rapport_equite['grade_code_ens'] == grade]
        min_s = grade_data['nb_surveillances'].min()
        max_s = grade_data['nb_surveillances'].max()
        avg_s = grade_data['nb_surveillances'].mean()
        print(f"   {grade}: min={min_s}, max={max_s}, moy={avg_s:.1f}, écart={max_s-min_s}")
    
    # 5. Statistiques JSON
    stats = {
        'date_execution': datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        'status_solver': solver.StatusName(status) if solver else 'N/A',
        'nb_enseignants_total': len(enseignants_df),
        'nb_creneaux': nb_creneaux,
        'nb_affectations': len(affectations),
        'temps_resolution': f"{solver.WallTime():.2f}s" if solver else 'N/A'
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
        WHERE creneau_id IN (
            SELECT creneau_id FROM creneau WHERE id_session = ?
        )
    """, (session_id,))
    
    print(f"\n🗑️ Anciennes affectations supprimées")
    
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
        
        # Ignorer les affectations EXTRA ou RESERVE sans salle réelle
        if salle in ['EXTRA', 'RESERVE', None]:
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
                # CORRECTION: Ajouter id_session dans l'INSERT
                cursor.execute("""
                    INSERT INTO affectation (code_smartex_ens, creneau_id, id_session)
                    VALUES (?, ?, ?)
                """, (code_ens, creneau_id, session_id))
                nb_inserted += 1
            except sqlite3.IntegrityError as e:
                nb_errors += 1
                error_msg = str(e)
                if error_msg not in errors_detail:
                    errors_detail[error_msg] = 0
                errors_detail[error_msg] += 1
                if nb_errors <= 3:
                    print(f"⚠️ Erreur insertion: {e}")
        else:
            nb_errors += 1
            if nb_errors <= 3:
                print(f"⚠️ Créneau non trouvé: {date} {h_debut} {salle}")
    
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


def export_results_to_csv(session_id):
    """
    Exporter les résultats depuis la base vers des fichiers CSV
    """
    print("\n" + "="*60)
    print("EXPORT DES RÉSULTATS VERS CSV")
    print("="*60)
    
    conn = get_db_connection()
    
    query = """
        SELECT 
            a.code_smartex_ens,
            e.nom_ens,
            e.prenom_ens,
            e.grade_code_ens,
            c.creneau_id,
            c.dateExam as date,
            c.h_debut,
            c.h_fin,
            c.cod_salle,
            c.enseignant as responsable_examen
        FROM affectation a
        JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
        JOIN creneau c ON a.creneau_id = c.creneau_id
        WHERE c.id_session = ?
        ORDER BY c.dateExam, c.h_debut, c.cod_salle, e.nom_ens
    """
    
    aff_df = pd.read_sql_query(query, conn, params=(session_id,))
    
    if aff_df.empty:
        print("⚠️ Aucune affectation à exporter")
        conn.close()
        return
    
    aff_df['seance'] = aff_df['h_debut'].apply(lambda x: determine_seance_from_time(x))
    
    # Calculer les jours
    dates_uniques = sorted(aff_df['date'].unique())
    date_to_jour = {date: idx+1 for idx, date in enumerate(dates_uniques)}
    aff_df['jour'] = aff_df['date'].map(date_to_jour)
    
    # 1. Fichier global
    out_global = os.path.join(OUTPUT_FOLDER, 'affectations_global_db.csv')
    aff_df.to_csv(out_global, index=False, encoding='utf-8')
    print(f"\n✓ {out_global}")
    print(f"  📊 {len(aff_df)} affectations totales")
    
    # 2. Par jour
    if 'jour' in aff_df.columns and not aff_df['jour'].isna().all():
        for jour in sorted(aff_df['jour'].dropna().unique()):
            jour_df = aff_df[aff_df['jour'] == jour]
            out = os.path.join(OUTPUT_FOLDER, f'affectations_jour_{int(jour)}_db.csv')
            jour_df.to_csv(out, index=False, encoding='utf-8')
            print(f"✓ Jour {int(jour)}: {len(jour_df)} affectations")
    
    # 3. Convocations individuelles
    nb_convocations = 0
    for code in aff_df['code_smartex_ens'].unique():
        ens_df = aff_df[aff_df['code_smartex_ens'] == code].copy()
        nom = ens_df.iloc[0]['nom_ens']
        prenom = ens_df.iloc[0]['prenom_ens']
        
        out = os.path.join(OUTPUT_FOLDER, f'convocation_{nom}_{prenom}_db.csv')
        ens_df.to_csv(out, index=False, encoding='utf-8')
        nb_convocations += 1
    
    print(f"\n✓ {nb_convocations} convocations individuelles générées")
    
    # 4. Rapport d'équité
    rapport_equite = aff_df.groupby(['code_smartex_ens', 'nom_ens', 'prenom_ens', 'grade_code_ens']).size().reset_index(name='nb_surveillances')
    
    quotas_df = pd.read_sql_query("""
        SELECT e.code_smartex_ens, g.quota
        FROM enseignant e
        JOIN grade g ON e.grade_code_ens = g.code_grade
    """, conn)
    
    rapport_equite = rapport_equite.merge(quotas_df, on='code_smartex_ens', how='left')
    rapport_equite['ecart_quota'] = rapport_equite['nb_surveillances'] - rapport_equite['quota']
    rapport_equite = rapport_equite.sort_values(['grade_code_ens', 'nb_surveillances'])
    
    out_rapport = os.path.join(OUTPUT_FOLDER, 'rapport_equite.csv')
    rapport_equite.to_csv(out_rapport, index=False, encoding='utf-8')
    print(f"✓ {out_rapport}")
    
    print("\n📊 Statistiques d'équité par grade :")
    for grade in rapport_equite['grade_code_ens'].unique():
        grade_data = rapport_equite[rapport_equite['grade_code_ens'] == grade]
        min_s = grade_data['nb_surveillances'].min()
        max_s = grade_data['nb_surveillances'].max()
        avg_s = grade_data['nb_surveillances'].mean()
        print(f"   {grade}: min={min_s}, max={max_s}, moy={avg_s:.1f}, écart={max_s-min_s}")
    
    conn.close()
    print("\n✅ Export CSV terminé")


def main():
    """Point d'entrée principal"""
    print("\n" + "="*60)
    print("SYSTÈME DE PLANIFICATION DE SURVEILLANCES")
    print("Version SQLite avec contrainte responsable de salle")
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
        enseignants_df, planning_df, salles_df, voeux_df, parametres_df, mapping_df = load_data_from_db(session_id)
        
        print("✓ Tous les fichiers chargés")
        
    except Exception as e:
        print(f"❌ Erreur de chargement : {e}")
        import traceback
        traceback.print_exc()
        return
    
    # Lancer l'optimisation
    result = optimize_surveillance_scheduling(
        enseignants_df, planning_df, salles_df, 
        voeux_df, parametres_df, mapping_df
    )
    
    # Sauvegarder les résultats uniquement si succès
    if result['status'] == 'ok' and len(result['affectations']) > 0:
        # Sauvegarder en base de données
        nb_inserted = save_results_to_db(result['affectations'], session_id)
        
        if nb_inserted > 0:
            print(f"\n✅ {nb_inserted} affectations sauvegardées en base de données")
        else:
            print("\n⚠️ Aucune affectation n'a été sauvegardée en base")
            print("💡 Vérifiez la structure de la table 'affectation'")
    
    # Afficher le résumé final UNE SEULE FOIS
    print("\n" + "="*60)
    print("RÉSUMÉ FINAL")
    print("="*60)
    print(f"Statut : {result['status']}")
    print(f"Affectations générées : {len(result['affectations'])}")
    print(f"Fichiers CSV dans : {OUTPUT_FOLDER}/")
    print(f"Base de données : {DB_NAME}")
    print("\n🎯 PRIORITÉS APPLIQUÉES :")
    print("   1. ✓ Couverture complète des créneaux")
    print("   2. ✓ Équité stricte par grade + Respect des vœux")
    print("   2C. ✓ Enseignant ne surveille pas sa propre salle")
    print("   3. ✓ Quotas max + Taux d'utilisation équilibré entre grades")
    print("   4. ✓ Dispersion dans la même journée")
    print("   5. ✓ Distribution équitable des réserves par salle")
    
    print("\n📁 FICHIERS GÉNÉRÉS :")
    print(f"   ✓ affectations_global.csv (fichier principal)")
    print(f"   ✓ affectations_jour_X.csv (par jour)")
    print(f"   ✓ convocation_NOM_PRENOM.csv (par enseignant)")
    print(f"   ✓ rapport_equite.csv (analyse d'équité)")
    print(f"   ✓ statistiques.json (métadonnées)")
    print("="*60 + "\n")


if __name__ == "__main__":
    main()