"""Health check endpoints."""

from fastapi import APIRouter

from src.api.state import get_app_state
from src.infrastructure.config import get_settings

router = APIRouter()


@router.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}


@router.get("/health/detailed")
async def detailed_health_check():
    """Detailed health check with component status."""
    settings = get_settings()
    state = get_app_state()

    agents = []
    if state.orchestrator:
        agents = state.orchestrator.get_agent_status()

    return {
        "status": "healthy",
        "environment": settings.app_env,
        "components": {
            "azure_openai": {
                "configured": settings.azure_openai_configured,
                "deployment": settings.azure_openai_deployment_name if settings.azure_openai_configured else None,
            },
            "azure_search": {
                "configured": settings.azure_search_configured,
                "index": settings.azure_search_index_name if settings.azure_search_configured else None,
            },
            "document_grounding": {
                "enabled": state.grounding_enabled,
            },
        },
        "agents": agents,
    }
