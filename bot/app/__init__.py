from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from flask import Flask


def create_app() -> "Flask":
    from flask import Flask

    from app.config import configure_logging, load_configurations
    from app.views import webhook_blueprint

    app = Flask(__name__)

    # Load configurations and logging settings
    load_configurations(app)
    configure_logging()

    # Import and register blueprints, if any
    app.register_blueprint(webhook_blueprint)

    return app
