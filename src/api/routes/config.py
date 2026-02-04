"""Configuration API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.api.state import get_app_state
from src.infrastructure.config import get_settings

router = APIRouter()


class GroundingConfig(BaseModel):
    """Configuration for document grounding."""

    enabled: bool = Field(..., description="Whether document grounding is enabled")


class AppConfig(BaseModel):
    """Full application configuration."""

    grounding_enabled: bool
    azure_openai_configured: bool
    azure_search_configured: bool
    environment: str


@router.get("/", response_model=AppConfig)
async def get_configuration():
    """Get current application configuration."""
    settings = get_settings()
    state = get_app_state()

    return AppConfig(
        grounding_enabled=state.grounding_enabled,
        azure_openai_configured=settings.azure_openai_configured,
        azure_search_configured=settings.azure_search_configured,
        environment=settings.app_env,
    )


@router.get("/grounding", response_model=GroundingConfig)
async def get_grounding_config():
    """Get document grounding configuration."""
    state = get_app_state()
    return GroundingConfig(enabled=state.grounding_enabled)


@router.put("/grounding", response_model=GroundingConfig)
async def set_grounding_config(config: GroundingConfig):
    """Enable or disable document grounding.

    When enabled, agents will use Azure AI Search to ground their
    responses in bank documentation.
    """
    state = get_app_state()
    settings = get_settings()

    # Check if Azure Search is configured when trying to enable
    if config.enabled and not settings.azure_search_configured:
        # Allow enabling with mock data for demo
        pass  # Mock search will be used

    state.grounding_enabled = config.enabled

    return GroundingConfig(enabled=state.grounding_enabled)


@router.post("/reload-data")
async def reload_mock_data():
    """Reload mock data from CSV files.

    Useful during demos when CSV files have been modified.
    """
    state = get_app_state()

    if state.customer_repository:
        state.customer_repository.reload()
        return {"status": "success", "message": "Mock data reloaded"}

    raise HTTPException(status_code=503, detail="Customer repository not initialized")
