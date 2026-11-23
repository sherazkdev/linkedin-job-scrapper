from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import health, internal_ops
from app.core.config import get_settings
from app.core.exceptions import register_exception_handlers
from app.core.lifespan import lifespan
from app.core.middleware import SecurityHeadersMiddleware
from app.modules.alerts import routes as alerts_routes
from app.modules.jobs.routes import countries, jobs


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="Global Jobs API",
        version="0.2.0",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.add_middleware(SecurityHeadersMiddleware)
    origins = [o.strip() for o in (settings.api_cors_origins or "").split(",") if o.strip()]
    if origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=origins,
            allow_credentials=True,
            allow_methods=["GET", "HEAD", "OPTIONS", "POST", "PATCH", "DELETE"],
            allow_headers=["*"],
        )
    app.include_router(health.router)
    app.include_router(jobs.router)
    app.include_router(countries.router)
    if settings.alerts_api_enabled:
        app.include_router(alerts_routes.router)
    app.include_router(internal_ops.router)
    return app


app = create_app()
