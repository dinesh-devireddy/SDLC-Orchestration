from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.exceptions import HTTPException

from .config import Settings
from .database import check_ready, make_engine
from .errors import ServiceError
from .schemas import CreateURL, ErrorResponse, URLInfo
from .service import create_link, generate_code, get_stats, redirect, utc_now


def create_app(settings=None, clock=utc_now, code_factory=generate_code):
    settings = settings or Settings.from_env()
    engine = make_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        try:
            check_ready(engine, settings)
        except Exception:
            engine.dispose()
            raise RuntimeError("Database not ready. Run python -m shortener init-db; check path and permissions.") from None
        try:
            yield
        finally:
            engine.dispose()

    app = FastAPI(title="Local URL Shortener", version="0.1.0", lifespan=lifespan,
                  responses={status: {"model": ErrorResponse} for status in (404, 405, 409, 410, 422, 500, 503)})

    def session_scope():
        with Session(engine, expire_on_commit=False) as session:
            try:
                yield session
            finally:
                session.rollback()

    def error(status, code, message, headers=None):
        return JSONResponse(status_code=status, content={"error": {"code": code, "message": message}}, headers=headers)

    @app.exception_handler(ServiceError)
    async def service_error(request, exc):
        return error(exc.status, exc.code, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return error(422, "validation_error", "Invalid request; check the API schema and input constraints")

    @app.exception_handler(HTTPException)
    async def http_error(request, exc):
        return error(exc.status_code, "http_error", str(exc.detail), exc.headers)

    @app.exception_handler(SQLAlchemyError)
    async def database_error(request, exc):
        return error(503, "database_unavailable", "Database unavailable; retry later")

    @app.exception_handler(Exception)
    async def unexpected_error(request, exc):
        return error(500, "internal_error", "An unexpected error occurred")

    def info(link):
        return URLInfo(code=link.code, short_url=f"{settings.public_base_url}/{link.code}",
                       destination=link.destination, created_at=link.created_at,
                       expires_at=link.expires_at, clicks=link.clicks)

    web_root = Path(__file__).parent / "web"
    ui_headers = {
        "Content-Security-Policy": "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'self'; frame-ancestors 'none'",
        "X-Content-Type-Options": "nosniff",
        "Referrer-Policy": "no-referrer",
        "Cache-Control": "no-store",
    }

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(web_root / "index.html", headers=ui_headers)

    @app.get("/api/ui/app.css", include_in_schema=False)
    def ui_styles():
        return FileResponse(web_root / "app.css", headers=ui_headers)

    @app.get("/api/ui/app.js", include_in_schema=False)
    def ui_script():
        return FileResponse(web_root / "app.js", headers=ui_headers)

    @app.get("/health")
    def health():
        try:
            check_ready(engine, settings)
        except Exception:
            raise ServiceError(503, "database_unavailable", "Database is not ready") from None
        return {"status": "ok", "database": "ready"}

    @app.post("/api/urls", status_code=201, response_model=URLInfo)
    def create(request: CreateURL, session: Session = Depends(session_scope)):
        return info(create_link(session, request, clock, code_factory))

    @app.get("/api/urls/{code}/stats", response_model=URLInfo)
    def stats(code: str, session: Session = Depends(session_scope)):
        return info(get_stats(session, code))

    @app.get("/{code}", status_code=302, response_class=RedirectResponse)
    def follow(code: str, session: Session = Depends(session_scope)):
        return RedirectResponse(redirect(session, code, clock), status_code=302,
                                headers={"Cache-Control": "no-store"})

    return app
