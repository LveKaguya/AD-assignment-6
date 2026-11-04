"""Health check route."""

from typing import TypedDict

from fastapi import APIRouter


class HealthResponse(TypedDict):
    """Response shape for the health check."""

    status: str


router = APIRouter()


@router.get("/health", response_model=HealthResponse)
def get_health() -> HealthResponse:
    """Return a simple success response without checking external services."""
    return {"status": "ok"}
