"""
Module d'aide à la décision pour l'affectation des surveillances
=================================================================

Ce module calcule automatiquement :
1. Le nombre de surveillances nécessaires par grade (avec majoration pour absences)
2. Le nombre de créneaux de non-souhaits autorisés par grade
3. Des propositions de quotas par enseignant

Règles de répartition des surveillances :
- Professeur (PR), Maître de conférences (MC), Vacataire (V) : même nombre
- Maître assistant (MA) : supérieur à PR/MC/V mais inférieur à Assistant (AS)
- Assistant contractuel (AC), PTC, PES : supérieur à Assistant (AS)
- Différence minimale configurable (Expert = 3)

Usage:
    from scripts.decision_support_module import DecisionSupportModule
    
    dsm = DecisionSupportModule(session_id=1)
    recommendations = dsm.generate_recommendations()
    dsm.save_recommendations(recommendations)
"""

import sqlite3
import pandas as pd
from typing import Dict, List, Tuple, Optional
from database.database import get_db
import math


class DecisionSupportModule:
    """
    Module d'aide à la décision pour calculer les quotas optimaux
    et les non-souhaits autorisés par grade
    """
    
    # Hiérarchie des grades (du plus bas au plus haut)
    GRADE_HIERARCHY = {
        'PR': 1,   # Professeur
        'MC': 1,   # Maître de conférences
        'V': 1,    # Vacataire
        'MA': 2,   # Maître assistant
        'AS': 3,   # Assistant
        'AC': 4,   # Assistant contractuel
        'PTC': 4,  # PTC
        'PES': 4,  # PES
        'Expert': 5  # Expert (si applicable)
    }
    
    def __init__(self, session_id: int, db_conn=None):
        """
        Initialiser le module
        
        Args:
            session_id: ID de la session
            db_conn: Connexion à la base de données (optionnel)
        """
        self.session_id = session_id
        self.db = db_conn if db_conn else get_db()
        
        # Paramètres configurables
        self.absence_margin = 0.15  # 15% de marge pour absences potentielles
        self.min_difference_between_levels = 3  # Différence minimale entre niveaux (Expert)
        self.max_non_souhaits_ratio = 0.30  # Maximum 30% de non-souhaits
    
    def load_session_data(self) -> Dict:
        """
        Charger les données de la session
        
        Returns:
            Dictionnaire avec enseignants_df, planning_df, salles_df, etc.
        """
        # Charger les enseignants
        enseignants_query = """
            SELECT 
                code_smartex_ens,
                nom_ens,
                prenom_ens,
                grade_code_ens,
                email_ens
            FROM enseignant
        """
        enseignants_df = pd.read_sql_query(enseignants_query, self.db)
        
        # Charger les créneaux
        creneaux_query = """
            SELECT 
                creneau_id,
                id_session,
                dateExam,
                h_debut,
                h_fin,
                enseignant as code_smartex_resp,
                cod_salle
            FROM creneau
            WHERE id_session = ?
        """
        creneaux_df = pd.read_sql_query(creneaux_query, self.db, params=(self.session_id,))
        
        # Charger les salles par créneau (depuis salle_par_creneau si existe, sinon depuis creneau)
        try:
            salles_creneau_query = """
                SELECT 
                    creneau_id,
                    code_salle,
                    nb_surveillants
                FROM salle_par_creneau
                WHERE creneau_id IN (
                    SELECT creneau_id FROM creneau WHERE id_session = ?
                )
            """
            salles_creneau_df = pd.read_sql_query(salles_creneau_query, self.db, params=(self.session_id,))
        except:
            # Si la table n'existe pas, créer à partir de creneau
            salles_creneau_df = creneaux_df[['creneau_id', 'cod_salle']].copy()
            salles_creneau_df.columns = ['creneau_id', 'code_salle']
            salles_creneau_df['nb_surveillants'] = 2  # Par défaut 2 surveillants par salle
        
        # Charger les salles
        salles_query = """
            SELECT 
                code_salle,
                capacite_salle,
                type_salle
            FROM salle
        """
        try:
            salles_df = pd.read_sql_query(salles_query, self.db)
        except:
            salles_df = pd.DataFrame()  # Si pas de table salle
        
        # Charger les voeux existants
        voeux_query = """
            SELECT 
                code_smartex_ens,
                id_session,
                jour,
                seance
            FROM voeu
            WHERE id_session = ?
        """
        voeux_df = pd.read_sql_query(voeux_query, self.db, params=(self.session_id,))
        
        return {
            'enseignants_df': enseignants_df,
            'creneaux_df': creneaux_df,
            'salles_creneau_df': salles_creneau_df,
            'salles_df': salles_df,
            'voeux_df': voeux_df
        }
    
    def calculate_required_surveillances(self, salles_creneau_df: pd.DataFrame) -> Tuple[int, int]:
        """
        Calculer le nombre total de surveillances nécessaires
        
        Args:
            salles_creneau_df: DataFrame des salles par créneau
        
        Returns:
            (surveillances_base, surveillances_avec_marge)
        """
        # Compter le nombre total de surveillances nécessaires
        # (somme de nb_surveillants pour toutes les salles de tous les créneaux)
        surveillances_base = int(salles_creneau_df['nb_surveillants'].sum())
        
        # Ajouter une marge pour les absences potentielles
        surveillances_avec_marge = math.ceil(surveillances_base * (1 + self.absence_margin))
        
        nb_creneaux = salles_creneau_df['creneau_id'].nunique()
        nb_salles = len(salles_creneau_df)
        
        print(f"\n📊 Calcul des surveillances nécessaires:")
        print(f"   - Nombre de créneaux: {nb_creneaux}")
        print(f"   - Nombre de salles: {nb_salles}")
        print(f"   - Surveillances de base: {surveillances_base}")
        print(f"   - Marge pour absences ({self.absence_margin*100}%): +{surveillances_avec_marge - surveillances_base}")
        print(f"   - Total avec marge: {surveillances_avec_marge}")
        
        return surveillances_base, surveillances_avec_marge
    
    def calculate_quotas_by_grade(self, enseignants_df: pd.DataFrame, 
                                   total_surveillances: int) -> Dict[str, Dict]:
        """
        Calculer les quotas par grade selon la hiérarchie
        
        Args:
            enseignants_df: DataFrame des enseignants
            total_surveillances: Nombre total de surveillances nécessaires
        
        Returns:
            Dictionnaire {grade: {quota, nb_enseignants, total_capacity}}
        """
        # Compter les enseignants par grade
        grade_counts = enseignants_df['grade_code_ens'].value_counts().to_dict()
        
        # Organiser les grades par niveau hiérarchique
        grades_by_level = {}
        for grade in grade_counts.keys():
            level = self.GRADE_HIERARCHY.get(grade, 3)  # Niveau 3 par défaut
            if level not in grades_by_level:
                grades_by_level[level] = []
            grades_by_level[level].append(grade)
        
        print(f"\n📋 Répartition des enseignants par niveau:")
        for level in sorted(grades_by_level.keys()):
            grades = grades_by_level[level]
            total = sum(grade_counts[g] for g in grades)
            print(f"   Niveau {level} ({', '.join(grades)}): {total} enseignants")
        
        # Calculer les quotas par niveau
        # Niveau le plus bas commence avec quota_base
        # Chaque niveau supérieur ajoute min_difference_between_levels
        
        # Trouver le quota de base pour le niveau 1
        total_enseignants = sum(grade_counts.values())
        
        # Calculer la somme pondérée : sum(nb_ens[level] * (quota_base + (level-1) * diff))
        # = quota_base * total_ens + diff * sum(nb_ens[level] * (level-1))
        
        weighted_sum = 0
        for level, grades in grades_by_level.items():
            nb_ens_level = sum(grade_counts[g] for g in grades)
            weighted_sum += nb_ens_level * (level - 1)
        
        # Résoudre: total_surveillances = quota_base * total_ens + diff * weighted_sum
        quota_base = (total_surveillances - self.min_difference_between_levels * weighted_sum) / total_enseignants
        quota_base = max(1, math.floor(quota_base))  # Au minimum 1
        
        print(f"\n🎯 Calcul des quotas:")
        print(f"   - Quota de base (niveau 1): {quota_base}")
        print(f"   - Différence entre niveaux: {self.min_difference_between_levels}")
        
        # Calculer les quotas par grade
        quotas = {}
        total_capacity = 0
        
        for grade, count in grade_counts.items():
            level = self.GRADE_HIERARCHY.get(grade, 3)
            quota = quota_base + (level - 1) * self.min_difference_between_levels
            capacity = quota * count
            total_capacity += capacity
            
            quotas[grade] = {
                'quota': quota,
                'nb_enseignants': count,
                'total_capacity': capacity,
                'level': level
            }
            
            print(f"   - {grade} (niveau {level}): {quota} surveillances × {count} enseignants = {capacity}")
        
        print(f"\n   📦 Capacité totale: {total_capacity}")
        print(f"   🎯 Surveillances requises: {total_surveillances}")
        
        if total_capacity < total_surveillances:
            print(f"   ⚠️ ATTENTION: Capacité insuffisante! Déficit: {total_surveillances - total_capacity}")
            # Ajuster les quotas si capacité insuffisante
            quotas = self._adjust_quotas_for_capacity(quotas, total_surveillances, grade_counts)
        else:
            print(f"   ✅ Capacité suffisante! Excédent: {total_capacity - total_surveillances}")
        
        return quotas
    
    def _adjust_quotas_for_capacity(self, quotas: Dict, required: int, 
                                     grade_counts: Dict) -> Dict:
        """
        Ajuster les quotas si la capacité totale est insuffisante
        
        Args:
            quotas: Quotas actuels par grade
            required: Nombre de surveillances requises
            grade_counts: Nombre d'enseignants par grade
        
        Returns:
            Quotas ajustés
        """
        print(f"\n🔧 Ajustement des quotas pour atteindre la capacité requise...")
        
        # Calculer le facteur d'augmentation nécessaire
        current_capacity = sum(q['total_capacity'] for q in quotas.values())
        factor = required / current_capacity
        
        new_quotas = {}
        new_capacity = 0
        
        for grade, data in quotas.items():
            new_quota = math.ceil(data['quota'] * factor)
            capacity = new_quota * data['nb_enseignants']
            new_capacity += capacity
            
            new_quotas[grade] = {
                'quota': new_quota,
                'nb_enseignants': data['nb_enseignants'],
                'total_capacity': capacity,
                'level': data['level']
            }
            
            print(f"   - {grade}: {data['quota']} → {new_quota} (+{new_quota - data['quota']})")
        
        print(f"   📦 Nouvelle capacité: {new_capacity} (objectif: {required})")
        
        return new_quotas
    
    def calculate_max_voeux_allowance(self, enseignants_df: pd.DataFrame,
                                       creneaux_df: pd.DataFrame,
                                       voeux_df: pd.DataFrame,
                                       quotas: Dict) -> Dict[str, int]:
        """
        Calculer le nombre MAXIMUM de voeux (souhaits de surveillance) autorisés par grade
        
        Logique: Un enseignant doit avoir suffisamment de créneaux disponibles (non souhaités)
        pour garantir qu'on puisse lui affecter son quota de surveillances.
        
        Formule: max_voeux = nb_creneaux_total - quota - marge_securite
        
        Plus le quota est élevé, MOINS de voeux autorisés (besoin de plus de disponibilité)
        
        Args:
            enseignants_df: DataFrame des enseignants
            creneaux_df: DataFrame des créneaux
            voeux_df: DataFrame des voeux
            quotas: Quotas calculés par grade
        
        Returns:
            Dictionnaire {grade: nb_max_voeux_autorises}
        """
        nb_creneaux = len(creneaux_df)
        
        print(f"\n� Calcul du nombre MAXIMUM de voeux autorisés par grade:")
        print(f"   - Nombre total de créneaux: {nb_creneaux}")
        print(f"   - Logique: Plus le quota est élevé, moins de voeux autorisés")
        print(f"   - Formule: max_voeux = nb_creneaux - quota - marge_sécurité")
        
        max_voeux_allowance = {}
        
        for grade, data in quotas.items():
            quota = data['quota']
            
            # Calcul de la marge de sécurité (fonction du quota)
            # Plus le quota est élevé, plus on a besoin de marge
            # Marge = quota × 0.5 (50% du quota) pour éviter les conflits
            marge_securite = math.ceil(quota * 0.5)
            
            # Maximum de voeux = créneaux totaux - quota obligatoire - marge
            max_voeux = nb_creneaux - quota - marge_securite
            
            # S'assurer qu'on a au moins un minimum raisonnable de voeux possibles
            # Au minimum, permettre de souhaiter la moitié des créneaux
            min_voeux = math.floor(nb_creneaux * 0.5)
            max_voeux = min(max_voeux, max(min_voeux, nb_creneaux - quota - 1))
            
            # Pourcentage de créneaux souhaitables
            pct_souhaitables = (max_voeux / nb_creneaux) * 100
            
            max_voeux_allowance[grade] = max_voeux
            
            print(f"   - {grade} (quota={quota}):")
            print(f"      * Marge de sécurité: {marge_securite} créneaux")
            print(f"      * MAX voeux autorisés: {max_voeux} créneaux ({pct_souhaitables:.1f}% des créneaux)")
            print(f"      * Créneaux disponibles minimum: {nb_creneaux - max_voeux} (dont {quota} pour surveillances)")
        
        return max_voeux_allowance
    
    def generate_individual_quotas(self, enseignants_df: pd.DataFrame,
                                    quotas_by_grade: Dict) -> pd.DataFrame:
        """
        Générer les quotas individuels par enseignant
        
        Args:
            enseignants_df: DataFrame des enseignants
            quotas_by_grade: Quotas par grade
        
        Returns:
            DataFrame avec code_smartex_ens, nom, prenom, grade, quota_propose
        """
        quotas_list = []
        
        for _, row in enseignants_df.iterrows():
            grade = row['grade_code_ens']
            quota_grade = quotas_by_grade.get(grade, {}).get('quota', 0)
            
            quotas_list.append({
                'code_smartex_ens': row['code_smartex_ens'],
                'nom_ens': row['nom_ens'],
                'prenom_ens': row['prenom_ens'],
                'email_ens': row['email_ens'],
                'grade_code_ens': grade,
                'quota_propose': quota_grade
            })
        
        return pd.DataFrame(quotas_list)
    
    def generate_recommendations(self) -> Dict:
        """
        Générer toutes les recommandations du module d'aide à la décision
        
        Returns:
            Dictionnaire complet avec toutes les recommandations
        """
        print("\n" + "="*70)
        print("MODULE D'AIDE À LA DÉCISION - SESSION", self.session_id)
        print("="*70)
        
        # 1. Charger les données
        print("\n1️⃣ Chargement des données...")
        data = self.load_session_data()
        
        enseignants_df = data['enseignants_df']
        creneaux_df = data['creneaux_df']
        salles_creneau_df = data['salles_creneau_df']
        voeux_df = data['voeux_df']
        
        print(f"   ✅ {len(enseignants_df)} enseignants disponibles")
        print(f"   ✅ {len(creneaux_df)} créneaux")
        print(f"   ✅ {len(salles_creneau_df)} salles à surveiller")
        print(f"   ✅ {len(voeux_df)} voeux enregistrés")
        
        # 2. Calculer les surveillances nécessaires
        print("\n2️⃣ Calcul des surveillances nécessaires...")
        surveillances_base, surveillances_totales = self.calculate_required_surveillances(
            salles_creneau_df
        )
        
        # 3. Calculer les quotas par grade
        print("\n3️⃣ Calcul des quotas par grade...")
        quotas_by_grade = self.calculate_quotas_by_grade(
            enseignants_df, surveillances_totales
        )
        
        # 4. Calculer les voeux maximum autorisés
        print("\n4️⃣ Calcul du nombre MAXIMUM de voeux autorisés...")
        max_voeux_allowance = self.calculate_max_voeux_allowance(
            enseignants_df, creneaux_df, voeux_df, quotas_by_grade
        )
        
        # 5. Générer les quotas individuels
        print("\n5️⃣ Génération des quotas individuels...")
        individual_quotas_df = self.generate_individual_quotas(
            enseignants_df, quotas_by_grade
        )
        print(f"   ✅ {len(individual_quotas_df)} quotas individuels générés")
        
        # Résumé final
        print("\n" + "="*70)
        print("RÉSUMÉ DES RECOMMANDATIONS")
        print("="*70)
        print(f"\n📊 Surveillances:")
        print(f"   - Base (sans marge): {surveillances_base}")
        print(f"   - Total avec marge: {surveillances_totales}")
        
        print(f"\n📋 Quotas par grade:")
        for grade in sorted(quotas_by_grade.keys(), 
                           key=lambda g: quotas_by_grade[g]['level']):
            data = quotas_by_grade[grade]
            print(f"   - {grade}: {data['quota']} surveillances × {data['nb_enseignants']} ens = {data['total_capacity']}")
        
        print(f"\n🎲 Voeux MAXIMUM autorisés par grade:")
        for grade, allowed in max_voeux_allowance.items():
            print(f"   - {grade}: {allowed} créneaux")
        
        print("\n" + "="*70)
        
        return {
            'session_id': self.session_id,
            'surveillances_base': surveillances_base,
            'surveillances_totales': surveillances_totales,
            'quotas_by_grade': quotas_by_grade,
            'max_voeux_allowance': max_voeux_allowance,
            'individual_quotas': individual_quotas_df,
            'nb_enseignants': len(enseignants_df),
            'nb_creneaux': len(creneaux_df),
            'parameters': {
                'absence_margin': self.absence_margin,
                'min_difference_between_levels': self.min_difference_between_levels,
                'max_voeux_ratio': 1.0 - self.max_non_souhaits_ratio  # Inverse
            }
        }
    
    def save_recommendations(self, recommendations: Dict, 
                            update_grade_table: bool = True,
                            export_csv: bool = True) -> Dict[str, bool]:
        """
        Sauvegarder les recommandations dans la base de données
        
        Args:
            recommendations: Recommandations générées
            update_grade_table: Mettre à jour la table grade avec les nouveaux quotas
            export_csv: Exporter les quotas individuels en CSV
        
        Returns:
            Dictionnaire avec les statuts de sauvegarde
        """
        print("\n💾 Sauvegarde des recommandations...")
        results = {}
        
        try:
            # 1. Mettre à jour la table grade
            if update_grade_table:
                print("\n   Mise à jour de la table grade...")
                for grade, data in recommendations['quotas_by_grade'].items():
                    self.db.execute("""
                        UPDATE grade
                        SET quota = ?
                        WHERE code_grade = ?
                    """, (data['quota'], grade))
                    print(f"      ✅ {grade}: quota = {data['quota']}")
                
                self.db.commit()
                results['grade_table_updated'] = True
            
            # 2. Exporter les quotas individuels en CSV
            if export_csv:
                import os
                output_path = os.path.join('results', f'quotas_proposes_session_{self.session_id}.csv')
                os.makedirs('results', exist_ok=True)
                
                recommendations['individual_quotas'].to_csv(output_path, index=False, encoding='utf-8')
                print(f"\n   ✅ Quotas individuels exportés: {output_path}")
                results['csv_exported'] = True
                results['csv_path'] = output_path
            
            # 3. Sauvegarder un résumé JSON
            import json
            summary = {
                'session_id': recommendations['session_id'],
                'surveillances_base': recommendations['surveillances_base'],
                'surveillances_totales': recommendations['surveillances_totales'],
                'quotas_by_grade': {
                    grade: {
                        'quota': data['quota'],
                        'nb_enseignants': data['nb_enseignants'],
                        'total_capacity': data['total_capacity']
                    }
                    for grade, data in recommendations['quotas_by_grade'].items()
                },
                'max_voeux_allowance': recommendations['max_voeux_allowance'],
                'parameters': recommendations['parameters']
            }
            
            summary_path = os.path.join('results', f'decision_summary_session_{self.session_id}.json')
            with open(summary_path, 'w', encoding='utf-8') as f:
                json.dump(summary, f, indent=2, ensure_ascii=False)
            
            print(f"   ✅ Résumé JSON sauvegardé: {summary_path}")
            results['summary_saved'] = True
            results['summary_path'] = summary_path
            
            print("\n✅ Toutes les recommandations ont été sauvegardées avec succès!")
            
        except Exception as e:
            print(f"\n❌ Erreur lors de la sauvegarde: {e}")
            self.db.rollback()
            results['error'] = str(e)
        
        return results


