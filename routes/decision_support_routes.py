"""
Routes pour le module d'aide à la décision
Génère des recommandations de quotas et non-souhaits par grade
"""

from flask import Blueprint, request, jsonify
from database.database import get_db
import sys
import os
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.decision_support_module import (
    DecisionSupportModule,
    generate_decision_support_report,
    compare_recommendations_with_current
)

decision_support_bp = Blueprint('decision_support', __name__)


# ===================================================================
# UTILITY FUNCTIONS
# ===================================================================

def convert_numpy_types(obj):
    """
    Convertir récursivement tous les types NumPy en types Python natifs
    pour la sérialisation JSON
    """
    if isinstance(obj, dict):
        return {key: convert_numpy_types(value) for key, value in obj.items()}
    elif isinstance(obj, list):
        return [convert_numpy_types(item) for item in obj]
    elif isinstance(obj, np.integer):
        return int(obj)
    elif isinstance(obj, np.floating):
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, np.ndarray):
        return obj.tolist()
    elif hasattr(obj, 'item'):  # Pour tous les autres types numpy scalaires
        return obj.item()
    else:
        return obj


# ===================================================================
# GENERATE RECOMMENDATIONS
# ===================================================================

@decision_support_bp.route('/recommendations/<int:session_id>', methods=['GET'])
def get_recommendations(session_id):
    """
    Générer les recommandations de quotas pour une session
    
    Query params:
    - save: true/false (défaut: false) - Sauvegarder en base
    - export_csv: true/false (défaut: true) - Exporter en CSV
    - absence_margin: float (défaut: 0.15) - Marge pour absences (15%)
    - min_difference: int (défaut: 3) - Différence minimale entre niveaux
    - max_non_souhaits_ratio: float (défaut: 0.30) - Ratio max non-souhaits (30%)
    
    Response:
    {
        "success": true,
        "data": {
            "session_id": 1,
            "surveillances_base": 622,
            "surveillances_totales": 716,
            "quotas_by_grade": {...},
            "non_souhaits_allowance": {...},
            "individual_quotas": [...],
            "nb_enseignants": 126,
            "nb_creneaux": 311,
            "parameters": {...}
        },
        "files_generated": ["quotas_proposes_session_1.csv", "decision_summary_session_1.json"]
    }
    """
    db = get_db()
    
    try:
        # Vérifier que la session existe
        cursor = db.execute(
            "SELECT * FROM session WHERE id_session = ?",
            (session_id,)
        )
        session = cursor.fetchone()
        
        if not session:
            return jsonify({
                'success': False,
                'error': f'Session {session_id} not found'
            }), 404
        
        # Paramètres
        save = request.args.get('save', 'false').lower() == 'true'
        export_csv = request.args.get('export_csv', 'true').lower() == 'true'
        absence_margin = float(request.args.get('absence_margin', 0.15))
        min_difference = int(request.args.get('min_difference', 3))
        max_non_souhaits_ratio = float(request.args.get('max_non_souhaits_ratio', 0.30))
        
        print(f"\n{'='*60}")
        print(f"RECOMMANDATIONS D'AIDE À LA DÉCISION - SESSION {session_id}")
        print(f"{'='*60}")
        print(f"Paramètres:")
        print(f"  - Sauvegarder: {save}")
        print(f"  - Exporter CSV: {export_csv}")
        print(f"  - Marge absences: {absence_margin*100}%")
        print(f"  - Différence min niveaux: {min_difference}")
        print(f"  - Ratio max non-souhaits: {max_non_souhaits_ratio*100}%")
        
        # Créer le module avec paramètres personnalisés
        dsm = DecisionSupportModule(session_id)
        dsm.absence_margin = absence_margin
        dsm.min_difference_between_levels = min_difference
        dsm.max_non_souhaits_ratio = max_non_souhaits_ratio
        
        # Générer les recommandations
        recommendations = dsm.generate_recommendations()
        
        # Convertir les types NumPy
        recommendations = convert_numpy_types(recommendations)
        
        # Convertir le DataFrame en liste de dictionnaires
        if 'individual_quotas' in recommendations:
            recommendations['individual_quotas'] = recommendations['individual_quotas'].to_dict('records')
        
        files_generated = []
        
        # Sauvegarder si demandé
        if save or export_csv:
            save_results = dsm.save_recommendations(
                recommendations,
                update_grade_table=save,
                export_csv=export_csv
            )
            
            if save_results.get('csv_exported'):
                files_generated.append(save_results.get('csv_path'))
            if save_results.get('summary_saved'):
                files_generated.append(save_results.get('summary_path'))
        
        print(f"\n{'='*60}")
        print("RECOMMANDATIONS GÉNÉRÉES AVEC SUCCÈS")
        print(f"{'='*60}")
        
        return jsonify({
            'success': True,
            'data': recommendations,
            'files_generated': files_generated,
            'saved_to_db': save
        })
    
    except Exception as e:
        db.rollback()
        import traceback
        print(f"ERREUR: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'type': type(e).__name__,
            'traceback': traceback.format_exc()
        }), 500


