"""Core agent models using Pydantic."""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field


class AgentCapability(str, Enum):
    """Enumeration of agent capabilities for routing."""

    # Customer Agent capabilities
    CUSTOMER_ONBOARDING = "customer-onboarding"
    FAQ = "faq"
    ESCALATION = "escalation"

    # Bank Employee Agent capabilities
    KYC_VERIFICATION = "kyc-verification"
    CUSTOMER_LOOKUP = "customer-lookup"
    DECISION_MAKING = "decision-making"

    # Future agent capabilities
    AUDIT_TRAIL = "audit-trail"
    COMPLIANCE_CHECK = "compliance-check"
    PEP_SCREENING = "pep-screening"
    DOCUMENT_EXTRACTION = "document-extraction"
    REPORT_GENERATION = "report-generation"


class AgentMetadata(BaseModel):
    """Metadata describing an agent."""

    name: str = Field(..., description="Unique identifier for the agent")
    display_name: str = Field(..., description="Human-readable name")
    description: str = Field(..., description="What the agent does")
    capabilities: list[AgentCapability] = Field(
        default_factory=list, description="List of capabilities this agent provides"
    )


class AgentMessage(BaseModel):
    """Standardized message format for inter-agent communication."""

    id: str = Field(..., description="Unique message identifier")
    source_agent: str = Field(..., description="Name of the sending agent")
    target_agent: str | None = Field(None, description="Name of target agent, None for user")
    content: str = Field(..., description="Message content")
    message_type: str = Field(default="chat", description="Type: chat, request, response, notification")
    metadata: dict[str, Any] = Field(default_factory=dict, description="Additional metadata")
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    correlation_id: str | None = Field(None, description="ID linking related messages")


class AgentResponse(BaseModel):
    """Response from an agent after processing."""

    message: str = Field(..., description="Response content")
    source_agent: str = Field(..., description="Agent that generated the response")
    target_user: str | None = Field(None, description="Target user role: customer, employee, or None")
    requires_handoff: bool = Field(default=False, description="Whether to hand off to another agent")
    handoff_target: str | None = Field(None, description="Target agent for handoff")
    handoff_context: dict[str, Any] = Field(default_factory=dict, description="Context for handoff")
    metadata: dict[str, Any] = Field(default_factory=dict)


class ChatRole(str, Enum):
    """Chat participant roles."""

    CUSTOMER = "customer"
    EMPLOYEE = "employee"
    SYSTEM = "system"


class ChatMessage(BaseModel):
    """A message in a chat conversation."""

    id: str
    role: ChatRole
    content: str
    agent_name: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ConversationState(BaseModel):
    """State of a conversation session."""

    session_id: str
    customer_messages: list[ChatMessage] = Field(default_factory=list)
    employee_messages: list[ChatMessage] = Field(default_factory=list)
    inter_agent_messages: list[AgentMessage] = Field(default_factory=list)
    grounding_enabled: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
    metadata: dict[str, Any] = Field(default_factory=dict)