# =============================================================================
# FONCTIONS UTILITAIRES
# =============================================================================

def generate_decision_support_report(session_id: int, 
                                     save: bool = True,
                                     export_csv: bool = True) -> Dict:
    """
    Fonction principale pour générer un rapport d'aide à la décision
    
    Args:
        session_id: ID de la session
        save: Sauvegarder les recommandations en base
        export_csv: Exporter en CSV
    
    Returns:
        Dictionnaire avec les recommandations
    
    Exemple:
        >>> report = generate_decision_support_report(session_id=1)
        >>> print(report['quotas_by_grade'])
    """
    dsm = DecisionSupportModule(session_id)
    recommendations = dsm.generate_recommendations()
    
    if save:
        dsm.save_recommendations(recommendations, 
                                update_grade_table=True,
                                export_csv=export_csv)
    
    return recommendations


def compare_recommendations_with_current(session_id: int) -> pd.DataFrame:
    """
    Comparer les recommandations avec les quotas actuels
    
    Args:
        session_id: ID de la session
    
    Returns:
        DataFrame avec comparaison ancien vs nouveau quota
    """
    db = get_db()
    
    # Quotas actuels
    current_query = """
        SELECT 
            code_grade,
            quota as quota_actuel
        FROM grade
    """
    current_df = pd.read_sql_query(current_query, db)
    
    # Générer les nouvelles recommandations
    dsm = DecisionSupportModule(session_id)
    recommendations = dsm.generate_recommendations()
    
    # Créer le DataFrame de comparaison
    comparison = []
    for grade, data in recommendations['quotas_by_grade'].items():
        current = current_df[current_df['code_grade'] == grade]['quota_actuel'].values
        current_quota = current[0] if len(current) > 0 else 0
        
        comparison.append({
            'grade': grade,
            'quota_actuel': current_quota,
            'quota_propose': data['quota'],
            'difference': data['quota'] - current_quota,
            'nb_enseignants': data['nb_enseignants'],
            'capacite_actuelle': current_quota * data['nb_enseignants'],
            'capacite_proposee': data['total_capacity']
        })
    
    return pd.DataFrame(comparison)


