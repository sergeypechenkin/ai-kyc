"""Chat API endpoints."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.agents.core import ChatRole
from src.api.state import get_app_state

router = APIRouter()


class ChatRequest(BaseModel):
    """Request model for chat messages."""

    message: str = Field(..., description="The user's message")
    role: str = Field(..., description="User role: 'customer' or 'employee'")
    session_id: str | None = Field(None, description="Optional session ID for conversation continuity")


class ChatResponse(BaseModel):
    """Response model for chat messages."""

    message: str = Field(..., description="The agent's response")
    agent: str = Field(..., description="Name of the responding agent")
    session_id: str = Field(..., description="Session ID for the conversation")
    metadata: dict = Field(default_factory=dict, description="Additional metadata")


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(request: ChatRequest):
    """Send a chat message to the appropriate agent.

    The message is routed based on the user's role:
    - 'customer' -> Customer Agent
    - 'employee' -> Bank Employee Agent
    """
    state = get_app_state()

    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    # Map role string to enum
    try:
        chat_role = ChatRole(request.role)
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid role: {request.role}. Must be 'customer' or 'employee'",
        )

    # Process the message
    try:
        response = await state.orchestrator.process_user_message(
            message=request.message,
            role=chat_role,
            context={"session_id": request.session_id},
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return ChatResponse(
        message=response.message,
        agent=response.source_agent,
        session_id=request.session_id or "default",
        metadata={
            "requires_handoff": response.requires_handoff,
            "handoff_target": response.handoff_target,
        },
    )


@router.get("/agents")
async def list_agents():
    """Get list of available agents and their status."""
    state = get_app_state()

    if not state.orchestrator:
        raise HTTPException(status_code=503, detail="Orchestrator not initialized")

    return {
        "agents": state.orchestrator.get_agent_status(),
    }


@router.get("/agents/{agent_name}")
async def get_agent_details(agent_name: str):
    """Get detailed information about a specific agent."""
    state = get_app_state()

    agent = state.registry.get(agent_name)
    if not agent:
        raise HTTPException(status_code=404, detail=f"Agent not found: {agent_name}")

    return {
        "name": agent.name,
        "display_name": agent.display_name,
        "description": agent.description,
        "capabilities": [c.value for c in agent.capabilities],
        "initialized": agent._initialized,
    }
