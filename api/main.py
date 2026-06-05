"""
FastAPI application entry point.

This module initializes the FastAPI application with all routes, middleware,
and lifespan management for database and Redis connections.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .config import settings
from .database import DatabasePool
from .redis.client import RedisPool
from .redis.events import start_event_subscriber

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

    Handles startup and shutdown of database and Redis connections.
    """
    logger.info("Starting API server")

    # Startup: Create database pool
    try:
        app.state.db_pool = await DatabasePool.create_pool()
        logger.info("Database pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize database pool: {e}")
        raise

    # Initialize Redis pool
    try:
        app.state.redis_pool = await RedisPool.create_pool()
        logger.info("Redis pool initialized")
    except Exception as e:
        logger.error(f"Failed to initialize Redis pool: {e}")
        raise

    # Start Redis event subscriber
    app.state.event_subscriber_task = asyncio.create_task(
        start_event_subscriber(app.state.redis_pool)
    )

    logger.info("API server startup complete")

    yield

    # Shutdown: Clean up resources
    logger.info("Shutting down API server")

    # Cancel Redis subscriber task
    if hasattr(app.state, "event_subscriber_task"):
        app.state.event_subscriber_task.cancel()
        try:
            await app.state.event_subscriber_task
        except asyncio.CancelledError:
            logger.info("Event subscriber cancelled")

    # Close Redis pool
    if hasattr(app.state, "redis_pool"):
        await RedisPool.close_pool()

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

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
from .auth.routes import router as auth_router
from .routes.health import router as health_router
from .routes.runs import router as runs_router
from .routes.trades import router as trades_router
from .routes.signals import router as signals_router
from .routes.orders import router as orders_router
from .routes.weights import router as weights_router
from .routes.optimizations import router as optimizations_router
from .routes.config import router as config_router

app.include_router(health_router, tags=["health"])
app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(runs_router, prefix="/runs", tags=["runs"])
app.include_router(trades_router, prefix="/trades", tags=["trades"])
app.include_router(signals_router, prefix="/signals", tags=["signals"])
app.include_router(orders_router, prefix="/orders", tags=["orders"])
app.include_router(weights_router, prefix="/weights", tags=["weights"])
app.include_router(optimizations_router, prefix="/optimizations", tags=["optimizations"])
app.include_router(config_router, prefix="/config", tags=["config"])


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
