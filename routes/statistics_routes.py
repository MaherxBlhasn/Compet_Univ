import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db
import pandas as pd
from collections import defaultdict

statistics_bp = Blueprint('statistics', __name__)

@statistics_bp.route('/session/<int:id_session>', methods=['GET'])
def get_session_statistics(id_session):
    """
    GET /api/statistics/session/<id_session> - Récupérer toutes les statistiques d'une session
    
    Retourne :
    - Statistiques de base (enseignants, créneaux, jours)
    - Statistiques d'optimisation (si affectations existent)
    """
    try:
        db = get_db()
        
        # Vérifier que la session existe
        session = db.execute(
            'SELECT * FROM session WHERE id_session = ?', 
            (id_session,)
        ).fetchone()
        
        if session is None:
            return jsonify({'error': 'Session non trouvée'}), 404
        
        # Vérifier si des affectations existent
        has_affectations = db.execute(
            'SELECT COUNT(*) as count FROM affectation WHERE id_session = ?',
            (id_session,)
        ).fetchone()['count'] > 0
        
        # Statistiques de base
        base_stats = _get_base_statistics(db, id_session)
        
        # Statistiques d'optimisation (seulement si affectations existent)
        optimization_stats = None
        if has_affectations:
            optimization_stats = _get_optimization_statistics(db, id_session)
        
        response = {
            'session': dict(session),
            'has_affectations': has_affectations,
            'base_statistics': base_stats,
            'optimization_statistics': optimization_stats
        }
        
        return jsonify(response), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def _get_base_statistics(db, id_session):
    """Calculer les statistiques de base de la session"""
    
    # 1. Enseignants
    total_enseignants = db.execute(
        'SELECT COUNT(*) as count FROM enseignant'
    ).fetchone()['count']
    
    enseignants_surveillants = db.execute(
        'SELECT COUNT(*) as count FROM enseignant WHERE participe_surveillance = 1'
    ).fetchone()['count']
    
    enseignants_non_surveillants = total_enseignants - enseignants_surveillants
    
    # Répartition par grade des surveillants
    enseignants_par_grade = {}
    grade_rows = db.execute('''
        SELECT 
            e.grade_code_ens,
            g.grade,
            g.quota,
            COUNT(*) as count
        FROM enseignant e
        LEFT JOIN grade g ON e.grade_code_ens = g.code_grade
        WHERE e.participe_surveillance = 1
        GROUP BY e.grade_code_ens
        ORDER BY g.quota DESC
    ''').fetchall()
    
    for row in grade_rows:
        enseignants_par_grade[row['grade_code_ens']] = {
            'grade': row['grade'],
            'quota': row['quota'],
            'count': row['count']
        }
    
    # 2. Créneaux de la session
    creneaux = db.execute('''
        SELECT 
            creneau_id,
            dateExam,
            h_debut,
            h_fin,
            cod_salle
        FROM creneau
        WHERE id_session = ?
        ORDER BY dateExam, h_debut
    ''', (id_session,)).fetchall()
    
    total_creneaux = len(creneaux)
    
    # Nombre de salles uniques
    salles_uniques = db.execute('''
        SELECT COUNT(DISTINCT cod_salle) as count
        FROM creneau
        WHERE id_session = ? AND cod_salle IS NOT NULL
    ''', (id_session,)).fetchone()['count']
    
    # 3. Voeux
    total_voeux = db.execute('''
        SELECT COUNT(*) as count
        FROM voeu
        WHERE id_session = ?
    ''', (id_session,)).fetchone()['count']
    
    # Voeux par enseignant
    voeux_stats = db.execute('''
        SELECT 
            MIN(voeu_count) as min_voeux,
            MAX(voeu_count) as max_voeux,
            AVG(voeu_count) as avg_voeux
        FROM (
            SELECT code_smartex_ens, COUNT(*) as voeu_count
            FROM voeu
            WHERE id_session = ?
            GROUP BY code_smartex_ens
        )
    ''', (id_session,)).fetchone()
    
    return {
        'enseignants': {
            'total': total_enseignants,
            'surveillants': enseignants_surveillants,
            'non_surveillants': enseignants_non_surveillants,
            'par_grade': enseignants_par_grade
        },
        'creneaux': {
            'total': total_creneaux,
            'salles': salles_uniques
        },
        'voeux': {
            'total': total_voeux,
            'min_par_enseignant': voeux_stats['min_voeux'] if voeux_stats['min_voeux'] else 0,
            'max_par_enseignant': voeux_stats['max_voeux'] if voeux_stats['max_voeux'] else 0,
            'moyenne_par_enseignant': round(voeux_stats['avg_voeux'], 2) if voeux_stats['avg_voeux'] else 0
        }
    }


