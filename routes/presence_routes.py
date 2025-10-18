import sqlite3
from flask import Blueprint, jsonify, request
from database.database import get_db

presence_bp = Blueprint('presence', __name__)

@presence_bp.route('/', methods=['GET'])
def get_all_presences():
    """
    GET /api/presence - Récupérer tous les responsables absents de toutes les sessions
    
    Query Parameters:
    - session_id (optionnel): Filtrer par session
    - participe_surveillance (optionnel): Filtrer par participation (0 ou 1)
    """
    try:
        db = get_db()
        
        # Récupérer les paramètres de requête
        session_id = request.args.get('session_id', type=int)
        participe_surveillance = request.args.get('participe_surveillance', type=int)
        
        # Construire la requête SQL
        query = '''
            SELECT 
                r.id,
                r.id_session,
                s.libelle_session,
                r.code_smartex_ens,
                r.nom,
                r.prenom,
                r.grade_code,
                r.participe_surveillance,
                r.nbre_jours_absents,
                r.nbre_creneaux_absents,
                r.nbre_total_jours_responsable,
                r.nbre_total_creneaux_responsable,
                r.dates_absentes
            FROM responsable_absent_jour_examen r
            LEFT JOIN session s ON r.id_session = s.id_session
            WHERE 1=1
        '''
        
        params = []
        
        # Appliquer les filtres
        if session_id is not None:
            query += ' AND r.id_session = ?'
            params.append(session_id)
        
        if participe_surveillance is not None:
            query += ' AND r.participe_surveillance = ?'
            params.append(participe_surveillance)
        
        query += ' ORDER BY r.id_session, r.nom, r.prenom'
        
        # Exécuter la requête
        responsables = db.execute(query, params).fetchall()
        
        # Formater les résultats
        results = []
        for resp in responsables:
            results.append({
                'id': resp['id'],
                'id_session': resp['id_session'],
                'libelle_session': resp['libelle_session'],
                'code_smartex_ens': resp['code_smartex_ens'],
                'nom': resp['nom'],
                'prenom': resp['prenom'],
                'grade_code': resp['grade_code'],
                'participe_surveillance': resp['participe_surveillance'] == 1,
                'nbre_jours_absents': resp['nbre_jours_absents'],
                'nbre_creneaux_absents': resp['nbre_creneaux_absents'],
                'nbre_total_jours_responsable': resp['nbre_total_jours_responsable'],
                'nbre_total_creneaux_responsable': resp['nbre_total_creneaux_responsable'],
                'dates_absentes': resp['dates_absentes'].split(',') if resp['dates_absentes'] else [],
                'taux_presence_jours': round(
                    ((resp['nbre_total_jours_responsable'] - resp['nbre_jours_absents']) / resp['nbre_total_jours_responsable'] * 100)
                    if resp['nbre_total_jours_responsable'] > 0 else 0, 2
                ),
                'taux_presence_creneaux': round(
                    ((resp['nbre_total_creneaux_responsable'] - resp['nbre_creneaux_absents']) / resp['nbre_total_creneaux_responsable'] * 100)
                    if resp['nbre_total_creneaux_responsable'] > 0 else 0, 2
                )
            })
        
        # Statistiques globales
        statistiques = {
            'total_responsables_absents': len(results),
            'total_jours_absents': sum(r['nbre_jours_absents'] for r in results),
            'total_creneaux_absents': sum(r['nbre_creneaux_absents'] for r in results),
        }
        
        return jsonify({
            'count': len(results),
            'statistiques': statistiques,
            'data': results
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@presence_bp.route('/session/<int:id_session>', methods=['GET'])
def get_presences_by_session(id_session):
    """
    GET /api/presence/session/<id_session> - Récupérer les responsables absents d'une session
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
        
        # Récupérer les responsables absents
        responsables = db.execute('''
            SELECT 
                id,
                id_session,
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
        
        # Formater les résultats
        results = []
        for resp in responsables:
            results.append({
                'id': resp['id'],
                'id_session': resp['id_session'],
                'code_smartex_ens': resp['code_smartex_ens'],
                'nom': resp['nom'],
                'prenom': resp['prenom'],
                'grade_code': resp['grade_code'],
                'participe_surveillance': resp['participe_surveillance'] == 1,
                'nbre_jours_absents': resp['nbre_jours_absents'],
                'nbre_creneaux_absents': resp['nbre_creneaux_absents'],
                'nbre_total_jours_responsable': resp['nbre_total_jours_responsable'],
                'nbre_total_creneaux_responsable': resp['nbre_total_creneaux_responsable'],
                'dates_absentes': resp['dates_absentes'].split(',') if resp['dates_absentes'] else [],
                'taux_presence_jours': round(
                    ((resp['nbre_total_jours_responsable'] - resp['nbre_jours_absents']) / resp['nbre_total_jours_responsable'] * 100)
                    if resp['nbre_total_jours_responsable'] > 0 else 0, 2
                ),
                'taux_presence_creneaux': round(
                    ((resp['nbre_total_creneaux_responsable'] - resp['nbre_creneaux_absents']) / resp['nbre_total_creneaux_responsable'] * 100)
                    if resp['nbre_total_creneaux_responsable'] > 0 else 0, 2
                )
            })
        
        # Statistiques pour cette session
        total_enseignants_surveillants = db.execute('''
            SELECT COUNT(*) as count
            FROM enseignant
            WHERE participe_surveillance = 1
        ''').fetchone()['count']
        
        statistiques = {
            'total_responsables_absents': len(results),
            'total_enseignants_surveillants': total_enseignants_surveillants,
            'total_jours_absents': sum(r['nbre_jours_absents'] for r in results),
            'total_creneaux_absents': sum(r['nbre_creneaux_absents'] for r in results),
            'taux_responsables_presents': round(
                (1 - len(results) / total_enseignants_surveillants) * 100 
                if total_enseignants_surveillants > 0 else 100, 2
            )
        }
        
        return jsonify({
            'session_id': id_session,
            'session_libelle': session['libelle_session'],
            'count': len(results),
            'statistiques': statistiques,
            'data': results
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@presence_bp.route('/enseignant/<int:code_smartex>', methods=['GET'])
def get_presences_by_enseignant(code_smartex):
    """
    GET /api/presence/enseignant/<code_smartex> - Récupérer l'historique d'absence d'un enseignant
    """
    try:
        db = get_db()
        
        # Vérifier que l'enseignant existe
        enseignant = db.execute(
            'SELECT * FROM enseignant WHERE code_smartex_ens = ?', 
            (code_smartex,)
        ).fetchone()
        
        if enseignant is None:
            return jsonify({'error': 'Enseignant non trouvé'}), 404
        
        # Récupérer toutes les absences de cet enseignant
        responsables = db.execute('''
            SELECT 
                r.id,
                r.id_session,
                s.libelle_session,
                r.code_smartex_ens,
                r.nom,
                r.prenom,
                r.grade_code,
                r.participe_surveillance,
                r.nbre_jours_absents,
                r.nbre_creneaux_absents,
                r.nbre_total_jours_responsable,
                r.nbre_total_creneaux_responsable,
                r.dates_absentes
            FROM responsable_absent_jour_examen r
            LEFT JOIN session s ON r.id_session = s.id_session
            WHERE r.code_smartex_ens = ?
            ORDER BY r.id_session
        ''', (code_smartex,)).fetchall()
        
        # Formater les résultats
        results = []
        for resp in responsables:
            results.append({
                'id': resp['id'],
                'id_session': resp['id_session'],
                'libelle_session': resp['libelle_session'],
                'nbre_jours_absents': resp['nbre_jours_absents'],
                'nbre_creneaux_absents': resp['nbre_creneaux_absents'],
                'nbre_total_jours_responsable': resp['nbre_total_jours_responsable'],
                'nbre_total_creneaux_responsable': resp['nbre_total_creneaux_responsable'],
                'dates_absentes': resp['dates_absentes'].split(',') if resp['dates_absentes'] else [],
                'taux_presence_jours': round(
                    ((resp['nbre_total_jours_responsable'] - resp['nbre_jours_absents']) / resp['nbre_total_jours_responsable'] * 100)
                    if resp['nbre_total_jours_responsable'] > 0 else 0, 2
                ),
                'taux_presence_creneaux': round(
                    ((resp['nbre_total_creneaux_responsable'] - resp['nbre_creneaux_absents']) / resp['nbre_total_creneaux_responsable'] * 100)
                    if resp['nbre_total_creneaux_responsable'] > 0 else 0, 2
                )
            })
        
        # Statistiques globales pour cet enseignant
        total_jours_absents = sum(r['nbre_jours_absents'] for r in results)
        total_creneaux_absents = sum(r['nbre_creneaux_absents'] for r in results)
        total_jours_responsable = sum(r['nbre_total_jours_responsable'] for r in results)
        total_creneaux_responsable = sum(r['nbre_total_creneaux_responsable'] for r in results)
        
        statistiques = {
            'total_sessions_avec_absences': len(results),
            'total_jours_absents': total_jours_absents,
            'total_creneaux_absents': total_creneaux_absents,
            'total_jours_responsable': total_jours_responsable,
            'total_creneaux_responsable': total_creneaux_responsable,
            'taux_presence_global_jours': round(
                ((total_jours_responsable - total_jours_absents) / total_jours_responsable * 100)
                if total_jours_responsable > 0 else 0, 2
            ),
            'taux_presence_global_creneaux': round(
                ((total_creneaux_responsable - total_creneaux_absents) / total_creneaux_responsable * 100)
                if total_creneaux_responsable > 0 else 0, 2
            )
        }
        
        return jsonify({
            'enseignant': {
                'code_smartex_ens': enseignant['code_smartex_ens'],
                'nom': enseignant['nom_ens'],
                'prenom': enseignant['prenom_ens'],
                'grade': enseignant['grade_code_ens'],
                'participe_surveillance': enseignant['participe_surveillance'] == 1
            },
            'count': len(results),
            'statistiques': statistiques,
            'data': results
        }), 200
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
