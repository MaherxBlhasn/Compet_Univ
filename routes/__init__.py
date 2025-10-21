from flask import Blueprint, app

def init_routes(app):
    """Enregistrer tous les blueprints"""
    from routes.grade_routes import grade_bp
    from routes.session_routes import session_bp
    from routes.enseignant_routes import enseignant_bp
    from routes.creneau_routes import creneau_bp
    from routes.voeu_routes import voeu_bp
    from routes.affectation_routes import affectation_bp
    from routes.upload_routes import upload_bp
    from routes.optimize_routes import optimize_bp
    from routes.quota_enseignant_routes import quota_enseignant_bp
    from routes.salle_par_creneau_routes import salle_par_creneau_bp
    from routes.statistics_routes import statistics_bp
    from routes.storage_routes import storage_bp
    from routes.presence_routes import presence_bp
    from routes.email_routes import email_bp
    
    app.register_blueprint(grade_bp, url_prefix='/api/grades')
    app.register_blueprint(session_bp, url_prefix='/api/sessions')
    app.register_blueprint(enseignant_bp, url_prefix='/api/enseignants')
    app.register_blueprint(creneau_bp, url_prefix='/api/creneaux')
    app.register_blueprint(voeu_bp, url_prefix='/api/voeux')
    app.register_blueprint(affectation_bp, url_prefix='/api/affectations')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(optimize_bp, url_prefix='/api/optimize')
    app.register_blueprint(quota_enseignant_bp, url_prefix='/api/quota-enseignants')
    app.register_blueprint(salle_par_creneau_bp, url_prefix='/api/salles-par-creneau')
    app.register_blueprint(statistics_bp, url_prefix='/api/statistics')
    app.register_blueprint(storage_bp, url_prefix='/api/storage')
    app.register_blueprint(presence_bp, url_prefix='/api/presence')
    app.register_blueprint(email_bp, url_prefix='/api/email')
