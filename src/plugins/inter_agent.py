"""Inter-agent communication plugin."""

from typing import TYPE_CHECKING
import uuid

from semantic_kernel.functions import kernel_function

from src.plugins.base_plugin import KycPlugin
from src.agents.core.models import AgentMessage

if TYPE_CHECKING:
    from src.agents.core.orchestrator import AgentOrchestrator


class InterAgentPlugin(KycPlugin):
    """Plugin for communication between agents.

    Enables agents to:
    - Send requests to other agents
    - Notify other agents of events
    - Escalate issues to specialized agents
    """

    name = "inter_agent"
    description = "Communicate with other agents in the system"

    def __init__(self, orchestrator: "AgentOrchestrator", current_agent: str):
        """Initialize with orchestrator reference.

        Args:
            orchestrator: The agent orchestrator
            current_agent: Name of the agent using this plugin
        """
        super().__init__(orchestrator=orchestrator)
        self._orchestrator = orchestrator
        self._current_agent = current_agent

    @kernel_function(
        name="request_bank_review",
        description="Request the Bank Employee Agent to review a customer's KYC documents or application. Use when a customer needs verification or approval.",
    )
    async def request_bank_review(
        self,
        customer_id: str,
        request_type: str,
        details: str,
    ) -> str:
        """Request bank employee review.

        Args:
            customer_id: Customer's ID
            request_type: Type of request (verification, approval, review)
            details: Additional details about the request

        Returns:
            Confirmation message
        """
        message = AgentMessage(
            id=str(uuid.uuid4()),
            source_agent=self._current_agent,
            target_agent="bank-employee-agent",
            content=f"Review request for customer {customer_id}: {details}",
            message_type="request",
            metadata={
                "customer_id": customer_id,
                "request_type": request_type,
                "details": details,
            },
        )

        # Queue the message for the orchestrator
        await self._orchestrator._message_queue.put(message)

        return (
            f"Request submitted to Bank Employee Agent:\n"
            f"- Customer: {customer_id}\n"
            f"- Type: {request_type}\n"
            f"- Details: {details}\n"
            f"The bank team will review and respond shortly."
        )

    @kernel_function(
        name="notify_customer_agent",
        description="Send a notification to the Customer Agent about a decision or update. Use when the bank has made a decision that the customer needs to know about.",
    )
    async def notify_customer_agent(
        self,
        customer_id: str,
        notification_type: str,
        message_content: str,
    ) -> str:
        """Notify customer agent about an update.

        Args:
            customer_id: Customer's ID
            notification_type: Type of notification (approval, rejection, info_request)
            message_content: The message to send

        Returns:
            Confirmation message
        """
        message = AgentMessage(
            id=str(uuid.uuid4()),
            source_agent=self._current_agent,
            target_agent="customer-agent",
            content=message_content,
            message_type="notification",
            metadata={
                "customer_id": customer_id,
                "notification_type": notification_type,
            },
        )

        await self._orchestrator._message_queue.put(message)

        return (
            f"Notification sent to Customer Agent:\n"
            f"- Customer: {customer_id}\n"
            f"- Type: {notification_type}\n"
            f"- Message: {message_content}"
        )

    @kernel_function(
        name="get_available_agents",
        description="Get a list of available agents and their capabilities.",
    )
    def get_available_agents(self) -> str:
        """Get list of available agents.

        Returns:
            List of agents and their capabilities
        """
        agents = self._orchestrator.registry.get_all()

        if not agents:
            return "No agents currently available."

        lines = []
        for agent in agents:
            caps = ", ".join(c.value for c in agent.capabilities)
            lines.append(f"- {agent.display_name} ({agent.name}): {caps}")

        return "Available Agents:\n" + "\n".join(lines)
