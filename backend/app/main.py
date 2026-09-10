from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.sessions import SessionMiddleware

from app.api import analytics, auth, interviews, resumes, settings as settings_api, tickets, users, voice
from app.api import notifications
from app.core.config import settings
from app.core.security import decode_access_token
from app.db.session import Base, SessionLocal, engine
from app.models import interview as interview_model  # noqa: F401  (registers the tables)
from app.models import notification as notification_model  # noqa: F401  (registers the table)
from app.models import recording as recording_model  # noqa: F401  (registers the tables)
from app.models import resume as resume_model  # noqa: F401  (registers the table)
from app.models import setting as setting_model  # noqa: F401  (registers the table)
from app.models import ticket as ticket_model  # noqa: F401  (registers the table)
from app.models import user as user_model  # noqa: F401  (registers the table)
from app.services import ai_provider
from app.services.metrics import metrics, timing_middleware

# Fine for coursework. Use Alembic migrations for anything real.
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title=settings.PROJECT_NAME,
    description="SmartHire AI — authentication, résumés, interviews and analytics.",
    openapi_url=f"{settings.API_PREFIX}/openapi.json",
)

# Paths that must keep working while the platform is in maintenance, so an
# administrator can always sign in and turn it back off.
_MAINTENANCE_EXEMPT = (
    f"{settings.API_PREFIX}/health",
    f"{settings.API_PREFIX}/auth/",
    f"{settings.API_PREFIX}/settings",
    f"{settings.API_PREFIX}/openapi.json",
    "/docs",
    "/redoc",
    "/",
)


@app.middleware("http")
async def maintenance_gate(request: Request, call_next):
    """
    When an administrator enables maintenance, non-admin API calls are refused.

    Administrators are always exempt, so enabling it cannot lock you out.
    """
    path = request.url.path
    if request.method == "OPTIONS" or path.startswith(_MAINTENANCE_EXEMPT):
        return await call_next(request)

    db = SessionLocal()
    try:
        from app.models.setting import get_settings

        if not get_settings(db).maintenance:
            return await call_next(request)

        # Maintenance is on — let administrators through, refuse everyone else.
        header = request.headers.get("authorization", "")
        if header.lower().startswith("bearer "):
            payload = decode_access_token(header.split(" ", 1)[1])
            if payload and payload.get("role") == "ADMIN":
                return await call_next(request)
    finally:
        db.close()

    return JSONResponse(
        status_code=503,
        content={"detail": "The platform is in maintenance mode. Please try again later."},
    )


# Registered after the maintenance gate so it runs first and therefore times
# the whole request, including any maintenance rejection.
app.middleware("http")(timing_middleware)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Response-Time-ms"],
)

# Authlib stores the OAuth state here between the redirect and the callback.
app.add_middleware(SessionMiddleware, secret_key=settings.JWT_SECRET_KEY)

app.include_router(auth.router, prefix=settings.API_PREFIX)
app.include_router(users.router, prefix=settings.API_PREFIX)
app.include_router(interviews.router, prefix=settings.API_PREFIX)
app.include_router(voice.router, prefix=settings.API_PREFIX)
app.include_router(resumes.router, prefix=settings.API_PREFIX)
app.include_router(analytics.router, prefix=settings.API_PREFIX)
app.include_router(tickets.router, prefix=settings.API_PREFIX)
app.include_router(settings_api.router, prefix=settings.API_PREFIX)
app.include_router(notifications.router, prefix=settings.API_PREFIX)


@app.get("/")
def read_root():
    return {"status": "online", "service": settings.PROJECT_NAME, "docs": "/docs"}


@app.get(f"{settings.API_PREFIX}/health")
def health_check():
    dialect = engine.dialect.name
    return {
        "status": "healthy",
        "database": dialect,
        "google_login": settings.google_enabled,
        "github_login": settings.github_enabled,
        # Which provider is live, its model, and whether it can actually be
        # reached — a stopped local Ollama shows up here rather than as a
        # mysterious 503 on the first upload.
        "ai": ai_provider.provider_status(),
        # Kept for the admin panel and older clients.
        "ai_enabled": settings.ai_enabled,
        "ai_model": ai_provider.active_model(),
        "metrics_since": metrics.window_start.isoformat(),
    }