def _get_optimization_statistics(db, id_session):
    """Calculer les statistiques d'optimisation basées sur les affectations"""
    
    # Charger les affectations
    affectations = db.execute('''
        SELECT 
            a.*,
            e.nom_ens,
            e.prenom_ens,
            e.grade_code_ens,
            c.dateExam,
            c.h_debut,
            c.h_fin,
            c.cod_salle
        FROM affectation a
        JOIN enseignant e ON a.code_smartex_ens = e.code_smartex_ens
        JOIN creneau c ON a.creneau_id = c.creneau_id
        WHERE a.id_session = ?
    ''', (id_session,)).fetchall()
    
    if not affectations:
        return None
    
    aff_df = pd.DataFrame([dict(row) for row in affectations])
    
    # 1. Respect des voeux
    voeux_stats = _analyze_voeux_respect(db, id_session, aff_df)
    
    # 2. Équité entre grades
    equite_stats = _analyze_grade_equity(db, id_session, aff_df)
    
    # 3. Couverture des créneaux
    couverture_stats = _analyze_coverage(db, id_session, aff_df)
    
    # 4. Responsables de salles
    responsables_stats = _analyze_responsables(db, id_session, aff_df)
    
    # 5. Charge des enseignants
    charge_stats = _analyze_teacher_load(db, id_session, aff_df)
    
    # 6. Dispersion des surveillances
    dispersion_stats = _analyze_dispersion(aff_df)
    
    # 7. Quotas
    quota_stats = _analyze_quotas(db, id_session, aff_df)
    
    return {
        'voeux': voeux_stats,
        'equite_grades': equite_stats,
        'couverture_creneaux': couverture_stats,
        'responsables_salles': responsables_stats,
        'charge_enseignants': charge_stats,
        'dispersion': dispersion_stats,
        'quotas': quota_stats,
        'score_global': _calculate_global_score({
            'voeux': voeux_stats,
            'equite': equite_stats,
            'couverture': couverture_stats,
            'responsables': responsables_stats
        })
    }


def _analyze_voeux_respect(db, id_session, aff_df):
    """Analyser le respect des voeux de non-surveillance"""
    
    # Charger les voeux
    voeux = db.execute('''
        SELECT code_smartex_ens, jour, seance
        FROM voeu
        WHERE id_session = ?
    ''', (id_session,)).fetchall()
    
    if not voeux:
        return {
            'total_voeux': 0,
            'voeux_respectes': 0,
            'voeux_violes': 0,
            'taux_respect': 100.0,
            'details': []
        }
    
    total_voeux = len(voeux)
    voeux_respectes = 0
    voeux_violes_list = []
    
    for voeu in voeux:
        code = voeu['code_smartex_ens']
        jour = voeu['jour']
        seance = voeu['seance']
        
        # Vérifier si l'enseignant est affecté à ce créneau
        matching = aff_df[
            (aff_df['code_smartex_ens'] == code) &
            (aff_df['jour'] == jour) &
            (aff_df['seance'] == seance)
        ]
        
        if len(matching) == 0:
            voeux_respectes += 1
        else:
            voeux_violes_list.append({
                'code_enseignant': int(code),
                'jour': int(jour),
                'seance': str(seance),
                'nb_affectations': int(len(matching))
            })
    
    taux = (voeux_respectes / total_voeux * 100) if total_voeux > 0 else 100.0
    
    return {
        'total_voeux': int(total_voeux),
        'voeux_respectes': int(voeux_respectes),
        'voeux_violes': int(len(voeux_violes_list)),
        'taux_respect': round(taux, 2),
        'details_violations': voeux_violes_list[:10]  # Limiter à 10 pour l'API
    }


