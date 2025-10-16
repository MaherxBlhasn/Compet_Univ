"""
Routes pour l'optimisation et gestion des affectations
avec support CRUD complet et switching bidirectionnel de code_smartex_ens
API simplifiée en anglais
"""

from flask import Blueprint, request, jsonify
from database import get_db
import json
import os
import sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from optimize_example import (
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
# AFFECTATIONS - CRUD OPERATIONS
# ===================================================================

@optimize_bp.route('', methods=['GET'])
def list_all():
    """
    Get all affectations with all details (joins)
    Filters: session_id, code_ens, jour
    """
    db = get_db()
    session_id = request.args.get('session_id', type=int)
    code_ens = request.args.get('code_ens', type=int)
    jour = request.args.get('jour', type=int)
    
    query = """
        SELECT
            a.affectation_id,
            a.code_smartex_ens,
            e.nom_ens,
            e.prenom_ens,
            e.email_ens,
            e.grade_code_ens,
            g.quota as grade_quota,
            a.creneau_id,
            c.dateExam,
            c.h_debut,
            c.h_fin,
            c.type_ex,
            c.semestre,
            a.jour,
            a.seance,
            a.date_examen,
            a.cod_salle,
            a.position,
            a.id_session,
            s.libelle_session,
            s.date_debut,
            s.date_fin
        FROM affectation a
        LEFT JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
        LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
        LEFT JOIN creneau c ON a.creneau_id = c.creneau_id
        LEFT JOIN session s ON a.id_session = s.id_session
        WHERE 1=1
    """
    
    params = []
    
    if session_id:
        query += " AND a.id_session = ?"
        params.append(session_id)
    if code_ens:
        query += " AND a.code_smartex_ens = ?"
        params.append(code_ens)
    if jour:
        query += " AND a.jour = ?"
        params.append(jour)
    
    query += " ORDER BY a.date_examen, a.h_debut, a.cod_salle"
    
    cursor = db.execute(query, params)
    affectations = [dict(row) for row in cursor.fetchall()]
    
    return jsonify({
        'success': True,
        'count': len(affectations),
        'data': affectations
    })


@optimize_bp.route('/<int:affectation_id>', methods=['GET'])
def get_one(affectation_id):
    """Get specific affectation with all details"""
    db = get_db()
    
    query = """
        SELECT
            a.affectation_id,
            a.code_smartex_ens,
            e.nom_ens,
            e.prenom_ens,
            e.email_ens,
            e.grade_code_ens,
            g.quota as grade_quota,
            a.creneau_id,
            c.dateExam,
            c.h_debut,
            c.h_fin,
            c.type_ex,
            c.semestre,
            a.jour,
            a.seance,
            a.date_examen,
            a.cod_salle,
            a.position,
            a.id_session,
            s.libelle_session
        FROM affectation a
        LEFT JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
        LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
        LEFT JOIN creneau c ON a.creneau_id = c.creneau_id
        LEFT JOIN session s ON a.id_session = s.id_session
        WHERE a.affectation_id = ?
    """
    
    cursor = db.execute(query, (affectation_id,))
    affectation = cursor.fetchone()
    
    if not affectation:
        return jsonify({'success': False, 'error': 'Affectation not found'}), 404
    
    return jsonify({'success': True, 'data': dict(affectation)})


@optimize_bp.route('', methods=['POST'])
def create():
    """Create new affectation"""
    db = get_db()
    data = request.get_json()
    
    required = ['code_smartex_ens', 'creneau_id', 'id_session', 'jour', 'seance']
    if not all(f in data for f in required):
        return jsonify({
            'success': False,
            'error': 'Missing required fields: ' + ', '.join(required)
        }), 400
    
    try:
        cursor = db.execute("""
            INSERT INTO affectation (
                code_smartex_ens, creneau_id, id_session, jour, seance,
                date_examen, h_debut, h_fin, cod_salle, position
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data['code_smartex_ens'],
            data['creneau_id'],
            data['id_session'],
            data['jour'],
            data['seance'],
            data.get('date_examen'),
            data.get('h_debut'),
            data.get('h_fin'),
            data.get('cod_salle'),
            data.get('position', 'TITULAIRE')
        ))
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Affectation created successfully',
            'id': cursor.lastrowid
        }), 201
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@optimize_bp.route('/<int:affectation_id>', methods=['PUT'])
def update(affectation_id):
    """Update affectation"""
    db = get_db()
    data = request.get_json()
    
    cursor = db.execute(
        "SELECT * FROM affectation WHERE affectation_id = ?",
        (affectation_id,)
    )
    if not cursor.fetchone():
        return jsonify({'success': False, 'error': 'Affectation not found'}), 404
    
    updates = []
    params = []
    
    fields = [
        'code_smartex_ens', 'creneau_id', 'jour', 'seance',
        'date_examen', 'h_debut', 'h_fin', 'cod_salle', 'position'
    ]
    
    for field in fields:
        if field in data:
            updates.append(f"{field} = ?")
            params.append(data[field])
    
    if not updates:
        return jsonify({'success': False, 'error': 'No fields to update'}), 400
    
    params.append(affectation_id)
    
    try:
        db.execute(
            f"UPDATE affectation SET {', '.join(updates)} WHERE affectation_id = ?",
            params
        )
        db.commit()
        return jsonify({'success': True, 'message': 'Affectation updated successfully'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@optimize_bp.route('/<int:affectation_id>', methods=['DELETE'])
def delete_one(affectation_id):
    """Delete single affectation"""
    db = get_db()
    
    cursor = db.execute(
        "SELECT * FROM affectation WHERE affectation_id = ?",
        (affectation_id,)
    )
    if not cursor.fetchone():
        return jsonify({'success': False, 'error': 'Affectation not found'}), 404
    
    try:
        db.execute("DELETE FROM affectation WHERE affectation_id = ?", (affectation_id,))
        db.commit()
        return jsonify({'success': True, 'message': 'Affectation deleted successfully'})
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


@optimize_bp.route('/delete-all', methods=['DELETE'])
def delete_all():
    """Delete all affectations for a session"""
    db = get_db()
    session_id = request.args.get('session_id', type=int)
    
    if not session_id:
        return jsonify({'success': False, 'error': 'session_id is required'}), 400
    
    try:
        cursor = db.execute(
            "DELETE FROM affectation WHERE id_session = ?",
            (session_id,)
        )
        db.commit()
        
        return jsonify({
            'success': True,
            'message': f'{cursor.rowcount} affectations deleted',
            'deleted': cursor.rowcount
        })
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


# ===================================================================
# SWITCH - PERMUTATION BIDIRECTIONNELLE
# ===================================================================

@optimize_bp.route('/switch', methods=['POST'])
def switch_codes():
    """
    Bidirectional switch of two teacher codes
    They exchange their places completely
    
    Body:
    {
        "code1": 123,
        "code2": 456,
        "session_id": 1,
        "include_voeux": true
    }
    """
    db = get_db()
    data = request.get_json()
    
    code1 = data.get('code1')
    code2 = data.get('code2')
    session_id = data.get('session_id')
    include_voeux = data.get('include_voeux', True)
    
    if not code1 or not code2:
        return jsonify({
            'success': False,
            'error': 'code1 and code2 are required'
        }), 400
    
    if code1 == code2:
        return jsonify({
            'success': False,
            'error': 'Codes must be different'
        }), 400
    
    try:
        # Verify teachers exist
        cursor = db.execute(
            "SELECT * FROM enseignant WHERE code_smartex_ens = ?",
            (code1,)
        )
        ens1 = cursor.fetchone()
        
        cursor = db.execute(
            "SELECT * FROM enseignant WHERE code_smartex_ens = ?",
            (code2,)
        )
        ens2 = cursor.fetchone()
        
        if not ens1:
            return jsonify({
                'success': False,
                'error': f'Teacher {code1} not found'
            }), 404
        
        if not ens2:
            return jsonify({
                'success': False,
                'error': f'Teacher {code2} not found'
            }), 404
        
        ens1_dict = dict(ens1)
        ens2_dict = dict(ens2)
        
        # Swap using temporary code
        temp_code = -999
        
        # Step 1: code1 -> temp
        if session_id:
            db.execute("""
                UPDATE affectation
                SET code_smartex_ens = ?
                WHERE code_smartex_ens = ? AND id_session = ?
            """, (temp_code, code1, session_id))
        else:
            db.execute("""
                UPDATE affectation
                SET code_smartex_ens = ?
                WHERE code_smartex_ens = ?
            """, (temp_code, code1))
        
        # Step 2: code2 -> code1
        if session_id:
            db.execute("""
                UPDATE affectation
                SET code_smartex_ens = ?
                WHERE code_smartex_ens = ? AND id_session = ?
            """, (code1, code2, session_id))
        else:
            db.execute("""
                UPDATE affectation
                SET code_smartex_ens = ?
                WHERE code_smartex_ens = ?
            """, (code1, code2))
        
        # Step 3: temp -> code2
        if session_id:
            db.execute("""
                UPDATE affectation
                SET code_smartex_ens = ?
                WHERE code_smartex_ens = ? AND id_session = ?
            """, (code2, temp_code, session_id))
        else:
            db.execute("""
                UPDATE affectation
                SET code_smartex_ens = ?
                WHERE code_smartex_ens = ?
            """, (code2, temp_code))
        
        aff_count = db.total_changes
        
        # Switch voeux if requested
        voeu_count = 0
        if include_voeux:
            if session_id:
                db.execute("""
                    UPDATE voeu
                    SET code_smartex_ens = ?
                    WHERE code_smartex_ens = ? AND id_session = ?
                """, (temp_code, code1, session_id))
            else:
                db.execute("""
                    UPDATE voeu
                    SET code_smartex_ens = ?
                    WHERE code_smartex_ens = ?
                """, (temp_code, code1))
            
            if session_id:
                db.execute("""
                    UPDATE voeu
                    SET code_smartex_ens = ?
                    WHERE code_smartex_ens = ? AND id_session = ?
                """, (code1, code2, session_id))
            else:
                db.execute("""
                    UPDATE voeu
                    SET code_smartex_ens = ?
                    WHERE code_smartex_ens = ?
                """, (code1, code2))
            
            if session_id:
                db.execute("""
                    UPDATE voeu
                    SET code_smartex_ens = ?
                    WHERE code_smartex_ens = ? AND id_session = ?
                """, (code2, temp_code, session_id))
            else:
                db.execute("""
                    UPDATE voeu
                    SET code_smartex_ens = ?
                    WHERE code_smartex_ens = ?
                """, (code2, temp_code))
            
            voeu_count = db.total_changes - aff_count
        
        db.commit()
        
        return jsonify({
            'success': True,
            'message': 'Switch completed successfully',
            'data': {
                'code1': {
                    'old': code1,
                    'name': f"{ens1_dict['nom_ens']} {ens1_dict['prenom_ens']}",
                    'new': code2,
                    'new_name': f"{ens2_dict['nom_ens']} {ens2_dict['prenom_ens']}"
                },
                'code2': {
                    'old': code2,
                    'name': f"{ens2_dict['nom_ens']} {ens2_dict['prenom_ens']}",
                    'new': code1,
                    'new_name': f"{ens1_dict['nom_ens']} {ens1_dict['prenom_ens']}"
                },
                'affectations_switched': aff_count,
                'voeux_switched': voeu_count,
                'total': aff_count + voeu_count
            }
        })
    
    except Exception as e:
        db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 400


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
        "save": true,
        "clear": true,
        "generate_files": true,
        "generate_stats": true
    }
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
            mapping_df, salle_par_creneau_df = load_data_from_db(session_id)
        
        # Build necessary structures for responsable presence files
        from optimize_example import (
            build_salle_responsable_mapping,
            build_creneaux_from_salles,
            map_creneaux_to_jours_seances,
            build_teachers_dict,
            build_voeux_set,
            generate_responsable_presence_files,
            save_results
        )
        
        print("\n2. Construction des structures...")
        salle_responsable = build_salle_responsable_mapping(planning_df)
        creneaux = build_creneaux_from_salles(salles_df, salle_responsable, salle_par_creneau_df)
        creneaux = map_creneaux_to_jours_seances(creneaux, mapping_df)
        teachers = build_teachers_dict(enseignants_df, parametres_df)
        voeux_set = build_voeux_set(voeux_df)
        
        # Generate responsable presence files
        nb_fichiers_responsables = 0
        total_presences = 0
        if generate_files:
            print("\n3. Génération des fichiers de présence obligatoire...")
            nb_fichiers_responsables, total_presences = generate_responsable_presence_files(
                planning_df, teachers, creneaux, mapping_df
            )
        
        # Run optimization
        print("\n4. Lancement de l'optimisation...")
        result = optimize_surveillance_scheduling(
            enseignants_df, planning_df, salles_df,
            voeux_df, parametres_df, mapping_df, salle_par_creneau_df
        )
        
        saved = 0
        files_generated = []
        stats = None
        quota_saved = False
        infeasibility_diagnostic = None
        
        # If infeasible, generate diagnostic
        if result['status'] == 'infeasible':
            print("\n⚠️ PROBLÈME INFAISABLE - Génération du diagnostic...")
            from infeasibility_diagnostic import diagnose_infeasibility, format_diagnostic_message
            
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
                from surveillance_stats import generate_statistics
                stats = generate_statistics(
                    result['affectations'],
                    creneaux,
                    teachers,
                    voeux_set,
                    planning_df
                )
            
            # Save CSV files
            if generate_files:
                print("\n6. Génération des fichiers CSV...")
                save_results(result['affectations'])
                files_generated.append('affectations_global.csv')
                files_generated.append('convocations individuelles')
                files_generated.append('affectations par jour')
            
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
                    from quota_enseignant_module import (
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