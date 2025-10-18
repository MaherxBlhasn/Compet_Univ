"""
Routes pour l'optimisation et gestion des affectations
avec support CRUD complet et switching bidirectionnel de code_smartex_ens
API simplifiée en anglais
"""

from flask import Blueprint, request, jsonify
from database.database import get_db, remplir_responsables_absents
import json
import os
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scripts.optimize_example import (
    optimize_surveillance_scheduling,
    load_data_from_db,
    save_results_to_db
)

optimize_bp = Blueprint('optimize', __name__)


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
# OPTIMIZE
# ===================================================================

@optimize_bp.route('/run', methods=['POST'])
def run():
    """
    Run optimization for a session with complete processing
    
    Body:
    {
        "session_id": 1,
        "save": true,               // Sauvegarder en base de données
        "clear": true,              // Supprimer anciennes affectations avant
        "generate_files": true,     // Générer quota_enseignant.csv (Note: Pour les CSV d'affectations, utilisez /api/affectations/csv/<session_id>)
        "generate_stats": true      // Générer les statistiques
    }
    
    Note: La génération des CSV d'affectations (global, par jour, convocations) 
    se fait maintenant via GET /api/affectations/csv/<session_id>
    """
    db = get_db()
    data = request.get_json()
    session_id = data.get('session_id')
    save = data.get('save', True)
    clear = data.get('clear', True)
    generate_files = data.get('generate_files', True)
    generate_stats = data.get('generate_stats', True)
    
    if not session_id:
        return jsonify({
            'success': False,
            'error': 'session_id is required'
        }), 400
    
    try:
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
        
        print("\n" + "="*60)
        print(f"OPTIMISATION DE LA SESSION {session_id}")
        print("="*60)
        
        # Load data
        print("\n1. Chargement des données...")
        enseignants_df, planning_df, salles_df, voeux_df, parametres_df, \
            mapping_df, salle_par_creneau_df, adjusted_quotas = load_data_from_db(session_id)
        
        # Build necessary structures for responsable presence files
        from scripts.optimize_example import (
            build_salle_responsable_mapping,
            build_creneaux_from_salles,
            map_creneaux_to_jours_seances,
            build_teachers_dict,
            build_voeux_set
        )
        
        print("\n2. Construction des structures...")
        salle_responsable = build_salle_responsable_mapping(planning_df)
        creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df)
        creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
        teachers = build_teachers_dict(enseignants_df, parametres_df, adjusted_quotas)
        voeux_set = build_voeux_set(voeux_df)
        
        # Generate responsable presence files (disabled - function not available)
        nb_fichiers_responsables = 0
        total_presences = 0
        # if generate_files:
        #     print("\n3. Génération des fichiers de présence obligatoire...")
        #     nb_fichiers_responsables, total_presences = generate_responsable_presence_files(
        #         planning_df, teachers, creneaux, mapping_df
        #     )
        
        # Run optimization
        print("\n4. Lancement de l'optimisation...")
        result = optimize_surveillance_scheduling(
            enseignants_df, planning_df, salles_df,
            voeux_df, parametres_df, mapping_df, salle_par_creneau_df,
            adjusted_quotas
        )
        
        saved = 0
        files_generated = []
        stats = None
        quota_saved = False
        infeasibility_diagnostic = None
        
        # If infeasible, generate diagnostic
        if result['status'] == 'infeasible':
            print("\n⚠️ PROBLÈME INFAISABLE - Génération du diagnostic...")
            from scripts.infeasibility_diagnostic import diagnose_infeasibility, format_diagnostic_message
            
            infeasibility_diagnostic = diagnose_infeasibility(session_id, db)
            # Convertir les types NumPy en types Python natifs pour JSON
            infeasibility_diagnostic = convert_numpy_types(infeasibility_diagnostic)
            diagnostic_message = format_diagnostic_message(infeasibility_diagnostic)
            
            print("\n" + "="*60)
            print("DIAGNOSTIC D'INFAISABILITÉ")
            print("="*60)
            print(diagnostic_message)
        
        if result['status'] == 'ok' and len(result['affectations']) > 0:
            
            # Generate statistics
            if generate_stats:
                print("\n5. Génération des statistiques...")
                from scripts.surveillance_stats import generate_statistics
                stats = generate_statistics(
                    result['affectations'],
                    creneaux,
                    teachers,
                    voeux_set,
                    planning_df
                )
            
            # Note: La génération des CSV se fait maintenant via l'API
            # GET /api/affectations/csv/<session_id>
            if generate_files:
                print("\n6. Note: Pour générer les CSV d'affectations, utilisez GET /api/affectations/csv/<session_id>")
            
            # Save to database
            if save:
                print("\n7. Sauvegarde en base de données...")
                if clear:
                    db.execute(
                        "DELETE FROM affectation WHERE id_session = ?",
                        (session_id,)
                    )
                    db.commit()
                
                saved = save_results_to_db(result['affectations'], session_id)
                
                # Calculate and save quotas
                print("\n8. Calcul des quotas...")
                try:
                    from scripts.quota_enseignant_module import (
                        create_quota_enseignant_table,
                        compute_quota_enseignant,
                        export_quota_to_csv
                    )
                    import pandas as pd
                    
                    conn = db
                    create_quota_enseignant_table(conn)
                    
                    affectations_query = """
                        SELECT code_smartex_ens, creneau_id, id_session, position
                        FROM affectation WHERE id_session = ?
                    """
                    affectations_df = pd.read_sql_query(affectations_query, conn, params=(session_id,))
                    
                    compute_quota_enseignant(affectations_df, session_id, conn)
                    
                    if generate_files:
                        quota_output = os.path.join('results', 'quota_enseignant.csv')
                        quota_df = export_quota_to_csv(session_id, conn, quota_output)
                        if quota_df is not None:
                            files_generated.append('quota_enseignant.csv')
                            quota_saved = True
                    
                    conn.commit()
                    
                except Exception as e:
                    print(f"Erreur calcul quotas: {e}")
        
        # Remplir la table responsable_absent_jour_examen
        remplir_responsables_absents(session_id)
        
        print("\n" + "="*60)
        print("OPTIMISATION TERMINÉE")
        print("="*60)
        
        response_data = {
            'success': result['status'] == 'ok',
            'status': result.get('solver_status', result['status']),
            'solve_time': result.get('solve_time', 0),
            'affectations': len(result['affectations']),
            'saved_to_db': saved,
            'files_generated': files_generated if generate_files else [],
            'responsable_files': nb_fichiers_responsables if generate_files else 0,
            'responsable_presences': total_presences if generate_files else 0,
            'quota_calculated': quota_saved,
            'statistics': stats if generate_stats else None,
            'infeasibility_diagnostic': infeasibility_diagnostic if result['status'] == 'infeasible' else None
        }
        
        return jsonify(response_data)
    
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


