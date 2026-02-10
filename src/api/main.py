"""FastAPI application for KYC demo."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import chat, config, documents, health
from src.api.state import AppState, get_app_state, reset_app_state
from src.infrastructure.config import get_settings, clear_settings_cache

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler for startup/shutdown."""
    # Clear settings cache to reload from .env
    clear_settings_cache()
    
    settings = get_settings()
    logger.info(f"Starting AI-KYC application in {settings.app_env} mode")
    logger.info(f"Azure OpenAI: {settings.azure_openai_endpoint} / {settings.azure_openai_deployment_name}")

    # Reset state to ensure clean start (clears chat history)
    reset_app_state()
    
    # Initialize application state
    state = get_app_state()
    await state.initialize()

    logger.info("Application initialized successfully (chat history cleared)")
    logger.info(f"Registered agents: {[a.name for a in state.registry.get_all()]}")
    logger.info(f"Document grounding enabled: {settings.enable_document_grounding}")
    
    # Log available plugins for each agent
    for agent in state.registry.get_all():
        plugins = list(agent.kernel.plugins.keys()) if agent.kernel.plugins else []
        logger.info(f"Agent '{agent.name}' plugins: {plugins}")

    yield

    # Cleanup
    logger.info("Shutting down AI-KYC application")


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    settings = get_settings()

    app = FastAPI(
        title="AI-KYC Demo",
        description="KYC demonstration with multi-agent architecture using Semantic Kernel",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Configure CORS for React frontend
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:5173",  # Vite dev server
            "http://localhost:3000",  # Alternative dev port
            "http://127.0.0.1:5173",
            "http://127.0.0.1:3000",
        ],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Include routers
    app.include_router(health.router, tags=["Health"])
    app.include_router(chat.router, prefix="/api", tags=["Chat"])
    app.include_router(config.router, prefix="/api/config", tags=["Configuration"])
    app.include_router(documents.router, prefix="/api/documents", tags=["Documents"])

    return app


# Create the app instance
app = create_app()


# WebSocket endpoint is added separately for real-time communication
from src.api.websocket import setup_websocket

setup_websocket(app)
