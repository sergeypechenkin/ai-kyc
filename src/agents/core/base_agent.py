"""Base agent class for KYC agents."""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from semantic_kernel import Kernel

from src.agents.core.models import AgentCapability, AgentMessage, AgentMetadata, AgentResponse

if TYPE_CHECKING:
    from src.agents.core.activity_logger import ActivityLogger


class KycAgent(ABC):
    """Abstract base class for all KYC agents.

    All agents in the system should inherit from this class and implement
    the required methods. Agents are automatically registered with the
    AgentRegistry when decorated with @kyc_agent.
    """

    # Subclasses must define these
    name: str
    display_name: str
    description: str
    capabilities: list[AgentCapability]

    def __init__(self, kernel: Kernel, activity_logger: "ActivityLogger | None" = None):
        """Initialize the agent with a Semantic Kernel instance.

        Args:
            kernel: Configured Semantic Kernel instance
            activity_logger: Optional activity logger for detailed logging
        """
        self.kernel = kernel
        self.activity_logger = activity_logger
        self._initialized = False

    @property
    def metadata(self) -> AgentMetadata:
        """Get agent metadata."""
        return AgentMetadata(
            name=self.name,
            display_name=self.display_name,
            description=self.description,
            capabilities=self.capabilities,
        )

    @abstractmethod
    async def initialize(self) -> None:
        """Initialize the agent (load prompts, configure plugins, etc.)."""
        pass

    @abstractmethod
    async def process(self, message: str, context: dict | None = None) -> AgentResponse:
        """Process a user message and return a response.

        Args:
            message: The user's message
            context: Optional context (conversation history, user info, etc.)

        Returns:
            AgentResponse with the agent's response and any handoff requirements
        """
        pass

    @abstractmethod
    async def handle_agent_message(self, message: AgentMessage) -> AgentResponse:
        """Handle a message from another agent.

        Args:
            message: Message from another agent

        Returns:
            AgentResponse with the agent's response
        """
        pass

    def has_capability(self, capability: AgentCapability) -> bool:
        """Check if this agent has a specific capability."""
        return capability in self.capabilities

    def clear_history(self) -> None:
        """Clear the conversation history.
        
        Subclasses should override this to clear their specific chat history.
        """
        pass

    async def log_activity(self, event_type: str, data: dict) -> None:
        """Log an activity event if logger is available."""
        if self.activity_logger:
            await self.activity_logger.log(
                event_type=event_type,
                agent_name=self.name,
                data=data,
            )
