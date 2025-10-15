#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Script de diagnostic pour identifier les problèmes d'infaisabilité
"""

import sqlite3
import pandas as pd

DB_NAME = 'surveillance.db'

def parse_time(time_str):
    """Parse une heure"""
    if pd.isna(time_str):
        return None
    time_str = str(time_str)
    if ' ' in time_str:
        return time_str.split(' ')[1][:5]
    return time_str[:5]

def diagnostic_h2c_h2d():
    """Diagnostiquer les conflits entre H2C et H2D"""
    
    print("\n" + "="*80)
    print("DIAGNOSTIC DES CONFLITS H2C / H2D")
    print("="*80)
    
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    
    # Charger les données
    planning_df = pd.read_sql_query("""
        SELECT 
            creneau_id,
            dateExam,
            h_debut,
            h_fin,
            enseignant,
            cod_salle
        FROM creneau
        WHERE id_session = 1
    """, conn)
    
    enseignants_df = pd.read_sql_query("""
        SELECT 
            e.code_smartex_ens,
            e.nom_ens,
            e.prenom_ens,
            e.participe_surveillance
        FROM enseignant e
    """, conn)
    
    conn.close()
    
    # Identifier les enseignants participants
    participants = set(enseignants_df[enseignants_df['participe_surveillance'] == 1]['code_smartex_ens'].tolist())
    
    # Parser les heures
    planning_df['h_debut_parsed'] = planning_df['h_debut'].apply(parse_time)
    
    # Grouper par créneau (date + heure)
    creneau_groups = planning_df.groupby(['dateExam', 'h_debut_parsed'])
    
    print("\n📊 ANALYSE PAR CRÉNEAU\n")
    
    problemes = []
    total_creneaux = 0
    
    for (date, heure), group in creneau_groups:
        total_creneaux += 1
        creneau_id = f"{date}_{heure}"
        nb_salles = len(group)
        
        # Identifier les responsables de ce créneau
        responsables = []
        for _, row in group.iterrows():
            resp = row['enseignant']
            if pd.notna(resp):
                try:
                    resp = int(resp)
                    if resp in participants:
                        responsables.append({
                            'code': resp,
                            'salle': row['cod_salle']
                        })
                except:
                    pass
        
        # Pour chaque responsable, vérifier s'il peut surveiller une autre salle
        for resp_info in responsables:
            resp_code = resp_info['code']
            sa_salle = resp_info['salle']
            
            # Compter les autres salles qu'il peut surveiller (toutes sauf la sienne)
            autres_salles = [s for s in group['cod_salle'].tolist() if s != sa_salle]
            
            if len(autres_salles) == 0:
                # PROBLÈME CRITIQUE : Le responsable n'a aucune autre salle disponible !
                ens_info = enseignants_df[enseignants_df['code_smartex_ens'] == resp_code]
                if not ens_info.empty:
                    nom = ens_info.iloc[0]['nom_ens']
                    prenom = ens_info.iloc[0]['prenom_ens']
                else:
                    nom, prenom = "Inconnu", ""
                
                problemes.append({
                    'creneau': creneau_id,
                    'date': date,
                    'heure': heure,
                    'responsable_code': resp_code,
                    'responsable_nom': f"{nom} {prenom}",
                    'sa_salle': sa_salle,
                    'nb_salles_total': nb_salles,
                    'nb_autres_salles': 0
                })
                
                print(f"❌ CONFLIT DÉTECTÉ :")
                print(f"   Créneau : {date} à {heure}")
                print(f"   Responsable : {nom} {prenom} (code {resp_code})")
                print(f"   Sa salle : {sa_salle}")
                print(f"   Nombre total de salles : {nb_salles}")
                print(f"   ⚠️  PROBLÈME : Ce créneau n'a qu'UNE SEULE salle !")
                print(f"   → H2C : Il ne peut PAS surveiller {sa_salle} (sa salle)")
                print(f"   → H2D : Il DOIT surveiller au moins une salle du créneau")
                print(f"   → IMPOSSIBLE à satisfaire !\n")
    
    print("="*80)
    print(f"\n📈 RÉSUMÉ DU DIAGNOSTIC")
    print(f"   Total de créneaux analysés : {total_creneaux}")
    print(f"   Conflits H2C/H2D détectés : {len(problemes)}")
    
    if problemes:
        print(f"\n   ❌ Le problème est INFAISABLE à cause de ces {len(problemes)} conflit(s)")
        print(f"\n💡 SOLUTIONS POSSIBLES :")
        print(f"   1. Assouplir H2D : Un responsable peut être ABSENT si son créneau n'a qu'une salle")
        print(f"   2. Autoriser exceptionnellement un responsable à surveiller sa salle si pas d'autre choix")
        print(f"   3. Ajouter des salles supplémentaires aux créneaux problématiques")
        print(f"   4. Retirer la contrainte H2D complètement")
    else:
        print(f"\n   ✅ Aucun conflit détecté - le problème devrait être faisable")
    
    print("="*80 + "\n")
    
    return problemes


def analyse_capacite():
    """Analyser si on a assez d'enseignants pour couvrir tous les créneaux"""
    
    print("\n" + "="*80)
    print("ANALYSE DE CAPACITÉ")
    print("="*80)
    
    conn = sqlite3.connect(DB_NAME)
    
    # Nombre d'enseignants participants
    nb_participants = pd.read_sql_query("""
        SELECT COUNT(*) as nb
        FROM enseignant
        WHERE participe_surveillance = 1
    """, conn).iloc[0]['nb']
    
    # Charger salle_par_creneau
    salle_par_creneau = pd.read_sql_query("""
        SELECT dateExam, h_debut, nb_salle
        FROM salle_par_creneau
        WHERE id_session = 1
    """, conn)
    
    conn.close()
    
    # Calculer les besoins par créneau
    salle_par_creneau['nb_surveillants'] = salle_par_creneau['nb_salle'] * 2 + 4
    
    print(f"\n📊 STATISTIQUES GLOBALES")
    print(f"   Enseignants participants : {nb_participants}")
    print(f"   Nombre de créneaux : {len(salle_par_creneau)}")
    print(f"\n📋 BESOINS PAR CRÉNEAU :")
    
    for _, row in salle_par_creneau.iterrows():
        date = row['dateExam']
        heure = parse_time(row['h_debut'])
        nb_salles = row['nb_salle']
        nb_surv = row['nb_surveillants']
        
        print(f"   {date} {heure} : {nb_salles} salles → {nb_surv} surveillants requis")
        
        if nb_surv > nb_participants:
            print(f"      ⚠️  ATTENTION : Plus de surveillants requis que d'enseignants disponibles !")
    
    total_besoins = salle_par_creneau['nb_surveillants'].sum()
    print(f"\n   Total surveillances requises : {total_besoins}")
    print(f"   Si équitablement réparti : {total_besoins / nb_participants:.1f} surveillances par enseignant")
    
    print("="*80 + "\n")


if __name__ == "__main__":
    # Diagnostic principal
    problemes = diagnostic_h2c_h2d()
    
    # Analyse de capacité
    analyse_capacite()
    
    # Conclusion
    if problemes:
        print("\n" + "="*80)
        print("⚠️  CONCLUSION : Problème INFAISABLE")
        print("="*80)
        print("\nLe modèle actuel ne peut pas trouver de solution car certains responsables")
        print("sont dans des créneaux avec une seule salle (la leur).")
        print("\nChoisissez une solution parmi les options proposées ci-dessus.")
        print("="*80 + "\n")
    else:
        print("\n✅ Le problème devrait être faisable avec les contraintes actuelles.\n")