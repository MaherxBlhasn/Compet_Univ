#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Module de diagnostic d'infaisabilité
Analyse pourquoi un problème d'optimisation est infaisable
"""

import pandas as pd


def diagnose_infeasibility(session_id, conn):
    """
    Diagnostiquer pourquoi le problème est infaisable
    
    Args:
        session_id: ID de la session
        conn: Connexion à la base de données
    
    Returns:
        dict: Diagnostic détaillé avec les raisons d'infaisabilité
    """
    
    diagnostic = {
        'is_feasible': True,
        'total_required': 0,
        'total_capacity': 0,
        'deficit': 0,
        'reasons': [],
        'grades_analysis': [],
        'suggestions': []
    }
    
    # 1. Récupérer les quotas par grade
    grades_df = pd.read_sql_query("""
        SELECT code_grade, quota
        FROM grade
        ORDER BY code_grade
    """, conn)
    
    # 2. Calculer la capacité totale
    capacity_df = pd.read_sql_query("""
        SELECT 
            e.grade_code_ens,
            COUNT(*) as nb_enseignants,
            g.quota,
            COUNT(*) * g.quota as capacite_totale
        FROM enseignant e
        JOIN grade g ON e.grade_code_ens = g.code_grade
        WHERE e.participe_surveillance = 1
        GROUP BY e.grade_code_ens
        ORDER BY e.grade_code_ens
    """, conn)
    
    total_capacity = capacity_df['capacite_totale'].sum()
    total_enseignants = capacity_df['nb_enseignants'].sum()
    
    # 3. Calculer les besoins en surveillance
    salle_creneau_df = pd.read_sql_query("""
        SELECT dateExam, h_debut, nb_salle
        FROM salle_par_creneau
        WHERE id_session = ?
    """, conn, params=(session_id,))
    
    total_required = 0
    nb_creneaux = len(salle_creneau_df)
    creneaux_details = []
    
    for _, row in salle_creneau_df.iterrows():
        nb_salles = row['nb_salle']
        # Formule: 2 surveillants par salle + 4 réserves
        nb_surveillants = (nb_salles * 2) + 4
        total_required += nb_surveillants
        
        creneaux_details.append({
            'date': row['dateExam'],
            'heure': row['h_debut'],
            'nb_salles': nb_salles,
            'nb_surveillants': nb_surveillants
        })
    
    # 4. Calculer le quota moyen nécessaire (DÉPLACÉ ICI pour être accessible partout)
    quota_moyen_necessaire = total_required / total_enseignants if total_enseignants > 0 else 0
    
    # 5. Analyse de faisabilité globale
    diagnostic['total_required'] = total_required
    diagnostic['total_capacity'] = total_capacity
    diagnostic['deficit'] = total_required - total_capacity
    diagnostic['nb_creneaux'] = nb_creneaux
    diagnostic['nb_enseignants'] = total_enseignants
    diagnostic['quota_moyen_necessaire'] = round(quota_moyen_necessaire, 2)
    
    if total_required > total_capacity:
        diagnostic['is_feasible'] = False
        
        # Raison principale
        diagnostic['reasons'].append({
            'type': 'CAPACITE_INSUFFISANTE',
            'message': f"Capacité insuffisante : {total_required} surveillances requises mais seulement {total_capacity} disponibles",
            'deficit': total_required - total_capacity,
            'severity': 'CRITICAL'
        })
        
        diagnostic['reasons'].append({
            'type': 'QUOTA_MOYEN_INSUFFISANT',
            'message': f"Le quota moyen nécessaire est de {quota_moyen_necessaire:.2f} surveillances/enseignant",
            'quota_actuel_moyen': total_capacity / total_enseignants if total_enseignants > 0 else 0,
            'quota_necessaire': quota_moyen_necessaire,
            'severity': 'HIGH'
        })
    
    # 6. Analyse par grade
    for _, row in capacity_df.iterrows():
        grade = row['grade_code_ens']
        nb_ens = row['nb_enseignants']
        quota = row['quota']
        capacite = row['capacite_totale']
        
        # Estimer la part de ce grade dans les surveillances
        part_theorique = capacite / total_capacity if total_capacity > 0 else 0
        surveillances_attendues = total_required * part_theorique
        deficit_grade = surveillances_attendues - capacite
        
        grade_info = {
            'grade': grade,
            'nb_enseignants': nb_ens,
            'quota_actuel': quota,
            'capacite_actuelle': capacite,
            'part_theorique': round(part_theorique * 100, 1),
            'surveillances_attendues': round(surveillances_attendues, 1),
            'deficit': round(deficit_grade, 1),
            'has_deficit': deficit_grade > 0
        }
        
        # Calculer le quota suggéré (utilise maintenant la variable déplacée)
        if total_enseignants > 0:
            quota_suggere = int(quota_moyen_necessaire) + 1
            grade_info['quota_suggere'] = quota_suggere
            grade_info['gain_potentiel'] = (quota_suggere - quota) * nb_ens
        
        diagnostic['grades_analysis'].append(grade_info)
        
        # Ajouter comme raison si déficit
        if deficit_grade > 0:
            diagnostic['reasons'].append({
                'type': 'DEFICIT_PAR_GRADE',
                'message': f"Grade {grade} : déficit de {deficit_grade:.1f} surveillances",
                'grade': grade,
                'deficit': round(deficit_grade, 1),
                'severity': 'MEDIUM' if deficit_grade < 20 else 'HIGH'
            })
    
    # 7. Vérifier l'équité par grade (NOUVELLE ANALYSE pour contrainte H4)
    equite_issues = []
    
    for _, row in capacity_df.iterrows():
        grade = row['grade_code_ens']
        nb_ens = row['nb_enseignants']
        quota = row['quota']
        
        if nb_ens > 1:
            # Pour que l'équité absolue soit possible, le total des surveillances
            # pour ce grade doit être divisible par le nombre d'enseignants
            grade_info = [g for g in diagnostic['grades_analysis'] if g['grade'] == grade][0]
            surveillances_attendues = grade_info['surveillances_attendues']
            
            # Si le nombre attendu n'est pas un multiple du nombre d'enseignants
            if surveillances_attendues % nb_ens != 0:
                remainder = surveillances_attendues % nb_ens
                
                equite_issues.append({
                    'grade': grade,
                    'nb_enseignants': nb_ens,
                    'surveillances_attendues': surveillances_attendues,
                    'remainder': remainder,
                    'message': f"Grade {grade}: {surveillances_attendues:.1f} surveillances pour {nb_ens} enseignants (reste: {remainder:.1f})"
                })
    
    if equite_issues:
        diagnostic['equite_analysis'] = equite_issues
        
        diagnostic['reasons'].append({
            'type': 'EQUITE_IMPOSSIBLE',
            'message': f"L'équité absolue par grade est IMPOSSIBLE : {len(equite_issues)} grade(s) ne peuvent avoir une distribution parfaitement égale",
            'details': equite_issues,
            'severity': 'CRITICAL'
        })
        
        # Suggestion spécifique pour l'équité
        diagnostic['suggestions'].insert(0, {
            'type': 'ASSOUPLIR_EQUITE',
            'description': "Passer la contrainte d'équité de HARD à SOFT (permettre des différences minimes)",
            'impact': "Permettra de trouver une solution quasi-équitable au lieu d'échouer complètement",
            'feasible_after': True,
            'priority': 0
        })
    
    # 8. Générer des suggestions
    if not diagnostic['is_feasible']:
        # Suggestion 1 : Augmenter les quotas
        quota_suggere_global = int(quota_moyen_necessaire) + 1
        gain_total = sum(
            (quota_suggere_global - row['quota']) * row['nb_enseignants']
            for _, row in capacity_df.iterrows()
        )
        
        diagnostic['suggestions'].append({
            'type': 'AUGMENTER_QUOTAS',
            'description': f"Augmenter tous les quotas à {quota_suggere_global} surveillances/enseignant",
            'impact': f"+{gain_total} surveillances (capacité totale: {total_capacity + gain_total})",
            'feasible_after': (total_capacity + gain_total) >= total_required,
            'priority': 1
        })
        
        # Suggestion 2 : Réduire les réserves
        nb_reserves_actuel = 4
        nb_reserves_suggere = 2
        reduction = (nb_reserves_actuel - nb_reserves_suggere) * nb_creneaux
        
        diagnostic['suggestions'].append({
            'type': 'REDUIRE_RESERVES',
            'description': f"Réduire le nombre de réserves de {nb_reserves_actuel} à {nb_reserves_suggere} par créneau",
            'impact': f"-{reduction} surveillances requises (nouveau total: {total_required - reduction})",
            'feasible_after': total_capacity >= (total_required - reduction),
            'priority': 2
        })
        
        # Suggestion 3 : Recruter plus d'enseignants
        non_participants_df = pd.read_sql_query("""
            SELECT 
                grade_code_ens,
                COUNT(*) as nb_non_participants
            FROM enseignant
            WHERE participe_surveillance = 0
            GROUP BY grade_code_ens
        """, conn)
        
        if len(non_participants_df) > 0:
            total_non_participants = non_participants_df['nb_non_participants'].sum()
            
            # Estimer le gain potentiel
            gain_potentiel = 0
            for _, row in non_participants_df.iterrows():
                grade = row['grade_code_ens']
                nb_non_part = row['nb_non_participants']
                
                # Trouver le quota pour ce grade
                quota_grade = grades_df[grades_df['code_grade'] == grade]['quota'].values
                if len(quota_grade) > 0:
                    gain_potentiel += nb_non_part * quota_grade[0]
            
            diagnostic['suggestions'].append({
                'type': 'RECRUTER_ENSEIGNANTS',
                'description': f"Faire participer les {total_non_participants} enseignants qui ne participent pas actuellement",
                'impact': f"+{gain_potentiel} surveillances potentielles",
                'feasible_after': (total_capacity + gain_potentiel) >= total_required,
                'priority': 3
            })
        
        # Suggestion 4 : Augmenter seulement les grades en déficit
        grades_en_deficit = [g for g in diagnostic['grades_analysis'] if g['has_deficit']]
        if grades_en_deficit:
            suggestions_par_grade = []
            gain_total_cible = 0
            
            for grade_info in grades_en_deficit:
                quota_min = int(grade_info['surveillances_attendues'] / grade_info['nb_enseignants']) + 1
                gain = (quota_min - grade_info['quota_actuel']) * grade_info['nb_enseignants']
                gain_total_cible += gain
                
                suggestions_par_grade.append({
                    'grade': grade_info['grade'],
                    'quota_actuel': grade_info['quota_actuel'],
                    'quota_suggere': quota_min,
                    'gain': gain
                })
            
            diagnostic['suggestions'].append({
                'type': 'AUGMENTER_QUOTAS_CIBLES',
                'description': "Augmenter uniquement les quotas des grades en déficit",
                'details': suggestions_par_grade,
                'impact': f"+{gain_total_cible} surveillances",
                'feasible_after': (total_capacity + gain_total_cible) >= total_required,
                'priority': 2
            })
    
    # 9. Analyser les vœux
    voeux_df = pd.read_sql_query("""
        SELECT COUNT(*) as nb_voeux
        FROM voeu
        WHERE id_session = ?
    """, conn, params=(session_id,))
    
    nb_voeux = voeux_df.iloc[0]['nb_voeux'] if len(voeux_df) > 0 else 0
    
    if nb_voeux > 0:
        # Calculer le taux de vœux
        taux_voeux = (nb_voeux / (total_enseignants * nb_creneaux)) * 100 if total_enseignants > 0 and nb_creneaux > 0 else 0
        
        diagnostic['voeux_analysis'] = {
            'nb_voeux': nb_voeux,
            'taux_voeux': round(taux_voeux, 2),
            'potential_issue': taux_voeux > 30  # Plus de 30% de vœux peut causer des problèmes
        }
        
        if taux_voeux > 30:
            diagnostic['reasons'].append({
                'type': 'VOEUX_TROP_NOMBREUX',
                'message': f"Nombre élevé de vœux de non-surveillance : {nb_voeux} vœux ({taux_voeux:.1f}%)",
                'nb_voeux': nb_voeux,
                'taux': taux_voeux,
                'severity': 'MEDIUM'
            })
    
    # 10. Trier les raisons par sévérité
    severity_order = {'CRITICAL': 0, 'HIGH': 1, 'MEDIUM': 2, 'LOW': 3}
    diagnostic['reasons'].sort(key=lambda x: severity_order.get(x['severity'], 999))
    
    # 11. Trier les suggestions par priorité
    diagnostic['suggestions'].sort(key=lambda x: x['priority'])
    
    return diagnostic


def format_diagnostic_message(diagnostic):
    """
    Formater le diagnostic en message lisible
    
    Args:
        diagnostic: Dictionnaire de diagnostic
    
    Returns:
        str: Message formaté
    """
    
    if diagnostic['is_feasible']:
        return "✅ Le problème est FAISABLE. La capacité disponible est suffisante."
    
    message = "❌ PROBLÈME INFAISABLE\n\n"
    
    # Résumé
    message += f"📊 RÉSUMÉ\n"
    message += f"   • Surveillances requises : {diagnostic['total_required']}\n"
    message += f"   • Capacité disponible    : {diagnostic['total_capacity']}\n"
    message += f"   • DÉFICIT                : {diagnostic['deficit']} surveillances\n"
    message += f"   • Nombre d'enseignants   : {diagnostic['nb_enseignants']}\n"
    message += f"   • Nombre de créneaux     : {diagnostic['nb_creneaux']}\n"
    message += f"   • Quota moyen nécessaire : {diagnostic.get('quota_moyen_necessaire', 0):.2f}\n\n"
    
    # Raisons principales
    if diagnostic['reasons']:
        message += "🔍 RAISONS D'INFAISABILITÉ\n"
        for i, reason in enumerate(diagnostic['reasons'][:5], 1):  # Top 5
            severity_emoji = {
                'CRITICAL': '🔴',
                'HIGH': '🟠',
                'MEDIUM': '🟡',
                'LOW': '🟢'
            }
            emoji = severity_emoji.get(reason['severity'], '⚪')
            message += f"   {i}. {emoji} {reason['message']}\n"
            
            # Détails supplémentaires pour l'équité
            if reason['type'] == 'EQUITE_IMPOSSIBLE' and 'details' in reason:
                for detail in reason['details'][:3]:  # Top 3
                    message += f"      → {detail['message']}\n"
        
        message += "\n"
    
    # Analyse par grade (top 5 déficits)
    grades_with_deficit = [g for g in diagnostic['grades_analysis'] if g['has_deficit']]
    if grades_with_deficit:
        message += "📈 GRADES EN DÉFICIT (Top 5)\n"
        grades_sorted = sorted(grades_with_deficit, key=lambda x: x['deficit'], reverse=True)[:5]
        for grade_info in grades_sorted:
            message += f"   • Grade {grade_info['grade']:3s} : "
            message += f"{grade_info['nb_enseignants']} ens × {grade_info['quota_actuel']} = {grade_info['capacite_actuelle']:3d} | "
            message += f"Besoin: {grade_info['surveillances_attendues']:5.1f} | "
            message += f"Déficit: {grade_info['deficit']:5.1f}\n"
        message += "\n"
    
    # Analyse d'équité
    if 'equite_analysis' in diagnostic and diagnostic['equite_analysis']:
        message += "⚖️ PROBLÈMES D'ÉQUITÉ ABSOLUE\n"
        for eq_issue in diagnostic['equite_analysis'][:5]:  # Top 5
            message += f"   • Grade {eq_issue['grade']} : {eq_issue['surveillances_attendues']:.1f} surveillances "
            message += f"pour {eq_issue['nb_enseignants']} enseignants (indivisible)\n"
        message += "\n"
    
    # Suggestions
    if diagnostic['suggestions']:
        message += "💡 SOLUTIONS RECOMMANDÉES\n"
        for i, suggestion in enumerate(diagnostic['suggestions'][:4], 1):  # Top 4
            feasible_icon = "✅" if suggestion.get('feasible_after', False) else "⚠️"
            message += f"\n   {i}. {feasible_icon} {suggestion['description']}\n"
            message += f"      Impact : {suggestion['impact']}\n"
            
            if suggestion['type'] == 'AUGMENTER_QUOTAS_CIBLES' and 'details' in suggestion:
                message += "      Détails :\n"
                for detail in suggestion['details'][:5]:  # Top 5
                    message += f"         - {detail['grade']} : {detail['quota_actuel']} → {detail['quota_suggere']} (+{detail['gain']})\n"
    
    return message