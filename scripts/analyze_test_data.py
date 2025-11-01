#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script d'analyse des fichiers de test pour diagnostiquer l'infaisabilité
"""

import pandas as pd
import sys
import os

# Ajouter le dossier parent au path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def analyze_test_files():
    """Analyser les fichiers de test pour comprendre l'infaisabilité"""
    
    print("="*80)
    print("ANALYSE DES FICHIERS DE TEST")
    print("="*80)
    
    # 1. Charger les enseignants
    enseignants_file = 'test_files/Ensiegnants-suveillance-Test.csv'
    enseignants_df = pd.read_csv(enseignants_file)
    
    print("\n📊 ANALYSE DES ENSEIGNANTS")
    print("-" * 80)
    
    # Enseignants participants
    participants = enseignants_df[enseignants_df['participe_surveillance'] == True]
    non_participants = enseignants_df[enseignants_df['participe_surveillance'] == False]
    
    print(f"Total enseignants         : {len(enseignants_df)}")
    print(f"Participants              : {len(participants)}")
    print(f"Non-participants          : {len(non_participants)}")
    
    # Grouper par grade
    print("\n📈 RÉPARTITION PAR GRADE (participants uniquement)")
    print("-" * 80)
    grades_count = participants.groupby('grade_code_ens').size().sort_index()
    
    # Charger les quotas par grade depuis la base de données
    import sqlite3
    conn = sqlite3.connect('surveillance.db')
    grades_df = pd.read_sql_query("SELECT code_grade, quota FROM grade", conn)
    grades_dict = dict(zip(grades_df['code_grade'], grades_df['quota']))
    
    total_capacity = 0
    for grade, count in grades_count.items():
        quota = grades_dict.get(grade, 0)
        capacity = count * quota
        total_capacity += capacity
        print(f"{grade:5s} : {count:3d} enseignants × quota {quota:2d} = capacité {capacity:4d}")
    
    print(f"\n{'TOTAL':5s} : {len(participants):3d} enseignants              = capacité {total_capacity:4d}")
    
    # 2. Charger les salles
    salles_file = 'test_files/Répartition salles.csv'
    salles_df = pd.read_csv(salles_file)
    
    print("\n\n📊 ANALYSE DES CRÉNEAUX")
    print("-" * 80)
    
    # Parser les heures
    def parse_time(time_str):
        if pd.isna(time_str):
            return None
        time_str = str(time_str)
        if ' ' in time_str:
            return time_str.split(' ')[1][:5]
        return time_str[:5]
    
    salles_df['h_debut_parsed'] = salles_df['h_debut'].apply(parse_time)
    
    # Grouper par créneau (date + heure)
    creneaux = salles_df.groupby(['dateExam', 'h_debut_parsed']).agg({
        'cod_salle': 'count'
    }).reset_index()
    creneaux.columns = ['date', 'heure', 'nb_salles']
    
    print(f"Nombre de créneaux : {len(creneaux)}")
    print("\nDétail des créneaux :")
    print(f"{'Date':12s} {'Heure':8s} {'Salles':>8s} {'Surveillants':>12s}")
    print("-" * 80)
    
    total_surveillances = 0
    for _, row in creneaux.iterrows():
        nb_salles = row['nb_salles']
        # Formule : 2 surveillants par salle + 4 réserves
        nb_surveillants = (nb_salles * 2) + 4
        total_surveillances += nb_surveillants
        print(f"{row['date']:12s} {row['heure']:8s} {nb_salles:8d} {nb_surveillants:12d}")
    
    print("-" * 80)
    print(f"{'TOTAL':21s} {creneaux['nb_salles'].sum():8d} {total_surveillances:12d}")
    
    # 3. Analyse globale
    print("\n\n🎯 ANALYSE GLOBALE")
    print("="*80)
    
    print(f"Surveillances nécessaires : {total_surveillances}")
    print(f"Capacité totale          : {total_capacity}")
    print(f"Différence               : {total_capacity - total_surveillances}")
    print(f"Ratio utilisation        : {total_surveillances / total_capacity * 100:.1f}%")
    
    if total_capacity >= total_surveillances:
        print("\n✅ CAPACITÉ SUFFISANTE en théorie")
        print("\nMais le problème peut être INFAISABLE pour d'autres raisons :")
        print("")
        print("🔍 CAUSES POSSIBLES D'INFAISABILITÉ :")
        print("-" * 80)
    else:
        print("\n❌ CAPACITÉ INSUFFISANTE")
        deficit = total_surveillances - total_capacity
        print(f"\nDéficit : {deficit} surveillances")
        return
    
    # 4. Analyser les contraintes qui peuvent causer l'infaisabilité
    
    # 4.1 Contrainte H2C : Responsables ne peuvent pas surveiller leur propre salle
    print("\n1️⃣  CONTRAINTE H2C : Responsable ne surveille pas sa propre salle")
    print("-" * 80)
    
    # Compter les responsables par créneau
    responsables_count = 0
    conflicts = []
    
    for _, creneau in creneaux.iterrows():
        date = creneau['date']
        heure = creneau['heure']
        
        # Salles de ce créneau
        salles_creneau = salles_df[
            (salles_df['dateExam'] == date) & 
            (salles_df['h_debut_parsed'] == heure)
        ]
        
        # Compter les responsables participants
        responsables_creneau = []
        for _, salle in salles_creneau.iterrows():
            resp = salle['enseignant']
            if pd.notna(resp):
                try:
                    resp_code = int(resp)
                    # Vérifier si le responsable participe
                    resp_info = enseignants_df[enseignants_df['code_smartex_ens'] == resp_code]
                    if len(resp_info) > 0 and resp_info.iloc[0]['participe_surveillance']:
                        responsables_creneau.append(resp_code)
                except:
                    pass
        
        nb_resp = len(responsables_creneau)
        nb_salles = len(salles_creneau)
        
        if nb_resp > 0:
            responsables_count += nb_resp
            # Chaque responsable ne peut surveiller que (nb_salles - 1) salles
            # Car il ne peut pas surveiller SA salle
            disponibilite_reduite = nb_resp  # Nombre de "slots" perdus
            
            if nb_resp > nb_salles / 2:  # Si plus de 50% sont responsables
                conflicts.append({
                    'date': date,
                    'heure': heure,
                    'nb_salles': nb_salles,
                    'nb_responsables': nb_resp,
                    'pct': nb_resp / nb_salles * 100
                })
    
    print(f"Nombre total de responsables participants : {responsables_count}")
    
    if conflicts:
        print(f"\n⚠️  ATTENTION : {len(conflicts)} créneaux avec forte concentration de responsables")
        print("\nCes créneaux peuvent causer des problèmes :")
        for c in conflicts[:5]:  # Top 5
            print(f"  • {c['date']} {c['heure']} : {c['nb_responsables']}/{c['nb_salles']} salles "
                  f"({c['pct']:.0f}% des salles ont leur responsable présent)")
    else:
        print("✅ Pas de conflits majeurs de responsables détectés")
    
    # 4.2 Contrainte H4 : Équité absolue par grade
    print("\n\n2️⃣  CONTRAINTE H4 : Équité ABSOLUE par grade")
    print("-" * 80)
    print("Avec quotas dynamiques, cette contrainte est TOUJOURS satisfaite")
    print("✅ Cette contrainte ne peut PAS causer d'infaisabilité")
    
    # 4.3 Contrainte H5 : Tous les enseignants ont au moins 1 affectation
    print("\n\n3️⃣  CONTRAINTE H5 : Tous les enseignants ont AU MOINS 1 surveillance")
    print("-" * 80)
    
    quota_moyen = total_surveillances / len(participants)
    print(f"Quota moyen nécessaire : {quota_moyen:.2f}")
    
    if quota_moyen < 1.0:
        print(f"✅ Quota moyen < 1 : Tous les enseignants PEUVENT avoir au moins 1 surveillance")
    elif quota_moyen > max(grades_dict.values()):
        print(f"❌ PROBLÈME : Quota moyen ({quota_moyen:.2f}) > quota maximum ({max(grades_dict.values())})")
        print("   → Certains enseignants ne pourront pas avoir au moins 1 surveillance")
    else:
        print(f"⚠️  Quota moyen proche de {quota_moyen:.2f}")
        print("   → L'équilibrage peut être difficile")
    
    # 4.4 Analyser les vœux
    print("\n\n4️⃣  VŒUX DE NON-SURVEILLANCE")
    print("-" * 80)
    
    voeux_file = 'test_files/Souhaits.csv'
    voeux_df = pd.read_csv(voeux_file)
    
    print(f"Nombre de lignes de vœux : {len(voeux_df)}")
    
    # Mapper les jours
    jour_mapping = {
        'Lundi': 1, 'Mardi': 2, 'Mercredi': 3,
        'Jeudi': 4, 'Vendredi': 5, 'Samedi': 6
    }
    
    # Mapper les dates aux jours
    dates_jours = {}
    for date in creneaux['date'].unique():
        # 27/10/2025 = Lundi, 28/10/2025 = Mardi, etc.
        day = int(date.split('/')[0])
        # Calculer le jour de la semaine (27/10/2025 est un lundi)
        jour_semaine = ((day - 27) % 7) + 1
        jour_name = {1: 'Lundi', 2: 'Mardi', 3: 'Mercredi', 4: 'Jeudi', 5: 'Vendredi', 6: 'Samedi'}
        dates_jours[date] = jour_name.get(jour_semaine, '')
    
    # Compter les vœux par créneau
    total_voeux = 0
    voeux_conflicts = []
    
    for _, creneau_row in creneaux.iterrows():
        date = creneau_row['date']
        heure = creneau_row['heure']
        nb_salles = creneau_row['nb_salles']
        nb_surveillants_necessaires = (nb_salles * 2) + 4
        
        jour = dates_jours.get(date, '')
        
        # Mapper l'heure à une séance
        seance_mapping = {
            '08:30': 'S1',
            '10:30': 'S2',
            '12:30': 'S3',
            '14:30': 'S4'
        }
        seance = seance_mapping.get(heure, '')
        
        # Compter les vœux pour ce créneau
        voeux_creneau = voeux_df[
            (voeux_df['Jour'] == jour) & 
            (voeux_df['Séances'].str.contains(seance, na=False))
        ]
        
        nb_voeux_creneau = len(voeux_creneau)
        total_voeux += nb_voeux_creneau
        
        # Calculer la disponibilité effective
        disponibilite_effective = len(participants) - nb_voeux_creneau
        
        if disponibilite_effective < nb_surveillants_necessaires:
            voeux_conflicts.append({
                'date': date,
                'heure': heure,
                'jour': jour,
                'seance': seance,
                'necessaire': nb_surveillants_necessaires,
                'voeux': nb_voeux_creneau,
                'disponible': disponibilite_effective,
                'deficit': nb_surveillants_necessaires - disponibilite_effective
            })
    
    print(f"Total de vœux (approximatif) : {total_voeux}")
    taux_voeux = (total_voeux / (len(participants) * len(creneaux))) * 100
    print(f"Taux de vœux : {taux_voeux:.1f}%")
    
    if voeux_conflicts:
        print(f"\n❌ PROBLÈME CRITIQUE : {len(voeux_conflicts)} créneaux avec trop de vœux!")
        print("\n⚠️  C'EST PROBABLEMENT LA CAUSE DE L'INFAISABILITÉ!")
        print("\nCréneaux problématiques :")
        print(f"{'Date':12s} {'Heure':8s} {'Jour':10s} {'Séance':8s} {'Nécess.':>8s} {'Vœux':>6s} {'Dispo':>6s} {'Déficit':>8s}")
        print("-" * 90)
        for c in voeux_conflicts[:10]:  # Top 10
            print(f"{c['date']:12s} {c['heure']:8s} {c['jour']:10s} {c['seance']:8s} "
                  f"{c['necessaire']:8d} {c['voeux']:6d} {c['disponible']:6d} {c['deficit']:8d}")
    else:
        print("✅ Les vœux ne causent pas de problème d'infaisabilité")
    
    # 5. CONCLUSION
    print("\n\n" + "="*80)
    print("🎯 CONCLUSION ET RECOMMANDATIONS")
    print("="*80)
    
    if voeux_conflicts:
        print("\n❌ CAUSE PRINCIPALE D'INFAISABILITÉ : VŒUX TROP NOMBREUX")
        print("\n💡 SOLUTIONS POSSIBLES :")
        print("   1. Réduire le nombre de vœux (demander aux enseignants d'être plus flexibles)")
        print("   2. Augmenter le nombre de réserves pour réduire les besoins par créneau")
        print("   3. Faire participer plus d'enseignants (activer participe_surveillance pour certains)")
        print("   4. Passer les vœux en contrainte SOFT uniquement (ils peuvent ne pas être respectés)")
    elif conflicts:
        print("\n⚠️  CAUSE PROBABLE : Contrainte H2C (responsables)")
        print("\n💡 SOLUTIONS POSSIBLES :")
        print("   1. Réduire le nombre de responsables participants")
        print("   2. Redistribuer les salles pour éviter trop de responsables par créneau")
    else:
        print("\n❓ CAUSE NON IDENTIFIÉE")
        print("\n💡 Pour plus d'informations :")
        print("   1. Lancer l'optimisation avec mode DEBUG")
        print("   2. Analyser le fichier RESULTAT_OPTIMISATION.txt")
        print("   3. Vérifier les logs du solver")
    
    conn.close()


if __name__ == '__main__':
    analyze_test_files()