# ===================================================================
# COMPARE WITH CURRENT
# ===================================================================

@decision_support_bp.route('/compare/<int:session_id>', methods=['GET'])
def compare_with_current(session_id):
    """
    Comparer les recommandations avec les quotas actuels
    
    Query params:
    - absence_margin: float (défaut: 0.15)
    - min_difference: int (défaut: 3)
    - max_non_souhaits_ratio: float (défaut: 0.30)
    
    Response:
    {
        "success": true,
        "data": [
            {
                "grade": "MA",
                "quota_actuel": 7,
                "quota_propose": 5,
                "difference": -2,
                "nb_enseignants": 57,
                "capacite_actuelle": 399,
                "capacite_proposee": 285
            },
            ...
        ],
        "summary": {
            "total_diff_capacity": -114,
            "grades_increased": 2,
            "grades_decreased": 5,
            "grades_unchanged": 0
        }
    }
    """
    db = get_db()
    
    try:
        # Vérifier que la session existe
        cursor = db.execute(
            "SELECT * FROM session WHERE id_session = ?",
            (session_id,)
        )
        session = cursor.fetchone()
        
        if not session:
            return jsonify({
                'success': False,
                'error': f'Session {session_id} not found'
            }), 404
        
        # Paramètres personnalisés
        absence_margin = float(request.args.get('absence_margin', 0.15))
        min_difference = int(request.args.get('min_difference', 3))
        max_non_souhaits_ratio = float(request.args.get('max_non_souhaits_ratio', 0.30))
        
        # Créer le module avec paramètres
        dsm = DecisionSupportModule(session_id)
        dsm.absence_margin = absence_margin
        dsm.min_difference_between_levels = min_difference
        dsm.max_non_souhaits_ratio = max_non_souhaits_ratio
        
        # Générer la comparaison
        comparison_df = compare_recommendations_with_current(session_id)
        
        # Convertir en dictionnaire
        comparison_list = comparison_df.to_dict('records')
        comparison_list = convert_numpy_types(comparison_list)
        
        # Calculer le résumé
        summary = {
            'total_diff_capacity': int(comparison_df['difference'].sum()),
            'grades_increased': int((comparison_df['difference'] > 0).sum()),
            'grades_decreased': int((comparison_df['difference'] < 0).sum()),
            'grades_unchanged': int((comparison_df['difference'] == 0).sum())
        }
        
        return jsonify({
            'success': True,
            'data': comparison_list,
            'summary': summary
        })
    
    except Exception as e:
        import traceback
        print(f"ERREUR: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'type': type(e).__name__
        }), 500


# ===================================================================
# APPLY RECOMMENDATIONS
# ===================================================================