def _analyze_grade_equity(db, id_session, aff_df):
    """Analyser l'équité entre grades"""
    
    # Récupérer les enseignants surveillants par grade
    enseignants = db.execute('''
        SELECT code_smartex_ens, grade_code_ens
        FROM enseignant
        WHERE participe_surveillance = 1
    ''').fetchall()
    
    teachers_by_grade = defaultdict(list)
    for ens in enseignants:
        teachers_by_grade[ens['grade_code_ens']].append(ens['code_smartex_ens'])
    
    equite_par_grade = {}
    grades_equitables = 0
    total_grades = len(teachers_by_grade)
    
    for grade, tcodes in teachers_by_grade.items():
        charges = []
        for tcode in tcodes:
            count = len(aff_df[aff_df['code_smartex_ens'] == tcode])
            charges.append(count)
        
        if charges:
            min_charge = int(min(charges))
            max_charge = int(max(charges))
            ecart = int(max_charge - min_charge)
            moyenne = float(sum(charges) / len(charges))

            equitable = (ecart == 0)
            if equitable:
                grades_equitables += 1
            
            equite_par_grade[grade] = {
                'nb_enseignants': int(len(tcodes)),
                'charge_min': min_charge,
                'charge_max': max_charge,
                'charge_moyenne': round(moyenne, 2),
                'ecart': ecart,
                'equitable': bool(equitable)
            }
    
    taux_equite = (grades_equitables / total_grades * 100) if total_grades > 0 else 100.0
    
    return {
        'total_grades': int(total_grades),
        'grades_equitables': int(grades_equitables),
        'taux_equite': round(taux_equite, 2),
        'details_par_grade': equite_par_grade
    }


def _analyze_coverage(db, id_session, aff_df):
    """Analyser la couverture des créneaux (minimum 2 surveillants par salle)"""
    
    # Compter les surveillants par créneau et salle
    couverture = defaultdict(lambda: defaultdict(int))
    
    for _, row in aff_df.iterrows():
        cid = row['creneau_id']
        salle = row['cod_salle']
        if pd.notna(salle):
            couverture[cid][salle] += 1
    
    total_salles = 0
    salles_bien_couvertes = 0  # >= 2 surveillants
    salles_sous_couvertes = 0  # < 2 surveillants
    salles_sur_couvertes = 0   # > 2 surveillants
    
    details_sous_couvertes = []
    
    for cid, salles_dict in couverture.items():
        for salle, nb_surv in salles_dict.items():
            total_salles += 1
            
            if nb_surv < 2:
                salles_sous_couvertes += 1
                # Récupérer info du créneau
                creneau_info = aff_df[aff_df['creneau_id'] == cid].iloc[0]
                details_sous_couvertes.append({
                    'creneau_id': int(cid),
                    'salle': str(salle),
                    'date': str(creneau_info['dateExam']),
                    'heure': str(creneau_info['h_debut']),
                    'nb_surveillants': int(nb_surv)
                })
            elif nb_surv == 2:
                salles_bien_couvertes += 1
            else:
                salles_sur_couvertes += 1
                salles_bien_couvertes += 1
    
    taux = (salles_bien_couvertes / total_salles * 100) if total_salles > 0 else 100.0
    
    return {
        'total_salles': int(total_salles),
        'salles_bien_couvertes': int(salles_bien_couvertes),
        'salles_sous_couvertes': int(salles_sous_couvertes),
        'salles_sur_couvertes': int(salles_sur_couvertes),
        'taux_couverture': round(taux, 2),
        'details_sous_couvertes': details_sous_couvertes[:10]
    }


def _analyze_responsables(db, id_session, aff_df):
    """
    Analyser la présence des responsables de salles
    Retourne uniquement les 3 indicateurs essentiels
    """
    
    # Récupérer le nombre total d'enseignants qui participent aux surveillances
    total_enseignants_surveillants = db.execute('''
        SELECT COUNT(*) as count
        FROM enseignant
        WHERE participe_surveillance = 1
    ''', ()).fetchone()['count']
    
    # Récupérer les responsables absents depuis la table responsable_absent_jour_examen
    # (Seulement ceux qui participent aux surveillances)
    responsables_absents = db.execute('''
        SELECT COUNT(*) as count
        FROM responsable_absent_jour_examen
        WHERE id_session = ?
            AND participe_surveillance = 1
    ''', (id_session,)).fetchone()['count']
    
    # Calculer le taux de surveillants responsables présents
    # = 100 - (nb_responsables_absents / total_enseignants_surveillants) × 100
    taux_absence = (responsables_absents / total_enseignants_surveillants * 100) if total_enseignants_surveillants > 0 else 0.0
    taux_surveillants_responsable_present = 100.0 - taux_absence
    
    return {
        'responsables_absents_count': int(responsables_absents),
        'total_enseignants_surveillants': int(total_enseignants_surveillants),
        'taux_surveillants_responsable_present': round(taux_surveillants_responsable_present, 2)
    }


