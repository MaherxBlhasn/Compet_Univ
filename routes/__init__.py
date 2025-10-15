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
    
    app.register_blueprint(grade_bp, url_prefix='/api/grades')
    app.register_blueprint(session_bp, url_prefix='/api/sessions')
    app.register_blueprint(enseignant_bp, url_prefix='/api/enseignants')
    app.register_blueprint(creneau_bp, url_prefix='/api/creneaux')
    app.register_blueprint(voeu_bp, url_prefix='/api/voeux')
    app.register_blueprint(affectation_bp, url_prefix='/api/affectations')
    app.register_blueprint(upload_bp, url_prefix='/api/upload')
    app.register_blueprint(optimize_bp, url_prefix='/api/affectations')