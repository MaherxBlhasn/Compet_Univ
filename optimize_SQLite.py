#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Planificateur de surveillances avec OR-Tools CP-SAT
Version SQLite : Lecture depuis BD + Écriture des résultats
VERSION CORRIGÉE
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


def save_results_to_db(affectations, session_id):
    """
    ÉTAPE FINALE : Sauvegarder les résultats dans la base de données
    """
    print("\n" + "="*60)
    print("SAUVEGARDE DANS LA BASE DE DONNÉES")
    print("="*60)
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        DELETE FROM affectation 
        WHERE creneau_id IN (
            SELECT creneau_id FROM creneau WHERE id_session = ?
        )
    """, (session_id,))
    
    print(f"\n🗑️ Anciennes affectations supprimées")
    
    creneaux_map = {}
    cursor.execute("""
        SELECT creneau_id, dateExam, h_debut, cod_salle
        FROM creneau
        WHERE id_session = ?
    """, (session_id,))
    
    for row in cursor.fetchall():
        key = (row['dateExam'], parse_time(row['h_debut']), row['cod_salle'])
        creneaux_map[key] = row['creneau_id']
    
    nb_inserted = 0
    nb_errors = 0
    
    for aff in affectations:
        date = aff['date']
        h_debut = aff['h_debut']
        salle = aff.get('cod_salle')
        code_ens = aff['code_smartex_ens']
        
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
                    INSERT INTO affectation (code_smartex_ens, creneau_id)
                    VALUES (?, ?)
                """, (code_ens, creneau_id))
                nb_inserted += 1
            except sqlite3.IntegrityError as e:
                nb_errors += 1
                if nb_errors <= 5:
                    print(f"⚠️ Erreur insertion: {e}")
        else:
            nb_errors += 1
            if nb_errors <= 5:
                print(f"⚠️ Créneau non trouvé: {date} {h_debut} {salle}")
    
    conn.commit()
    conn.close()
    
    print(f"\n✅ {nb_inserted} affectations insérées dans la base")
    if nb_errors > 0:
        print(f"⚠️ {nb_errors} erreurs d'insertion")
    
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
            c.enseignant as responsable_examen,
            v.jour
        FROM affectation a
        JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
        JOIN creneau c ON a.creneau_id = c.creneau_id
        LEFT JOIN (
            SELECT DISTINCT 
                dateExam, 
                h_debut,
                MAX(CASE 
                    WHEN CAST(strftime('%H', h_debut) AS INTEGER) BETWEEN 8 AND 9 THEN 1
                    WHEN CAST(strftime('%H', h_debut) AS INTEGER) BETWEEN 10 AND 11 THEN 2
                    WHEN CAST(strftime('%H', h_debut) AS INTEGER) BETWEEN 12 AND 13 THEN 3
                    WHEN CAST(strftime('%H', h_debut) AS INTEGER) BETWEEN 14 AND 16 THEN 4
                END) as jour
            FROM creneau
            WHERE id_session = ?
            GROUP BY dateExam
        ) v ON c.dateExam = v.dateExam
        WHERE c.id_session = ?
        ORDER BY c.dateExam, c.h_debut, c.cod_salle, e.nom_ens
    """
    
    aff_df = pd.read_sql_query(query, conn, params=(session_id, session_id))
    
    if aff_df.empty:
        print("⚠️ Aucune affectation à exporter")
        conn.close()
        return
    
    aff_df['seance'] = aff_df['h_debut'].apply(lambda x: determine_seance_from_time(x))
    
    # 1. Fichier global
    out_global = os.path.join(OUTPUT_FOLDER, 'affectations_global.csv')
    aff_df.to_csv(out_global, index=False, encoding='utf-8')
    print(f"\n✓ {out_global}")
    print(f"  📊 {len(aff_df)} affectations totales")
    
    # 2. Par jour
    if 'jour' in aff_df.columns and not aff_df['jour'].isna().all():
        for jour in sorted(aff_df['jour'].dropna().unique()):
            jour_df = aff_df[aff_df['jour'] == jour]
            out = os.path.join(OUTPUT_FOLDER, f'affectations_jour_{int(jour)}.csv')
            jour_df.to_csv(out, index=False, encoding='utf-8')
            print(f"✓ Jour {int(jour)}: {len(jour_df)} affectations")
    
    # 3. Convocations individuelles
    nb_convocations = 0
    for code in aff_df['code_smartex_ens'].unique():
        ens_df = aff_df[aff_df['code_smartex_ens'] == code].copy()
        nom = ens_df.iloc[0]['nom_ens']
        prenom = ens_df.iloc[0]['prenom_ens']
        
        out = os.path.join(OUTPUT_FOLDER, f'convocation_{nom}_{prenom}.csv')
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


def build_creneaux_from_salles(salles_df, salle_responsable):
    """Construire les créneaux avec distribution équitable"""
    print("\n=== ÉTAPE 1 : Construction des créneaux ===")
    
    salles_df['h_debut_parsed'] = salles_df['heure_debut'].apply(parse_time)
    salles_df['h_fin_parsed'] = salles_df['heure_fin'].apply(parse_time)
    
    creneau_groups = salles_df.groupby(['date_examen', 'h_debut_parsed', 'h_fin_parsed'])
    
    creneaux = {}
    for (date, h_debut, h_fin), group in creneau_groups:
        creneau_id = f"{date}_{h_debut}"
        nb_salles = len(group)
        
        nb_reserves = max(2, nb_salles // 4)
        nb_surveillants = 2 * nb_salles + nb_reserves
        
        salles_info = []
        for salle in group['salle'].tolist():
            key = (date, h_debut, salle)
            responsable = salle_responsable.get(key, None)
            salles_info.append({'salle': salle, 'responsable': responsable})
        
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


def build_teachers_dict(enseignants_df, parametres_df):
    """
    Construire le dictionnaire des enseignants - VERSION CORRIGÉE
    Utilise les données de la base au lieu de valeurs statiques
    """
    print("\n=== ÉTAPE 3 : Préparation des enseignants ===")
    
    # Créer un dictionnaire des quotas depuis parametres_df
    quotas_dict = {}
    for _, row in parametres_df.iterrows():
        quotas_dict[row['grade']] = int(row['max_surveillances'])
    
    print(f"📋 Quotas disponibles pour {len(quotas_dict)} grades:")
    for grade, quota in sorted(quotas_dict.items()):
        print(f"   {grade}: {quota} surveillances max")
    
    # Définir les priorités (ordre de sollicitation)
    # Plus le nombre est élevé, plus le grade est sollicité en priorité
    priorite_map = {
        'VA': 5, 'V': 5,
        'AC': 4, 'AS': 4, 'PES': 4, 'EX': 4,
        'PTC': 3,
        'MA': 2, 'MC': 2,
        'PR': 1
    }
    
    teachers = {}
    participent = 0
    grades_manquants = set()
    
    for _, row in enseignants_df.iterrows():
        code = row['code_smartex_ens']
        
        if pd.isna(code):
            continue
        
        try:
            code = int(code)
        except (ValueError, TypeError):
            continue
        
        grade = str(row['grade_code_ens']).strip().upper()
        
        # Obtenir le quota depuis la base
        quota = quotas_dict.get(grade)
        
        if quota is None:
            if grade not in grades_manquants:
                print(f"   ⚠️ Grade '{grade}' non trouvé dans parametres - quota par défaut: 8")
                grades_manquants.add(grade)
            quota = 8
        
        # Vérifier participe_surveillance (défaut: True si non spécifié)
        participe = row.get('participe_surveillance')
        if pd.isna(participe):
            participe = True
        else:
            participe = bool(int(participe))
        
        if participe:
            participent += 1
        
        # Obtenir la priorité
        priorite = priorite_map.get(grade, 3)  # 3 par défaut (milieu de gamme)
        
        teachers[code] = {
            'code': code,
            'nom': row['nom_ens'],
            'prenom': row['prenom_ens'],
            'grade': grade,
            'quota': quota,
            'priorite': priorite,
            'participe': participe
        }
    
    print(f"\n✓ {len(teachers)} enseignants chargés")
    print(f"✓ {participent} enseignants participent")
    
    # Afficher les statistiques par grade
    print(f"\n📊 Répartition par grade :")
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
        print(f"   {grade}: {stats['count']} enseignants × quota moy {quota_moy:.1f} = {stats['capacity']} surveillances max")
        total_capacity += stats['capacity']
    
    print(f"\n💪 CAPACITÉ TOTALE : {total_capacity} surveillances")
    
    return teachers


def build_voeux_set(voeux_df):
    """Construire l'ensemble des vœux"""
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