def _analyze_teacher_load(db, id_session, aff_df):
    """Analyser la charge des enseignants"""
    
    # Tous les enseignants surveillants
    enseignants = db.execute('''
        SELECT code_smartex_ens, nom_ens, prenom_ens, grade_code_ens
        FROM enseignant
        WHERE participe_surveillance = 1
    ''').fetchall()
    
    charges = []
    sans_affectation = 0
    
    charge_par_enseignant = []
    
    for ens in enseignants:
        code = ens['code_smartex_ens']
        count = len(aff_df[aff_df['code_smartex_ens'] == code])
        charges.append(count)
        
        if count == 0:
            sans_affectation += 1
        
        charge_par_enseignant.append({
            'code': int(code),
            'nom': str(ens['nom_ens']),
            'prenom': str(ens['prenom_ens']),
            'grade': str(ens['grade_code_ens']),
            'nb_surveillances': int(count)
        })
    
    # Statistiques
    total_ens = len(enseignants)
    total_affectations = len(aff_df)
    
    return {
        'total_enseignants': int(total_ens),
        'total_affectations': int(total_affectations),
        'enseignants_sans_affectation': int(sans_affectation),
        'charge_min': int(min(charges)) if charges else 0,
        'charge_max': int(max(charges)) if charges else 0,
        'charge_moyenne': round(sum(charges) / len(charges), 2) if charges else 0,
        'repartition': sorted(charge_par_enseignant, key=lambda x: x['nb_surveillances'], reverse=True)[:20]  # Top 20
    }


def _analyze_dispersion(aff_df):
    """Analyser la dispersion des surveillances dans la journée"""
    
    profs_multi_seances = 0
    seances_consecutives = 0
    seances_espacees = 0
    
    for tcode in aff_df['code_smartex_ens'].unique():
        prof_aff = aff_df[aff_df['code_smartex_ens'] == tcode]
        
        for jour in prof_aff['jour'].unique():
            jour_aff = prof_aff[prof_aff['jour'] == jour]
            
            if len(jour_aff) <= 1:
                continue
            
            profs_multi_seances += 1
            
            # Extraire les numéros de séances
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
                    seances_consecutives += 1
                else:
                    seances_espacees += 1
    
    return {
        'enseignants_plusieurs_seances_par_jour': int(profs_multi_seances),
        'seances_consecutives': int(seances_consecutives),
        'seances_espacees': int(seances_espacees)
    }


def _analyze_quotas(db, id_session, aff_df):
    """Analyser les quotas par grade"""
    
    # Vérifier si la table quota_enseignant existe pour cette session
    quota_exists = db.execute('''
        SELECT COUNT(*) as count
        FROM quota_enseignant
        WHERE id_session = ?
    ''', (id_session,)).fetchone()['count'] > 0
    
    if not quota_exists:
        return {
            'quota_table_exists': False,
            'message': 'Table quota_enseignant non remplie pour cette session'
        }
    
    # Charger les quotas
    quotas = db.execute('''
        SELECT 
            code_smartex_ens,
            grade_code_ens,
            quota_grade,
            quota_realise,
            quota_majoritaire,
            diff_quota_grade,
            diff_quota_majoritaire,
            quota_ajuste,
            quota_ajuste_maj
        FROM quota_enseignant
        WHERE id_session = ?
    ''', (id_session,)).fetchall()
    
    quota_df = pd.DataFrame([dict(row) for row in quotas])
    
    # Statistiques par grade
    stats_par_grade = {}
    
    for grade in quota_df['grade_code_ens'].unique():
        grade_data = quota_df[quota_df['grade_code_ens'] == grade]
        
        stats_par_grade[str(grade)] = {
            'nb_enseignants': int(len(grade_data)),
            'quota_moyen': round(float(grade_data['quota_grade'].mean()), 2),
            'realise_moyen': round(float(grade_data['quota_realise'].mean()), 2),
            'diff_grade_moyen': round(float(grade_data['diff_quota_grade'].mean()), 2),
            'diff_majoritaire_moyen': round(float(grade_data['diff_quota_majoritaire'].mean()), 2)
        }
    
    # Équilibre global
    total_diff_grade = abs(quota_df['diff_quota_grade'].sum())
    total_diff_maj = abs(quota_df['diff_quota_majoritaire'].sum())
    
    return {
        'quota_table_exists': True,
        'total_enseignants': int(len(quota_df)),
        'ecart_total_quota_grade': round(float(total_diff_grade), 2),
        'ecart_total_quota_majoritaire': round(float(total_diff_maj), 2),
        'stats_par_grade': stats_par_grade
    }