@decision_support_bp.route('/apply/<int:session_id>', methods=['POST'])
def apply_recommendations(session_id):
    """
    Appliquer les recommandations (mettre à jour la table grade)
    
    Body (optional):
    {
        "quotas": {
            "MA": 5,
            "PR": 2,
            "MC": 2,
            ...
        }
    }
    
    Si quotas non fournis, utilise les recommandations calculées automatiquement
    
    Response:
    {
        "success": true,
        "message": "Quotas updated successfully",
        "updated": {
            "MA": 5,
            "PR": 2,
            ...
        }
    }
    """
    db = get_db()
    
    try:
        # Vérifier que la session existe
        cursor = db.execute(
            "SELECT * FROM session WHERE id_session = ?",
            (session_id,)
        )
        session = cursor.fetchone()
        
        if not session:
            return jsonify({
                'success': False,
                'error': f'Session {session_id} not found'
            }), 404
        
        data = request.get_json() or {}
        custom_quotas = data.get('quotas')
        
        if custom_quotas:
            # Utiliser les quotas fournis
            print(f"\nApplication des quotas personnalisés pour session {session_id}...")
            updated = {}
            
            for grade, quota in custom_quotas.items():
                db.execute("""
                    UPDATE grade
                    SET quota = ?
                    WHERE code_grade = ?
                """, (quota, grade))
                updated[grade] = quota
                print(f"  - {grade}: {quota}")
            
            db.commit()
            
            return jsonify({
                'success': True,
                'message': 'Custom quotas applied successfully',
                'updated': updated
            })
        
        else:
            # Générer et appliquer les recommandations automatiques
            print(f"\nGénération et application des recommandations pour session {session_id}...")
            
            dsm = DecisionSupportModule(session_id)
            recommendations = dsm.generate_recommendations()
            
            save_results = dsm.save_recommendations(
                recommendations,
                update_grade_table=True,
                export_csv=True
            )
            
            updated = {
                grade: data['quota']
                for grade, data in recommendations['quotas_by_grade'].items()
            }
            
            return jsonify({
                'success': True,
                'message': 'Recommendations applied successfully',
                'updated': updated,
                'files_generated': [
                    save_results.get('csv_path'),
                    save_results.get('summary_path')
                ]
            })
    
    except Exception as e:
        db.rollback()
        import traceback
        print(f"ERREUR: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e),
            'type': type(e).__name__
        }), 500


# ===================================================================
# GET CURRENT QUOTAS
# ===================================================================

