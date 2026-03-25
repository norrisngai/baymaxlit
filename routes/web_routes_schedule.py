"""Student schedule routes.

This file is intentionally kept as the public entrypoint (imported by web_app.py).
The implementation is split into:
- web_routes_schedule_views.py: HTML views (month/week/day)
- web_routes_schedule_api.py: JSON APIs (manual CRUD, generate, chat, study guide)

All URLs and behaviors remain the same.
"""

from __future__ import annotations

from flask import Flask

from routes import web_routes_schedule_api
from routes import web_routes_schedule_views


def register(app: Flask) -> None:
    web_routes_schedule_views.register(app)
    web_routes_schedule_api.register(app)
