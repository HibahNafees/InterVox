from flask import Flask, jsonify
from flask_cors import CORS

from .config import Config
from .extensions import db, jwt, migrate


def _sqlite_foreign_keys(app: Flask) -> None:
    """Tests run on SQLite: enforce foreign keys (and ON DELETE) like MySQL does."""
    from sqlalchemy import event

    with app.app_context():
        event.listen(
            db.engine,
            "connect",
            lambda conn, _record: conn.execute("PRAGMA foreign_keys=ON"),
        )


def _check_production(app: Flask) -> None:
    """Refuse to start in production with settings that would be unsafe."""
    problems = []
    for key in ("SECRET_KEY", "JWT_SECRET_KEY"):
        if len(app.config.get(key) or "") < 32:
            problems.append(f"{key} must be a random string of 32+ characters")
    if not app.config.get("FIRE_API_KEY"):
        problems.append("FIRE_API_KEY is not set")
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        problems.append("DATABASE_URL must point at MySQL, not SQLite")
    origins = app.config.get("CORS_ORIGINS") or []
    if not origins or any(o == "*" or "localhost" in o for o in origins):
        problems.append("CORS_ORIGINS must list the real frontend URL(s)")
    if app.debug:
        problems.append("debug mode must be off")
    if problems:
        raise RuntimeError("Unsafe production settings: " + "; ".join(problems))


def create_app(config_class: type[Config] = Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_class)

    for key in ("SECRET_KEY", "JWT_SECRET_KEY", "SQLALCHEMY_DATABASE_URI"):
        if not app.config.get(key):
            raise RuntimeError(f"{key} is not set; copy .env.example to .env")
    if app.config.get("APP_ENV") == "production":
        _check_production(app)
    if app.config.get("TRUST_PROXY"):
        from werkzeug.middleware.proxy_fix import ProxyFix

        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)

    db.init_app(app)
    if app.config["SQLALCHEMY_DATABASE_URI"].startswith("sqlite"):
        _sqlite_foreign_keys(app)
    migrate.init_app(app, db)
    jwt.init_app(app)
    CORS(app, origins=app.config["CORS_ORIGINS"])

    from . import models  # noqa: F401  (register tables with SQLAlchemy)
    from .routes.admin import bp as admin_bp
    from .routes.auth import bp as auth_bp
    from .routes.common import register_error_handlers
    from .routes.company import bp as company_bp
    from .routes.debriefs import bp as debriefs_bp
    from .routes.demo import bp as demo_bp
    from .routes.decoder import bp as decoder_bp
    from .routes.documents import bp as documents_bp
    from .routes.health import bp as health_bp
    from .routes.lab import bp as lab_bp
    from .routes.orgs import bp as orgs_bp
    from .routes.reports import bp as reports_bp
    from .routes.reports import shared_bp
    from .routes.reverse import bp as reverse_bp
    from .routes.sessions import bp as sessions_bp
    from .routes.stats import bp as stats_bp
    from .routes.stories import bp as stories_bp

    app.register_blueprint(health_bp, url_prefix="/api")
    app.register_blueprint(stats_bp, url_prefix="/api")
    app.register_blueprint(decoder_bp, url_prefix="/api/decoder")
    app.register_blueprint(debriefs_bp, url_prefix="/api/debriefs")
    app.register_blueprint(reverse_bp, url_prefix="/api/reverse")
    app.register_blueprint(company_bp, url_prefix="/api/company")
    app.register_blueprint(stories_bp, url_prefix="/api/stories")
    app.register_blueprint(lab_bp, url_prefix="/api/lab")
    app.register_blueprint(auth_bp, url_prefix="/api/auth")
    app.register_blueprint(admin_bp, url_prefix="/api/admin")
    app.register_blueprint(demo_bp, url_prefix="/api/demo")
    app.register_blueprint(orgs_bp, url_prefix="/api/orgs")
    app.register_blueprint(documents_bp, url_prefix="/api/documents")
    app.register_blueprint(sessions_bp, url_prefix="/api/sessions")
    app.register_blueprint(reports_bp, url_prefix="/api/sessions")
    app.register_blueprint(shared_bp, url_prefix="/api/shared")
    register_error_handlers(app)

    @app.cli.command("purge-expired")
    def purge_expired():
        """Delete documents past their 30-day retention (run daily)."""
        from .services.privacy import purge_expired_documents

        print(f"Deleted {purge_expired_documents()} expired documents")

    @app.cli.command("demo-reset")
    def demo_reset():
        """Delete and re-seed the fictional demo org (no Fire calls; run nightly)."""
        from .services.demo import reset

        counts = reset()
        print("Demo reset: " + ", ".join(f"{v} {k}" for k, v in counts.items()))

    @jwt.unauthorized_loader
    def missing_token(reason: str):
        return jsonify(error="Please log in"), 401

    @jwt.invalid_token_loader
    def invalid_token(reason: str):
        return jsonify(error="Your session is invalid; please log in again"), 401

    @jwt.expired_token_loader
    def expired_token(_header, _payload):
        return jsonify(error="Your session expired; please log in again"), 401

    # A token outlives a deleted account (Delete my data) unless the user is looked
    # up on every request: it was still accepted and could start Fire work (T-125).
    @jwt.user_lookup_loader
    def load_user(_header, payload):
        from .models import User
        from .services.access import demo_token_ok

        user = db.session.get(User, int(payload["sub"]))
        # A demo account (T-166) is usable only through an admin's View as.
        if user is not None and not demo_token_ok(user, payload):
            return None
        return user

    @jwt.user_lookup_error_loader
    def missing_user(_header, _payload):
        return jsonify(error="Your account no longer exists; please log in again"), 401

    @app.errorhandler(404)
    def not_found(_err):
        return jsonify(error="Not found"), 404

    @app.errorhandler(413)
    def too_large(_err):
        return jsonify(error="That upload is too large"), 413

    @app.errorhandler(405)
    def method_not_allowed(_err):
        return jsonify(error="Method not allowed"), 405

    @app.errorhandler(500)
    def server_error(_err):
        return jsonify(error="Something went wrong on our side; please try again"), 500

    return app