def _calculate_global_score(stats):
    """Calculer un score global de qualité de l'optimisation (sur 100)"""
    
    score = 0
    max_score = 100
    
    # Voeux (30 points)
    voeux_taux = stats['voeux'].get('taux_respect', 0)
    score += (voeux_taux / 100) * 30
    
    # Équité (25 points)
    equite_taux = stats['equite'].get('taux_equite', 0)
    score += (equite_taux / 100) * 25
    
    # Couverture (25 points)
    couverture_taux = stats['couverture'].get('taux_couverture', 0)
    score += (couverture_taux / 100) * 25
    
    # Responsables (20 points)
    resp_taux = stats['responsables'].get('taux_surveillants_responsable_present', 0)
    score += (resp_taux / 100) * 20
    
    return {
        'score': round(score, 2),
        'max_score': max_score,
        'pourcentage': round(score, 2),
        'appreciation': _get_appreciation(score)
    }


def _get_appreciation(score):
    """Retourner une appréciation basée sur le score"""
    if score >= 95:
        return "Excellent - Solution optimale"
    elif score >= 85:
        return "Très Bien - Solution de haute qualité"
    elif score >= 75:
        return "Bien - Solution satisfaisante"
    elif score >= 65:
        return "Correct - Solution acceptable"
    else:
        return "À améliorer - Solution sous-optimale"