def check_feasibility(teachers, creneaux, voeux_set):
    """Vérifier la faisabilité du problème"""
    print("\n=== VÉRIFICATION DE FAISABILITÉ ===")
    print("-" * 60)
    
    teacher_codes = [c for c, t in teachers.items() if t['participe']]
    
    capacite_totale = sum(teachers[c]['quota'] for c in teacher_codes)
    surveillances_requises = sum(c['nb_surveillants'] for c in creneaux.values())
    
    print(f"👥 Enseignants participants : {len(teacher_codes)}")
    print(f"💪 Capacité totale : {capacite_totale} surveillances")
    print(f"📋 Surveillances requises : {surveillances_requises}")
    
    if capacite_totale == 0:
        print("❌ ERREUR : Aucune capacité!")
        return False
    
    ratio = capacite_totale / surveillances_requises if surveillances_requises > 0 else 0
    print(f"📊 Ratio capacité/besoin : {ratio:.2f}")
    
    if ratio < 1.0:
        print(f"\n❌ PROBLÈME INFAISABLE : Capacité insuffisante!")
        print(f"   Manque : {surveillances_requises - capacite_totale} surveillances")
        print(f"\n💡 Solutions :")
        print(f"   1. Augmenter les quotas dans la table 'grade'")
        print(f"   2. Mettre participe_surveillance=1 pour plus d'enseignants")
        print(f"   3. Réduire la formule : 2*nb_salles + 2 au lieu de + max(2, nb_salles//4)")
        return False
    
    # Vérifier créneau par créneau
    problemes = []
    for cid, cre in creneaux.items():
        if cre.get('jour') is None:
            continue
        
        disponibles = 0
        for tcode in teacher_codes:
            if (tcode, cre['jour'], cre['seance']) in voeux_set:
                continue
            if any(s.get('responsable') == tcode for s in cre.get('salles_info', [])):
                continue
            disponibles += 1
        
        if disponibles < cre['nb_surveillants']:
            problemes.append({
                'creneau': cid,
                'date': cre['date'],
                'heure': cre['h_debut'],
                'requis': cre['nb_surveillants'],
                'disponibles': disponibles,
                'manque': cre['nb_surveillants'] - disponibles
            })
    
    if problemes:
        print(f"\n❌ {len(problemes)} créneaux problématiques :")
        for i, p in enumerate(problemes[:5]):
            print(f"   {i+1}. {p['date']} {p['heure']} - Besoin: {p['requis']}, Dispo: {p['disponibles']} (manque {p['manque']})")
        
        if len(problemes) > 5:
            print(f"   ... et {len(problemes) - 5} autres créneaux")
        
        print(f"\n💡 Solutions :")
        print(f"   1. Réduire les vœux de non-surveillance")
        print(f"   2. Ajuster la formule de calcul des surveillants")
        return False
    
    print("\n✅ Vérifications OK : problème réalisable")
    return True


