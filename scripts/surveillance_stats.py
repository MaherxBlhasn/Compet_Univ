#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module de statistiques pour optimize_example.py
Analyse : voeux, dispersion, responsables, équité, couverture, charges
"""

import pandas as pd
import numpy as np
from collections import defaultdict


def parse_time(time_str):
    """Parse une heure au format 'HH:MM:SS' ou 'DD/MM/YYYY HH:MM:SS'"""
    if pd.isna(time_str):
        return None
    time_str = str(time_str)
    if ' ' in time_str:
        return time_str.split(' ')[1][:5]
    return time_str[:5]


class SurveillanceStatistics:
    """Classe pour calculer les statistiques d'optimisation"""
    
    def __init__(self, affectations, creneaux, teachers, voeux_set, planning_df):
        """
        Args:
            affectations : list de dicts (résultat de assign_rooms_equitable)
            creneaux : dict des creneaux
            teachers : dict des enseignants
            voeux_set : set des voeux (tcode, jour, seance)
            planning_df : DataFrame du planning original
        """
        self.aff = pd.DataFrame(affectations)
        self.creneaux = creneaux
        self.teachers = teachers
        self.voeux_set = voeux_set
        self.planning_df = planning_df
        self.stats = {}
    
    def compute_all_stats(self):
        """Calculer toutes les statistiques"""
        print("\n" + "="*70)
        print("ANALYSE STATISTIQUE DE LA SOLUTION D'OPTIMISATION")
        print("="*70)
        
        self.stats['voeux'] = self._compute_voeux_stats()
        self.stats['dispersion'] = self._compute_dispersion_stats()
        self.stats['responsables'] = self._compute_responsable_stats()
        self.stats['equite'] = self._compute_equite_stats()
        self.stats['couverture'] = self._compute_couverture_stats()
        self.stats['charges'] = self._compute_charge_stats()
        
        self._print_summary()
        
        return self.stats
    
    def _compute_voeux_stats(self):
        """Analyser le respect des voeux de non-surveillance"""
        print("\n[1] VOEUX DE NON-SURVEILLANCE")
        
        total_voeux = len(self.voeux_set)
        voeux_respectes = 0
        voeux_violes = []
        
        for (tcode, jour, seance) in self.voeux_set:
            matching = self.aff[
                (self.aff['code_smartex_ens'] == tcode) &
                (self.aff['jour'] == jour) &
                (self.aff['seance'] == seance)
            ]
            
            if len(matching) == 0:
                voeux_respectes += 1
            else:
                voeux_violes.append({
                    'code': tcode,
                    'jour': jour,
                    'seance': seance,
                    'nb': len(matching)
                })
        
        taux = (voeux_respectes / total_voeux * 100) if total_voeux > 0 else 0
        
        print(f"    Voeux totaux : {total_voeux}")
        print(f"    Respectés : {voeux_respectes} ({taux:.1f}%)")
        print(f"    Violés : {len(voeux_violes)} ({100-taux:.1f}%)")
        
        if voeux_violes and len(voeux_violes) <= 3:
            for v in voeux_violes:
                print(f"      ⚠ Code {v['code']} : jour {v['jour']} {v['seance']}")
        
        return {
            'total': total_voeux,
            'respectes': voeux_respectes,
            'violes': len(voeux_violes),
            'taux_respect': taux
        }
    
    def _compute_dispersion_stats(self):
        """Analyser la dispersion des surveillances dans la même journée"""
        print("\n[2] DISPERSION DANS LA JOURNÉE")
        
        profs_with_multiple = 0
        consecutives = 0
        espacees = 0
        
        for tcode in self.aff['code_smartex_ens'].unique():
            prof_aff = self.aff[self.aff['code_smartex_ens'] == tcode]
            
            for jour in prof_aff['jour'].unique():
                jour_aff = prof_aff[prof_aff['jour'] == jour]
                
                if len(jour_aff) <= 1:
                    continue
                
                profs_with_multiple += 1
                
                seances = []
                for _, row in jour_aff.iterrows():
                    seance_str = str(row['seance']).upper()
                    if seance_str.startswith('S'):
                        try:
                            seance_num = int(seance_str[1:])
                            seances.append(seance_num)
                        except:
                            pass
                
                if len(seances) > 1:
                    seances_sorted = sorted(set(seances))
                    gaps = [seances_sorted[i+1] - seances_sorted[i] 
                           for i in range(len(seances_sorted)-1)]
                    min_gap = min(gaps)
                    
                    if min_gap == 1:
                        consecutives += 1
                    else:
                        espacees += 1
        
        print(f"    Enseignants avec plusieurs séances/jour : {profs_with_multiple}")
        print(f"      - Séances consécutives : {consecutives}")
        print(f"      - Séances espacées : {espacees}")
        
        return {
            'total_multi': profs_with_multiple,
            'consecutives': consecutives,
            'espacees': espacees
        }
    
    def _compute_responsable_stats(self):
        """Analyser la disponibilité des responsables"""
        print("\n[3] RESPONSABLES DE SALLES")
        
        # Total d'enseignants avec participe_surveillance=1
        total_enseignants_surveillants = sum(1 for t in self.teachers.values() if t['participe'])
        
        planning_df_copy = self.planning_df.copy()
        planning_df_copy['h_debut_parsed'] = planning_df_copy['h_debut'].apply(parse_time)
        
        # Collecter les responsables par date (enseignants uniques)
        responsables_par_date = defaultdict(set)
        for _, row in planning_df_copy.iterrows():
            date = row['dateExam']
            responsable = row['enseignant']
            
            if pd.notna(date) and pd.notna(responsable):
                try:
                    responsable = int(responsable)
                    # Vérifier que le responsable participe aux surveillances
                    if responsable in self.teachers and self.teachers[responsable]['participe']:
                        responsables_par_date[date].add(responsable)
                except (ValueError, TypeError):
                    continue
        
        # Vérifier pour chaque responsable s'il est présent le jour de son examen
        responsables_absents = set()
        
        for date, responsables in responsables_par_date.items():
            for resp_code in responsables:
                # Vérifier si le responsable est affecté à une surveillance CE JOUR
                matching = self.aff[
                    (self.aff['code_smartex_ens'] == resp_code) &
                    (self.aff['date'] == date)
                ]
                
                # Si aucune affectation ce jour = absent
                if len(matching) == 0:
                    responsables_absents.add(resp_code)
        
        nb_responsables_absents = len(responsables_absents)
        nb_responsables_presents = total_enseignants_surveillants - nb_responsables_absents
        taux = (nb_responsables_presents / total_enseignants_surveillants * 100) if total_enseignants_surveillants > 0 else 0
        
        print(f"    Total enseignants surveillants (participe_surveillance=1) : {total_enseignants_surveillants}")
        print(f"    Responsables absents le jour de leur examen : {nb_responsables_absents}")
        print(f"    Responsables présents : {nb_responsables_presents} ({taux:.1f}%)")
        
        return {
            'total': total_enseignants_surveillants,
            'presents': nb_responsables_presents,
            'absents': nb_responsables_absents,
            'taux_presence': taux
        }
    
    def _compute_equite_stats(self):
        """Analyser l'équité par grade"""
        print("\n[4] ÉQUITÉ PAR GRADE")
        
        teachers_by_grade = defaultdict(list)
        for tcode, t in self.teachers.items():
            if t['participe']:
                teachers_by_grade[t['grade']].append(tcode)
        
        equite_parfaite_count = 0
        total_grades = len(teachers_by_grade)
        
        for grade in sorted(teachers_by_grade.keys()):
            tcodes = teachers_by_grade[grade]
            
            charges = {}
            for tcode in tcodes:
                count = len(self.aff[self.aff['code_smartex_ens'] == tcode])
                charges[tcode] = count
            
            if charges:
                min_charge = min(charges.values())
                max_charge = max(charges.values())
                ecart = max_charge - min_charge
                
                if ecart <= 1:
                    equite_parfaite_count += 1
                    status = "✓"
                else:
                    status = "⚠"
                
                print(f"    {status} Grade {grade:3s} ({len(tcodes):2d} prof) : "
                      f"min={min_charge} max={max_charge} écart={ecart}")
        
        print(f"    → {equite_parfaite_count}/{total_grades} grades en équité parfaite")
        
        return {
            'grades_equitables': equite_parfaite_count,
            'total_grades': total_grades,
            'taux_equite': 100 * equite_parfaite_count / total_grades if total_grades > 0 else 0
        }
    
    def _compute_couverture_stats(self):
        """Analyser la couverture des créneaux - toutes les salles doivent avoir minimum 2 surveillants"""
        print("\n[5] COUVERTURE DES CRENEAUX")
        
        # Regrouper les affectations par créneau et salle
        couverture_par_salle = defaultdict(lambda: defaultdict(int))
        
        for _, aff in self.aff.iterrows():
            cid = aff.get('creneau_id')
            salle = aff.get('cod_salle')  # Utiliser 'cod_salle' au lieu de 'salle'
            if pd.notna(cid) and pd.notna(salle):
                couverture_par_salle[cid][salle] += 1
        
        total_salles = 0
        salles_bien_couvertes = 0  # >= 2 surveillants
        salles_sous_couvertes = 0  # < 2 surveillants
        
        for cid in couverture_par_salle:
            for salle, nb_surveillants in couverture_par_salle[cid].items():
                total_salles += 1
                if nb_surveillants >= 2:
                    salles_bien_couvertes += 1
                else:
                    salles_sous_couvertes += 1
        
        taux = (salles_bien_couvertes / total_salles * 100) if total_salles > 0 else 0
        
        print(f"    Salles totales : {total_salles}")
        print(f"    Salles avec >= 2 surveillants : {salles_bien_couvertes} ({taux:.1f}%)")
        print(f"    Salles avec < 2 surveillants : {salles_sous_couvertes}")
        
        return {
            'total': total_salles,
            'bien_couvertes': salles_bien_couvertes,
            'sous_couvertes': salles_sous_couvertes,
            'taux_couverture': taux
        }
    
    def _compute_charge_stats(self):
        """Analyser la distribution des charges"""
        print("\n[6] DISTRIBUTION DES CHARGES")
        
        charges_by_grade = defaultdict(list)
        
        for tcode, t in self.teachers.items():
            if not t['participe']:
                continue
            
            count = len(self.aff[self.aff['code_smartex_ens'] == tcode])
            charges_by_grade[t['grade']].append(count)
        
        profs_zero = 0
        profs_total = 0
        
        for grade in sorted(charges_by_grade.keys()):
            charges = charges_by_grade[grade]
            profs_total += len(charges)
            profs_zero += sum(1 for c in charges if c == 0)
            
            if charges:
                print(f"    {grade} ({len(charges):2d} prof) : "
                      f"total={sum(charges):3d} moy={np.mean(charges):4.1f} "
                      f"min-max={min(charges)}-{max(charges)}")
        
        print(f"    → {profs_zero}/{profs_total} enseignants sans affectation")
        
        return {
            'sans_affectation': profs_zero,
            'total_enseignants': profs_total
        }
    
    def _print_summary(self):
        """Afficher le résumé global"""
        print("\n" + "="*70)
        print("RÉSUMÉ GLOBAL")
        print("="*70)
        
        voeux = self.stats['voeux']
        disp = self.stats['dispersion']
        resp = self.stats['responsables']
        equite = self.stats['equite']
        couv = self.stats['couverture']
        
        print(f"\n✓ VOEUX         : {voeux['taux_respect']:5.1f}% ({voeux['respectes']}/{voeux['total']})")
        print(f"✓ DISPERSION    : {disp['espacees']:3d} prof espacées / "
              f"{disp['consecutives']:3d} consécutives")
        print(f"✓ RESPONSABLES  : {resp['taux_presence']:5.1f}% présents le jour de l'examen "
              f"({resp['presents']}/{resp['total']} avec participe=1)")
        print(f"✓ ÉQUITÉ        : {equite['taux_equite']:5.1f}% "
              f"({equite['grades_equitables']}/{equite['total_grades']} grades)")
        print(f"✓ COUVERTURE    : {couv['taux_couverture']:5.1f}% "
              f"({couv['bien_couvertes']}/{couv['total']} salles avec >=2 surveillants)")
        
        print("\n" + "="*70 + "\n")


def generate_statistics(affectations, creneaux, teachers, voeux_set, planning_df):
    """Fonction wrapper pour générer les statistiques"""
    stats = SurveillanceStatistics(affectations, creneaux, teachers, voeux_set, planning_df)
    return stats.compute_all_stats()