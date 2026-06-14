"""
FastAPI application entry point.

This module initializes the FastAPI application with all routes, middleware,
and lifespan management for database connections.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from .config import settings
from .database import DatabasePool
from .db_config import apply_db_config_to_settings
from .limiter import limiter
from .middleware.security_headers import SecurityHeadersMiddleware

# Setup logging
logging.basicConfig(
    level=getattr(logging, settings.log_level.upper()),
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    if settings.log_format == "text"
    else None,
)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    FastAPI lifespan context manager.

    Handles startup and shutdown of database connections.
    """
    logger.info("Starting API server")

    # Startup: Create database pool
    try:
        app.state.db_pool = await DatabasePool.create_pool()
        logger.info("Database pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

    # Load persisted configuration from database
    try:
        await apply_db_config_to_settings(app.state.db_pool, settings)
        logger.info("Configuration loaded from database")
    except Exception as e:
        logger.warning(f"Failed to load configuration from database: {e}. Using defaults.")

    logger.info("API server startup complete")

    yield

    # Shutdown: Clean up resources
    logger.info("Shutting down API server")

    # Close database pool
    if hasattr(app.state, "db_pool"):
        await DatabasePool.close_pool()
        logger.info("Database pool closed")

    logger.info("API server shutdown complete")


# Create FastAPI application
app = FastAPI(
    title="Trading Bot API",
    description="FastAPI backend for crypto trading bot",
    version="1.0.0",
    lifespan=lifespan,
)

# Configure rate limiting
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Generic error handler (prevents information disclosure in production)
@app.exception_handler(Exception)
async def generic_exception_handler(request: Request, exc: Exception):
    """
    Handle all unhandled exceptions.

    In production: Returns generic error message (prevents information disclosure)
    In development: Returns full error details for debugging
    """
    # Log full error server-side (always)
    logger.error(f"Unhandled exception: {exc}", exc_info=True)

    # Return different messages based on environment
    if settings.environment == "prod":
        # Production: Generic error (no details leaked to client)
        return JSONResponse(
            status_code=500,
            content={"detail": "An internal error occurred"}
        )
    else:
        # Development: Full error for debugging
        return JSONResponse(
            status_code=500,
            content={
                "detail": str(exc),
                "type": type(exc).__name__
            }
        )

# Add security headers middleware
app.add_middleware(SecurityHeadersMiddleware)

# Configure CORS
# Security: Explicitly list allowed methods and headers (no wildcards)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,  # Exact domains from .env (no wildcards in production)
    allow_credentials=True,  # Required for httpOnly cookies
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],  # Explicit methods only
    allow_headers=["Content-Type", "Authorization", "X-CSRF-Token"],  # Explicit headers only
    expose_headers=["Content-Length", "Content-Type"],
    max_age=3600,  # Cache preflight requests for 1 hour
)

# Include routers
from .auth.routes import router as auth_router
from .auth.oidc_routes import router as oidc_router
from .routes.health import router as health_router
from .routes.runs import router as runs_router
from .routes.trades import router as trades_router
from .routes.signals import router as signals_router
from .routes.orders import router as orders_router
from .routes.weights import router as weights_router
from .routes.optimizations import router as optimizations_router
from .routes.config import router as config_router
from .routes.logs import router as logs_router

app.include_router(health_router, tags=["health"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(oidc_router, prefix="/auth/oidc", tags=["auth"])
app.include_router(runs_router, prefix="/runs", tags=["runs"])
app.include_router(trades_router, prefix="/trades", tags=["trades"])
app.include_router(signals_router, prefix="/signals", tags=["signals"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])
app.include_router(weights_router, prefix="/weights", tags=["weights"])
app.include_router(optimizations_router, prefix="/optimizations", tags=["optimizations"])
app.include_router(config_router, prefix="/config", tags=["config"])
app.include_router(logs_router, prefix="/logs", tags=["errors"])


@app.get("/")
async def root():
    """Root endpoint."""
    return {
        "message": "Trading Bot API",
        "version": "1.0.0",
        "environment": settings.environment,
        "status": "online",
    }


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload,
        log_level=settings.log_level.lower(),
    )