# =============================================================================
# EXEMPLE D'UTILISATION
# =============================================================================

if __name__ == "__main__":
    import sys
    
    # Session ID par défaut
    session_id = 1
    if len(sys.argv) > 1:
        session_id = int(sys.argv[1])
    
    print("\n" + "="*70)
    print("MODULE D'AIDE À LA DÉCISION - DÉMONSTRATION")
    print("="*70)
    
    # 1. Générer les recommandations
    print(f"\n🚀 Génération des recommandations pour la session {session_id}...")
    recommendations = generate_decision_support_report(
        session_id=session_id,
        save=False,  # Ne pas sauvegarder automatiquement
        export_csv=True
    )
    
    # 2. Comparer avec les quotas actuels
    print("\n📊 Comparaison avec les quotas actuels:")
    comparison_df = compare_recommendations_with_current(session_id)
    print(comparison_df.to_string(index=False))
    
    # 3. Demander confirmation pour sauvegarder
    print("\n" + "="*70)
    print("💡 VOULEZ-VOUS ADOPTER CES RECOMMANDATIONS?")
    print("="*70)
    print("\nOptions:")
    print("  1. Adopter les recommandations (mettre à jour la base)")
    print("  2. Modifier manuellement (les fichiers CSV ont été exportés)")
    print("  3. Annuler")
    
    choice = input("\nVotre choix (1/2/3): ").strip()
    
    if choice == "1":
        print("\n📝 Sauvegarde des recommandations en base de données...")
        dsm = DecisionSupportModule(session_id)
        results = dsm.save_recommendations(recommendations, 
                                          update_grade_table=True,
                                          export_csv=True)
        print("\n✅ Recommandations adoptées avec succès!")
        
    elif choice == "2":
        print("\n📝 Les quotas proposés ont été exportés en CSV.")
        print(f"   Fichier: results/quotas_proposes_session_{session_id}.csv")
        print("\n💡 Vous pouvez modifier ce fichier et l'importer ensuite.")
        
    else:
        print("\n❌ Opération annulée. Aucune modification n'a été apportée.")
    
    print("\n" + "="*70)
    print("FIN DU MODULE D'AIDE À LA DÉCISION")
    print("="*70)