def optimize_with_ortools(teachers, creneaux, voeux_set):
    """Optimisation avec OR-Tools CP-SAT"""
    print("\n=== ÉTAPE 5 : Optimisation OR-Tools ===")
    
    if not check_feasibility(teachers, creneaux, voeux_set):
        return [], cp_model.INFEASIBLE, None
    
    teacher_codes = [c for c, t in teachers.items() if t['participe']]
    creneau_ids = [cid for cid, c in creneaux.items() if c.get('jour') is not None]
    
    model = cp_model.CpModel()
    x = {}
    
    nb_vars = 0
    nb_exclusions_voeux = 0
    nb_exclusions_resp = 0
    
    print("\n🔧 Création des variables...")
    for tcode in teacher_codes:
        for cid in creneau_ids:
            cre = creneaux[cid]
            
            if (tcode, cre['jour'], cre['seance']) in voeux_set:
                nb_exclusions_voeux += 1
                continue
            
            if any(s.get('responsable') == tcode for s in cre.get('salles_info', [])):
                nb_exclusions_resp += 1
                continue
            
            x[(tcode, cid)] = model.NewBoolVar(f"x_{tcode}_{cid}")
            nb_vars += 1
    
    print(f"✓ {nb_vars:,} variables créées")
    print(f"✓ {nb_exclusions_voeux:,} exclusions (vœux)")
    print(f"✓ {nb_exclusions_resp:,} exclusions (responsables)")
    
    print("\n🎯 Ajout des contraintes...")
    for cid in creneau_ids:
        vars_creneau = [x[(t, cid)] for t in teacher_codes if (t, cid) in x]
        required = creneaux[cid]['nb_surveillants']
        
        if len(vars_creneau) < required:
            print(f"⚠️ Créneau {cid}: {len(vars_creneau)} dispos < {required} requis")
        
        model.Add(sum(vars_creneau) == required)
    
    print(f"✓ Couverture : {len(creneau_ids)} créneaux")
    
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        if vars_teacher:
            model.Add(sum(vars_teacher) <= teachers[tcode]['quota'])
    
    print(f"✓ Quotas : {len(teacher_codes)} enseignants")
    
    print("\n📈 Définition de l'objectif...")
    abs_deviations = []
    
    for tcode in teacher_codes:
        vars_teacher = [x[(tcode, cid)] for cid in creneau_ids if (tcode, cid) in x]
        if vars_teacher:
            quota = teachers[tcode]['quota']
            nb_aff = model.NewIntVar(0, len(creneau_ids), f"nb_{tcode}")
            model.Add(nb_aff == sum(vars_teacher))
            
            delta = model.NewIntVar(-len(creneau_ids), len(creneau_ids), f"delta_{tcode}")
            model.Add(delta == nb_aff - quota)
            
            abs_delta = model.NewIntVar(0, len(creneau_ids), f"abs_{tcode}")
            model.AddAbsEquality(abs_delta, delta)
            abs_deviations.append(abs_delta)
    
    model.Minimize(sum(abs_deviations))
    print(f"✓ Objectif : minimiser écarts pour {len(abs_deviations)} enseignants")
    
    print("\n⚙️ Résolution en cours...")
    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = 180
    solver.parameters.num_search_workers = 8
    
    status = solver.Solve(model)
    
    print(f"✓ Statut: {solver.StatusName(status)}")
    print(f"✓ Temps: {solver.WallTime():.2f}s")
    
    affectations = []
    if status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
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
        
        print(f"\n✅ {len(affectations)} affectations générées")
        
        affectations = assign_to_rooms(affectations, creneaux)
    else:
        print("\n❌ Échec de l'optimisation")
        if status == cp_model.INFEASIBLE:
            print("Le modèle est INFAISABLE (contradictions)")
    
    return affectations, status, solver