@decision_support_bp.route('/current-quotas', methods=['GET'])
def get_current_quotas():
    """
    Récupérer les quotas actuels de tous les grades
    
    Response:
    {
        "success": true,
        "data": [
            {
                "code_grade": "MA",
                "grade": "Maître Assistant",
                "quota": 7
            },
            ...
        ]
    }
    """
    db = get_db()
    
    try:
        cursor = db.execute("""
            SELECT code_grade, grade, quota
            FROM grade
            ORDER BY code_grade
        """)
        
        quotas = [dict(row) for row in cursor.fetchall()]
        
        return jsonify({
            'success': True,
            'data': quotas
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500


# ===================================================================
# GET PARAMETERS INFO
# ===================================================================

@decision_support_bp.route('/parameters-info', methods=['GET'])
def get_parameters_info():
    """
    Obtenir les informations sur les paramètres configurables
    
    Response:
    {
        "success": true,
        "data": {
            "absence_margin": {
                "default": 0.15,
                "description": "Marge pour absences potentielles (15%)",
                "range": [0.0, 0.5]
            },
            "min_difference": {
                "default": 3,
                "description": "Différence minimale entre niveaux hiérarchiques",
                "range": [1, 10]
            },
            "max_non_souhaits_ratio": {
                "default": 0.30,
                "description": "Ratio maximum de non-souhaits autorisés (30%)",
                "range": [0.0, 0.5]
            }
        },
        "grade_hierarchy": {
            "level_1": ["PR", "MC", "V"],
            "level_2": ["MA"],
            "level_3": ["AS", "EX"],
            "level_4": ["AC", "PTC", "PES"]
        }
    }
    """
    return jsonify({
        'success': True,
        'data': {
            'absence_margin': {
                'default': 0.15,
                'description': 'Marge pour absences potentielles (15%)',
                'range': [0.0, 0.5],
                'unit': 'percentage'
            },
            'min_difference': {
                'default': 3,
                'description': 'Différence minimale entre niveaux hiérarchiques (Expert)',
                'range': [1, 10],
                'unit': 'surveillances'
            },
            'max_non_souhaits_ratio': {
                'default': 0.30,
                'description': 'Ratio maximum de non-souhaits autorisés (30%)',
                'range': [0.0, 0.5],
                'unit': 'percentage'
            }
        },
        'grade_hierarchy': {
            'level_1': {
                'grades': ['PR', 'MC', 'V'],
                'description': 'Professeurs, Maîtres de conférences, Vacataires - Quota le plus bas'
            },
            'level_2': {
                'grades': ['MA'],
                'description': 'Maîtres assistants - Quota supérieur à niveau 1'
            },
            'level_3': {
                'grades': ['AS', 'EX'],
                'description': 'Assistants, Experts - Quota supérieur à niveau 2'
            },
            'level_4': {
                'grades': ['AC', 'PTC', 'PES'],
                'description': 'Assistants contractuels, PTC, PES - Quota le plus élevé'
            }
        },
        'formula': 'quota(niveau) = quota_base + (niveau - 1) × min_difference'
    })


# ===================================================================
# STATISTICS
# ===================================================================

@decision_support_bp.route('/statistics/<int:session_id>', methods=['GET'])
def get_statistics(session_id):
    """
    Obtenir des statistiques détaillées pour la session
    
    Response:
    {
        "success": true,
        "data": {
            "enseignants": {
                "total": 126,
                "by_grade": {"MA": 57, "PR": 10, ...}
            },
            "creneaux": {
                "total": 311,
                "salles_total": 311
            },
            "surveillances": {
                "required_base": 622,
                "required_with_margin": 716,
                "current_capacity": 777,
                "deficit_or_surplus": 61
            },
            "voeux": {
                "total": 636,
                "by_grade": {...}
            }
        }
    }
    """
    db = get_db()
    
    try:
        # Vérifier que la session existe
        cursor = db.execute(
            "SELECT * FROM session WHERE id_session = ?",
            (session_id,)
        )
        session = cursor.fetchone()
        
        if not session:
            return jsonify({
                'success': False,
                'error': f'Session {session_id} not found'
            }), 404
        
        # Créer le module pour obtenir les données
        dsm = DecisionSupportModule(session_id)
        data = dsm.load_session_data()
        
        enseignants_df = data['enseignants_df']
        creneaux_df = data['creneaux_df']
        salles_creneau_df = data['salles_creneau_df']
        voeux_df = data['voeux_df']
        
        # Statistiques enseignants
        enseignants_by_grade = enseignants_df['grade_code_ens'].value_counts().to_dict()
        
        # Statistiques créneaux
        nb_creneaux = len(creneaux_df)
        nb_salles = len(salles_creneau_df)
        
        # Statistiques surveillances
        surveillances_base = int(salles_creneau_df['nb_surveillants'].sum())
        surveillances_marge = int(surveillances_base * 1.15)
        
        # Capacité actuelle
        cursor = db.execute("""
            SELECT g.code_grade, g.quota, COUNT(e.code_smartex_ens) as nb_ens
            FROM grade g
            LEFT JOIN enseignant e ON g.code_grade = e.grade_code_ens
            GROUP BY g.code_grade
        """)
        
        current_capacity = sum(row['quota'] * row['nb_ens'] for row in cursor.fetchall())
        
        # Statistiques voeux
        voeux_by_grade = voeux_df.merge(
            enseignants_df[['code_smartex_ens', 'grade_code_ens']],
            on='code_smartex_ens',
            how='left'
        )['grade_code_ens'].value_counts().to_dict()
        
        return jsonify({
            'success': True,
            'data': {
                'enseignants': {
                    'total': len(enseignants_df),
                    'by_grade': convert_numpy_types(enseignants_by_grade)
                },
                'creneaux': {
                    'total': nb_creneaux,
                    'salles_total': nb_salles
                },
                'surveillances': {
                    'required_base': surveillances_base,
                    'required_with_margin': surveillances_marge,
                    'current_capacity': current_capacity,
                    'deficit_or_surplus': current_capacity - surveillances_marge
                },
                'voeux': {
                    'total': len(voeux_df),
                    'by_grade': convert_numpy_types(voeux_by_grade)
                }
            }
        })
    
    except Exception as e:
        import traceback
        print(f"ERREUR: {e}")
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': str(e)
        }), 500
