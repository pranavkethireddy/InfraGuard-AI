"""FastAPI entry point. Run from the repository root:

    python -m uvicorn backend.app.main:app --reload --port 8000
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.v1 import health
from .api.v1.router import api_router
from .core.config import APP_VERSION, Settings, get_settings
from .core.errors import REQUEST_ID_HEADER, install_error_handlers
from .services.store import Store


def _app_logging() -> None:
    """Show backend.* INFO logs (Gemini retries, fallbacks, live-loop errors) next to uvicorn's."""
    log = logging.getLogger("backend")
    if not log.handlers:
        h = logging.StreamHandler()
        h.setFormatter(logging.Formatter("%(levelname)s:     %(name)s: %(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    _app_logging()
    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if settings.live_autostart:
            from .schemas.fleet import LiveStartRequest
            from .services import live

            live.start(app.state.store, LiveStartRequest(), settings)
            yield
            live.stop(app.state.store, settings)
        else:
            yield

    app = FastAPI(title="InfraGuard AI API", version=APP_VERSION, lifespan=lifespan)
    app.state.store = Store()
    install_error_handlers(app)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_methods=["GET", "POST", "PATCH", "OPTIONS"],
        allow_headers=["Content-Type", REQUEST_ID_HEADER],
        expose_headers=[REQUEST_ID_HEADER],
    )
    app.include_router(health.router)
    app.include_router(api_router)
    return app


app = create_app()
