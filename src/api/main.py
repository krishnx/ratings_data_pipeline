import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from api.config import settings
from api.db.session import SessionLocal
from api.pipeline.runner import run_pipeline
from api.routers import companies, snapshots, uploads

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format='{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","message":"%(message)s"}',
)
log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    log.info("Starting pipeline run on DATA_DIR=%s", settings.data_dir)
    try:
        result = run_pipeline(settings.data_dir, SessionLocal)
        log.info("Pipeline finished: processed=%d skipped=%d failed=%d",
                 result["files_processed"], result["files_skipped"], result["files_failed"])
    except Exception as exc:
        log.exception("Pipeline failed at startup: %s", exc)
    yield


app = FastAPI(
    title="Corporate Credit Rating Data Pipeline",
    description="Extracts, validates, and serves corporate credit rating data from .xlsm files.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(companies.router)
app.include_router(snapshots.router)
app.include_router(uploads.router)


@app.get("/health", summary="Health check", tags=["health"])
def health_check():
    from sqlalchemy import text

    try:
        session = SessionLocal()
        session.execute(text("SELECT 1"))
        session.close()
        db_status = "connected"
    except Exception:
        db_status = "error"
    return {"status": "ok", "db": db_status}


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    log.exception("Unhandled exception: %s", exc)
    return JSONResponse(
        status_code=500,
        content={"error": "internal_server_error", "detail": str(exc), "status_code": 500},
    )
