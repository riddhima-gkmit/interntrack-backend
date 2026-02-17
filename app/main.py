"""InternTrack API entry point: FastAPI app, lifespan, middleware, exception handlers, and router mounting."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.exc import IntegrityError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.config import settings
from app.config.logging_config import setup_logging
from app.middleware.request_logging import RequestLoggingMiddleware
from app.routers import auth, comments, dashboard, leaves, tasks, tenants, users
from app.utils.exception_handlers import (
    db_exception_handler,
    global_exception_handler,
    http_exception_handler,
    validation_exception_handler,
)
from app.utils.redis_client import redis_client

# Run once at import time so all loggers use the same format and level.
setup_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup: verify Redis (fail fast if unavailable). Shutdown: close Redis connection."""
    try:
        await redis_client.get_client().ping()
    except Exception as e:
        # Fail on startup so OTP and rate limiting don't run with a broken Redis.
        raise RuntimeError(f"Redis connection failed: {e}") from e
    yield
    await redis_client.close()


app = FastAPI(
    title="InternTrack API",
    description="Multi-tenant internship task tracking platform",
    version="1.0.0",
    lifespan=lifespan,
)

# Middleware: last added runs first on request (so RequestLoggingMiddleware runs first, then CORS).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(RequestLoggingMiddleware)

# All handlers return unified format: { success: false, error: { code, message [, details] } }
app.add_exception_handler(IntegrityError, db_exception_handler)  # DB constraint violations → 400
app.add_exception_handler(StarletteHTTPException, http_exception_handler)  # raise HTTPException in code
app.add_exception_handler(RequestValidationError, validation_exception_handler)  # Pydantic / request validation
app.add_exception_handler(Exception, global_exception_handler)  # Catch-all → 500, log traceback


@app.get("/health")
async def health():
    """Health check for deployment and load balancers. No auth required."""
    return {"status": "ok"}


# All API routes under /api/v1; comments and dashboard are nested under tasks and users.
api_v1 = APIRouter(prefix="/api/v1")
api_v1.include_router(auth.router)
api_v1.include_router(tenants.router)
api_v1.include_router(users.router)
api_v1.include_router(tasks.router)
api_v1.include_router(comments.router, prefix="/tasks")  # e.g. /api/v1/tasks/{task_id}/comments/
api_v1.include_router(dashboard.router, prefix="/users")  # e.g. /api/v1/users/{user_id}/dashboard/
api_v1.include_router(leaves.router)
app.include_router(api_v1)
