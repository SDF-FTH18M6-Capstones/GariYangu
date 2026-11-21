import os
from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, jsonify, send_from_directory
from flask_cors import CORS
from werkzeug.exceptions import HTTPException

from .auth import ApiError
from .extensions import bcrypt, db, jwt

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


def _rename_kra_column():
    
    insp = db.inspect(db.engine)
    if insp.has_table("dealer_profiles"):
        cols = {c["name"] for c in insp.get_columns("dealer_profiles")}
        if "kra_pin" in cols and "id_number" not in cols:
            db.session.execute(db.text("ALTER TABLE dealer_profiles RENAME COLUMN kra_pin TO id_number"))
            db.session.commit()


def create_app(overrides=None):
    from .config import Config

    app = Flask(__name__, static_folder=None)
    app.config.from_object(Config)
    app.config.update(overrides or {})
    app.config.setdefault("JWT_SECRET_KEY", app.config["SECRET_KEY"])
    if overrides and "SECRET_KEY" in overrides and "JWT_SECRET_KEY" not in overrides:
        app.config["JWT_SECRET_KEY"] = app.config["SECRET_KEY"]
    from .config import check_production
    check_production(app.config)

    db.init_app(app)
    jwt.init_app(app)
    bcrypt.init_app(app)
    CORS(app, resources={r"/api/*": {"origins": app.config["CORS_ORIGINS"]}})

    from .routes import admin, auth, buyer, cars, dealer
    for m in (auth, cars, buyer, dealer, admin):
        app.register_blueprint(m.bp)

    @app.get("/uploads/<path:filename>")
    def uploaded_file(filename):
        return send_from_directory(app.config["UPLOAD_FOLDER"], filename, max_age=3600)

    @app.get("/api/health")
    def health():
        try:
            db.session.execute(db.text("SELECT 1"))
        except Exception:
            return jsonify(status="error", database="unreachable"), 503
        return jsonify(status="ok", database="ok")

    @app.after_request
    def security_headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return resp

    @app.errorhandler(ApiError)
    def api_error(e):
        return jsonify(error=e.message), e.status

    @app.errorhandler(HTTPException)
    def http_error(e):
        return jsonify(error=e.description), e.code

    @app.errorhandler(Exception)
    def unhandled(e):
        app.logger.exception(e)
        db.session.rollback()
        return jsonify(error="Something went wrong on the server."), 500

    
    if DIST.is_dir():
        @app.get("/", defaults={"path": ""})
        @app.get("/<path:path>")
        def spa(path):
            if path.startswith("api/"):
                return jsonify(error="Not found."), 404
            f = DIST / path
            return send_from_directory(DIST, path if path and f.is_file() else "index.html")

    with app.app_context():
        _rename_kra_column()
        db.create_all()
        from .models import User
    
        want_demo = app.config.get("APP_ENV") != "production" or os.environ.get("SEED_DEMO_DATA") == "1"
        if want_demo and not app.config.get("TESTING") and User.query.count() == 0:
            from .seed import seed
            seed()

    @app.cli.command("seed")
    def seed_cmd():
        """Wipe the database and load demo data."""
        from .seed import reset_and_seed
        reset_and_seed()
        print("Database reset and seeded.")

    return app
