"""FastAPI application entry point."""

from contextlib import asynccontextmanager
from collections.abc import AsyncIterator

from fastapi import FastAPI

from app.api.routes.auth import router as auth_router
from app.api.routes.health import router as health_router
from app.api.routes.items import router as items_router
from app.api.routes.interactions import router as interactions_router
from app.api.routes.users import router as users_router
from app.core.config import SecuritySettings


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    """Refuse to start authentication without a configured JWT secret."""
    SecuritySettings.from_env()
    yield

app = FastAPI(
    title="Technical Support Knowledge Base Platform",
    version="0.1.0",
    lifespan=lifespan,
)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(items_router)
app.include_router(interactions_router)