@optimize_bp.route('/status/<int:session_id>', methods=['GET'])
def get_status(session_id):
    """Get optimization status for a session"""
    db = get_db()
    
    try:
        cursor = db.execute(
            "SELECT COUNT(*) as count FROM affectation WHERE id_session = ?",
            (session_id,)
        )
        aff_count = cursor.fetchone()['count']
        
        cursor = db.execute(
            "SELECT COUNT(DISTINCT jour) as count FROM affectation WHERE id_session = ?",
            (session_id,)
        )
        days_count = cursor.fetchone()['count']
        
        cursor = db.execute(
            "SELECT COUNT(DISTINCT code_smartex_ens) as count FROM affectation WHERE id_session = ?",
            (session_id,)
        )
        teacher_count = cursor.fetchone()['count']
        
        return jsonify({
            'success': True,
            'data': {
                'session_id': session_id,
                'affectations': aff_count,
                'days': days_count,
                'teachers': teacher_count,
                'optimized': aff_count > 0
            }
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


# ===================================================================
# STATISTICS
# ===================================================================

@optimize_bp.route('/stats/<int:session_id>', methods=['GET'])
def get_stats(session_id):
    """Get detailed statistics for a session"""
    db = get_db()
    
    try:
        # By grade
        cursor = db.execute("""
            SELECT e.grade_code_ens as grade, COUNT(*) as count
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            WHERE a.id_session = ?
            GROUP BY e.grade_code_ens
            ORDER BY grade
        """, (session_id,))
        
        by_grade = {row['grade']: row['count'] for row in cursor.fetchall()}
        
        # By teacher
        cursor = db.execute("""
            SELECT
                a.code_smartex_ens,
                e.nom_ens,
                e.prenom_ens,
                e.grade_code_ens,
                COUNT(*) as count
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            WHERE a.id_session = ?
            GROUP BY a.code_smartex_ens
            ORDER BY count DESC
        """, (session_id,))
        
        by_teacher = [dict(row) for row in cursor.fetchall()]
        
        # By position
        cursor = db.execute("""
            SELECT position, COUNT(*) as count
            FROM affectation
            WHERE id_session = ?
            GROUP BY position
        """, (session_id,))
        
        by_position = {row['position']: row['count'] for row in cursor.fetchall()}
        
        # By day
        cursor = db.execute("""
            SELECT jour, COUNT(*) as count
            FROM affectation
            WHERE id_session = ?
            GROUP BY jour
            ORDER BY jour
        """, (session_id,))
        
        by_day = {row['jour']: row['count'] for row in cursor.fetchall()}
        
        return jsonify({
            'success': True,
            'data': {
                'by_grade': by_grade,
                'by_teacher': by_teacher,
                'by_position': by_position,
                'by_day': by_day
            }
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400


@optimize_bp.route('/workload/<int:session_id>', methods=['GET'])
def get_workload(session_id):
    """Get teacher workload (affectations vs quota)"""
    db = get_db()
    
    try:
        cursor = db.execute("""
            SELECT
                a.code_smartex_ens,
                e.nom_ens,
                e.prenom_ens,
                e.email_ens,
                e.grade_code_ens,
                g.quota,
                COUNT(*) as affectations,
                ROUND(COUNT(*) * 100.0 / g.quota, 2) as percentage
            FROM affectation a
            JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
            JOIN grade g ON e.grade_code_ens = g.code_grade
            WHERE a.id_session = ?
            GROUP BY a.code_smartex_ens
            ORDER BY percentage DESC
        """, (session_id,))
        
        workload = [dict(row) for row in cursor.fetchall()]
        avg = sum(t['percentage'] for t in workload) / len(workload) if workload else 0
        
        return jsonify({
            'success': True,
            'data': workload,
            'summary': {
                'total_teachers': len(workload),
                'average_percentage': round(avg, 2)
            }
        })
    
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        }), 400