@statistics_bp.route('/sessions', methods=['GET'])
def get_all_sessions_statistics():
    """
    GET /api/statistics/sessions - Récupérer un résumé des statistiques pour toutes les sessions
    """
    try:
        db = get_db()
        
        sessions = db.execute('SELECT * FROM session ORDER BY id_session').fetchall()
        
        sessions_stats = []
        
        for session in sessions:
            id_session = session['id_session']
            
            # Vérifier si des affectations existent
            has_affectations = db.execute(
                'SELECT COUNT(*) as count FROM affectation WHERE id_session = ?',
                (id_session,)
            ).fetchone()['count'] > 0
            
            # Compter les créneaux
            nb_creneaux = db.execute(
                'SELECT COUNT(*) as count FROM creneau WHERE id_session = ?',
                (id_session,)
            ).fetchone()['count']
            
            # Compter les affectations
            nb_affectations = 0
            score = None
            
            if has_affectations:
                nb_affectations = db.execute(
                    'SELECT COUNT(*) as count FROM affectation WHERE id_session = ?',
                    (id_session,)
                ).fetchone()['count']
            
            sessions_stats.append({
                'id_session': id_session,
                'libelle': session['libelle_session'],
                'date_debut': session['date_debut'],
                'date_fin': session['date_fin'],
                'nb_creneaux': nb_creneaux,
                'nb_affectations': nb_affectations,
                'has_affectations': has_affectations
            })
        
        return jsonify({
            'total_sessions': len(sessions),
            'sessions': sessions_stats
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@statistics_bp.route('/session/<int:id_session>/responsables-absents', methods=['GET'])
def get_responsables_absents(id_session):
    """
    GET /api/statistics/session/<id_session>/responsables-absents
    
    Retourne la liste des responsables qui sont ABSENTS le jour de leur examen
    (c'est-à-dire : ils sont responsables d'un examen à une date donnée,
     mais n'ont aucune affectation de surveillance à cette même date)
    """
    try:
        db = get_db()
        
        # Vérifier que la session existe
        session = db.execute(
            'SELECT * FROM session WHERE id_session = ?', 
            (id_session,)
        ).fetchone()
        
        if session is None:
            return jsonify({'error': 'Session non trouvée'}), 404
        
        # Récupérer les responsables absents depuis la table
        responsables_absents = db.execute('''
            SELECT 
                code_smartex_ens,
                nom,
                prenom,
                grade_code,
                participe_surveillance,
                nbre_jours_absents,
                nbre_creneaux_absents,
                nbre_total_jours_responsable,
                nbre_total_creneaux_responsable,
                dates_absentes
            FROM responsable_absent_jour_examen
            WHERE id_session = ?
            ORDER BY nom, prenom
        ''', (id_session,)).fetchall()
        
        # Récupérer les détails pour chaque responsable absent
        details = []
        
        for resp in responsables_absents:
            code = resp['code_smartex_ens']
            
            # Trouver les dates où il est responsable mais absent
            creneaux_responsable = db.execute('''
                SELECT DISTINCT
                    dateExam,
                    COUNT(*) as nb_creneaux_ce_jour
                FROM creneau
                WHERE id_session = ?
                    AND enseignant = ?
                GROUP BY dateExam
                ORDER BY dateExam
            ''', (id_session, code)).fetchall()
            
            dates_absentes = []
            
            for creneau_jour in creneaux_responsable:
                date = creneau_jour['dateExam']
                
                # Vérifier si affecté ce jour
                affecte = db.execute('''
                    SELECT COUNT(*) as count
                    FROM affectation a
                    JOIN creneau c ON a.creneau_id = c.creneau_id
                    WHERE a.code_smartex_ens = ?
                        AND c.dateExam = ?
                        AND c.id_session = ?
                ''', (code, date, id_session)).fetchone()
                
                if affecte['count'] == 0:
                    # Récupérer les créneaux de ce jour où il est responsable
                    creneaux_detail = db.execute('''
                        SELECT 
                            creneau_id,
                            h_debut,
                            h_fin,
                            cod_salle,
                            type_ex
                        FROM creneau
                        WHERE id_session = ?
                            AND enseignant = ?
                            AND dateExam = ?
                        ORDER BY h_debut
                    ''', (id_session, code, date)).fetchall()
                    
                    dates_absentes.append({
                        'date': date,
                        'nb_creneaux': len(creneaux_detail),
                        'creneaux': [dict(c) for c in creneaux_detail]
                    })
            
            details.append({
                'code_smartex_ens': code,
                'nom': resp['nom'],
                'prenom': resp['prenom'],
                'grade': resp['grade_code'],
                'participe_surveillance': resp['participe_surveillance'] == 1,
                'nbre_jours_absents': resp['nbre_jours_absents'],
                'nbre_total_jours_responsable': resp['nbre_total_jours_responsable'],
                'nbre_creneaux_absents': resp['nbre_creneaux_absents'],
                'nbre_total_creneaux_responsable': resp['nbre_total_creneaux_responsable'],
                'dates_absentes': resp['dates_absentes'].split(',') if resp['dates_absentes'] else [],
                'dates_absentes_details': dates_absentes
            })
        
        # Statistiques globales
        total_responsables_absents = len(details)
        total_creneaux_sans_responsable = sum(r['nbre_creneaux_absents'] for r in details)
        
        # Compter le total de responsabilités
        total_responsabilites = db.execute('''
            SELECT COUNT(*) as count
            FROM creneau
            WHERE id_session = ?
                AND enseignant IS NOT NULL
        ''', (id_session,)).fetchone()['count']
        
        taux_absence = 0
        if total_responsabilites > 0:
            taux_absence = (total_creneaux_sans_responsable / total_responsabilites) * 100
        
        return jsonify({
            'session_id': id_session,
            'session_libelle': session['libelle_session'],
            'statistiques': {
                'total_responsables_absents': total_responsables_absents,
                'total_creneaux_sans_responsable': total_creneaux_sans_responsable,
                'total_responsabilites': total_responsabilites,
                'taux_absence': round(taux_absence, 2)
            },
            'responsables_absents': details
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
