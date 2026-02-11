"""Flask app factory for CabinetForge."""

from __future__ import annotations

from flask import Flask

from .config import build_config
from .routes import build_blueprint
from .workspace import WorkspaceManager


def create_app() -> Flask:
    """Create and configure the Flask app instance."""

    cfg = build_config()

    app = Flask(
        __name__,
        static_folder="../static",
        template_folder="../templates",
    )
    app.config["SECRET_KEY"] = cfg.secret_key
    app.config["MAX_CONTENT_LENGTH"] = cfg.max_content_length
    app.config["CABINETFORGE_UPLOAD_DIR"] = cfg.upload_dir
    app.config["CABINETFORGE_EXTRACT_DIR"] = cfg.extract_dir

    app.extensions["workspace_manager"] = WorkspaceManager(cfg.session_ttl_seconds)
    app.register_blueprint(build_blueprint())
    return app
