"""web_app.py

Local web app (no Telegram):
- Login system
- Student vs Teacher roles
- Student onboarding at signup: name, class, interests (checkboxes, up to 8)
- Chat UI with multiple chat threads (each thread has its own chat_id)

Run:
  python web_app.py
Open:
  http://127.0.0.1:5000

Dependencies:
  pip install flask
"""

from __future__ import annotations

import os
import threading
import time
from flask import Flask

import web_context
import web_db
from routes import web_routes_activities
from routes import web_routes_auth
from routes import web_routes_chat
from routes import web_routes_core
from routes import web_routes_financial_aid
from routes import web_routes_google
from routes import web_routes_notebook
from routes import web_routes_notifications
from routes import web_routes_profile
from routes import web_routes_quiz
from routes import web_routes_revision
from routes import web_routes_schedule
from routes import web_routes_check_work
from routes import web_routes_study_timer
from routes import web_routes_teacher

try:
    import local_secrets  # type: ignore
except Exception:
    local_secrets = None

try:
    from google import genai
    from google.genai import types
except Exception:  # pragma: no cover
    genai = None
    types = None


def _create_app() -> Flask:
    app = Flask(__name__)
    app.secret_key = os.environ.get("BAYMAX_WEB_SECRET", "dev-secret-change-me")

    # Ensure the SQLite schema exists in both local runs and WSGI deployment.
    web_db.init_db()

    # Attachment uploads exposes a request body; keep it bounded.
    try:
        app.config["MAX_CONTENT_LENGTH"] = int(os.environ.get("MAX_UPLOAD_BYTES", "10485760"))
    except Exception:
        app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

    google_key = os.environ.get("GOOGLE_GEMINI_API_KEY")
    if not google_key and local_secrets is not None:
        google_key = getattr(local_secrets, "GOOGLE_GEMINI_API_KEY", None)
    model_name = os.environ.get("GEMINI_MODEL", "models/gemini-2.5-flash-lite")

    client = None
    if genai and google_key:
        try:
            client = genai.Client(api_key=google_key)
        except Exception:
            client = None

    app.config["GEMINI_CLIENT"] = client
    app.config["GEMINI_TYPES"] = types
    app.config["GEMINI_MODEL_NAME"] = model_name
    # Notebook routes may use a higher-tier model if explicitly configured,
    # but default to the working base model to avoid region/quota failures.
    app.config["GEMINI_PRO_MODEL_NAME"] = os.environ.get("GEMINI_PRO_MODEL", model_name)
    # Image generation model for mind maps
    app.config["GEMINI_IMAGE_MODEL_NAME"] = os.environ.get("GEMINI_IMAGE_MODEL", "gemini-3.1-flash-image-preview")

    @app.context_processor
    def _inject_globals():
        return {"nav_user": web_context.current_user()}

    web_routes_core.register(app)
    web_routes_auth.register(app)
    web_routes_chat.register(app)
    web_routes_profile.register(app)
    web_routes_revision.register(app)
    web_routes_quiz.register(app)
    web_routes_teacher.register(app)
    web_routes_activities.register(app)
    web_routes_financial_aid.register(app)
    web_routes_notebook.register(app)
    web_routes_schedule.register(app)
    web_routes_study_timer.register(app)
    web_routes_check_work.register(app)
    web_routes_google.register(app)
    web_routes_notifications.register(app)

    return app


app = _create_app() 


def _notification_checker():
    """Background thread to check for deadline notifications + housekeeping every hour."""
    while True:
        try:
            time.sleep(3600)  # Check every hour
            count = web_db.check_and_create_deadline_notifications()
            if count > 0:
                print(f"Created {count} new deadline notifications")

            # Housekeeping: prune assignments whose deadline is >7 days past.
            try:
                pruned_ids = web_db.prune_expired_assignments(days_past=7)
                if pruned_ids:
                    print(f"Auto-deleted {len(pruned_ids)} expired assignment(s)")
            except Exception as prune_e:
                print(f"Assignment auto-prune failed: {prune_e}")
        except Exception as e:
            print(f"Notification checker error: {e}")


if __name__ == "__main__":
    # Start notification checker thread
    notification_thread = threading.Thread(target=_notification_checker, daemon=True)
    notification_thread.start()

    app.run(
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5000")),
        debug=os.environ.get("FLASK_DEBUG", "1") == "1",
    )