def assign_to_rooms(affectations, creneaux):
    """Affecter les surveillants aux salles"""
    aff_df = pd.DataFrame(affectations)
    results = []
    
    for cid in aff_df['creneau_id'].unique():
        cre_affs = aff_df[aff_df['creneau_id'] == cid].copy()
        salles_info = creneaux[cid]['salles_info']
        
        idx = 0
        for salle_info in salles_info:
            for j in range(2):
                if idx < len(cre_affs):
                    row = cre_affs.iloc[idx].to_dict()
                    row['cod_salle'] = salle_info['salle']
                    row['responsable_salle'] = (j == 0)
                    results.append(row)
                    idx += 1
        
        nb_reserves = creneaux[cid]['nb_reserves']
        for j in range(nb_reserves):
            if idx < len(cre_affs):
                row = cre_affs.iloc[idx].to_dict()
                row['cod_salle'] = 'RESERVE'
                row['responsable_salle'] = False
                results.append(row)
                idx += 1
    
    return results


def main():
    """Point d'entrée principal"""
    print("\n" + "="*60)
    print("SYSTÈME DE PLANIFICATION - VERSION SQLite CORRIGÉE")
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
    
    # 1. Charger les données
    enseignants_df, planning_df, salles_df, voeux_df, parametres_df, mapping_df = load_data_from_db(session_id)
    
    # 2. Optimiser - CORRECTION: Passer parametres_df à build_teachers_dict
    salle_responsable = build_salle_responsable_mapping(planning_df)
    creneaux = build_creneaux_from_salles(salles_df, salle_responsable)
    creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
    teachers = build_teachers_dict(enseignants_df, parametres_df)  # CORRIGÉ ICI
    voeux_set = build_voeux_set(voeux_df)
    
    affectations, status, solver = optimize_with_ortools(teachers, creneaux, voeux_set)
    
    # 3. Sauvegarder les résultats
    if affectations and status in (cp_model.OPTIMAL, cp_model.FEASIBLE):
        print(f"\n✅ {len(affectations)} affectations générées")
        
        nb_inserted = save_results_to_db(affectations, session_id)
        
        export_results_to_csv(session_id)
        
        print("\n" + "="*60)
        print("RÉSUMÉ FINAL")
        print("="*60)
        print(f"✓ Statut : {solver.StatusName(status)}")
        print(f"✓ Affectations : {len(affectations)}")
        print(f"✓ Sauvegardées en BD : {nb_inserted}")
        print(f"✓ Fichiers CSV dans : {OUTPUT_FOLDER}")
        print("="*60 + "\n")
    else:
        print("\n" + "="*60)
        print("❌ OPTIMISATION ÉCHOUÉE")
        print("="*60)
        
        if status == cp_model.INFEASIBLE:
            print("\n🔍 DIAGNOSTIC :")
            print("   Le problème est INFAISABLE - les contraintes sont contradictoires")
            print("\n💡 SOLUTIONS POSSIBLES :")
            print("   1. Vérifier les quotas : SELECT * FROM grade;")
            print("   2. Augmenter les quotas dans la table 'grade'")
            print("   3. Réduire les vœux de non-surveillance")
            print("   4. Vérifier que tous les enseignants ont participe_surveillance=1")
            print("   5. Modifier la formule dans build_creneaux_from_salles() :")
            print("      Ligne ~150 : nb_surveillants = 2 * nb_salles + 2")
            print("\n📊 Pour plus d'infos, lancez : python verify_db.py")
        else:
            print(f"\n❌ Erreur : {solver.StatusName(status)}")
        
        print("="*60 + "\n")


if __name__ == "__main__":
    main()