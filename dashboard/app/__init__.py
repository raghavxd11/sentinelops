"""Application factory: builds and configures the Flask app."""
from flask import Flask, jsonify, render_template, request
from flask_wtf.csrf import CSRFError

from .config import Config
from .extensions import csrf, db, login_manager
from .filters import register_filters
from .models import Deployment, Incident, User


def create_app(test_config=None):
    app = Flask(__name__)
    app.config.from_object(Config)
    if test_config:
        app.config.update(test_config)

    db.init_app(app)
    csrf.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"
    login_manager.login_message = "Sign in to continue."
    login_manager.login_message_category = "info"

    from .routes.api import bp as api_bp
    from .routes.auth import bp as auth_bp
    from .routes.deployments import bp as deployments_bp
    from .routes.incidents import bp as incidents_bp
    from .routes.main import bp as main_bp
    from .routes.services import bp as services_bp

    for blueprint in (main_bp, auth_bp, services_bp, deployments_bp, incidents_bp, api_bp):
        app.register_blueprint(blueprint)

    # The API is called by Jenkins with a token header, not by a browser form,
    # so it does not use CSRF tokens.
    csrf.exempt(api_bp)

    register_filters(app)
    register_error_handlers(app)

    @app.context_processor
    def template_helpers():
        def has_seed_data():
            """True while demo rows from seed.py are in the database."""
            return (
                Deployment.query.filter_by(is_seed=True).first() is not None
                or Incident.query.filter_by(is_seed=True).first() is not None
            )

        return {"has_seed_data": has_seed_data}

    # Create tables on first start. Fine for this project size (no migrations).
    with app.app_context():
        db.create_all()

    return app


@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


def register_error_handlers(app):
    def error_response(code, title, detail):
        if request.path.startswith("/api/"):
            return jsonify({"error": title}), code
        return render_template("error.html", code=code, title=title, detail=detail), code

    @app.errorhandler(404)
    def not_found(error):
        return error_response(404, "Not found", "Nothing is served at this path.")

    @app.errorhandler(405)
    def method_not_allowed(error):
        return error_response(405, "Method not allowed", "This path does not accept that method.")

    @app.errorhandler(CSRFError)
    def csrf_failed(error):
        return error_response(
            400, "Invalid or missing CSRF token", "Reload the page and submit the form again."
        )

    @app.errorhandler(500)
    def server_error(error):
        db.session.rollback()
        return error_response(
            500, "Internal server error", "The request failed. The error is in the server log."
        )
