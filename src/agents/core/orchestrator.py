"""Agent orchestrator for managing agent-to-agent communication."""

import asyncio
import uuid
from collections.abc import Callable
from datetime import datetime
from typing import Any

from src.agents.core.agent_registry import AgentRegistry
from src.agents.core.base_agent import KycAgent
from src.agents.core.models import AgentCapability, AgentMessage, AgentResponse, ChatRole


class AgentOrchestrator:
    """Orchestrator for managing multi-agent communication and routing.

    Handles:
    - User message routing to appropriate agents
    - Agent-to-agent message passing
    - Capability-based routing
    - Message queue management
    - Activity broadcasting
    """

    def __init__(
        self,
        registry: AgentRegistry,
        on_activity: Callable[[dict[str, Any]], None] | None = None,
    ):
        """Initialize the orchestrator.

        Args:
            registry: Agent registry containing all agents
            on_activity: Callback for activity events (for real-time logging)
        """
        self.registry = registry
        self.on_activity = on_activity
        self._message_queue: asyncio.Queue[AgentMessage] = asyncio.Queue()
        self._processing = False

    async def process_user_message(
        self,
        message: str,
        role: ChatRole,
        context: dict | None = None,
    ) -> AgentResponse:
        """Process a message from a user (customer or employee).

        Args:
            message: The user's message
            role: The user's role (customer or employee)
            context: Optional context

        Returns:
            Response from the appropriate agent
        """
        # Route to appropriate agent based on role
        if role == ChatRole.CUSTOMER:
            agent = self.registry.get("customer-agent")
        elif role == ChatRole.EMPLOYEE:
            agent = self.registry.get("bank-employee-agent")
        else:
            raise ValueError(f"Invalid role: {role}")

        if not agent:
            raise RuntimeError(f"No agent found for role: {role}")

        # Log the incoming message
        await self._broadcast_activity({
            "type": "user_message",
            "role": role.value,
            "agent": agent.name,
            "content": message[:100] + "..." if len(message) > 100 else message,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Process the message
        response = await agent.process(message, context)

        # Log the response
        await self._broadcast_activity({
            "type": "agent_response",
            "agent": agent.name,
            "target_user": response.target_user,
            "requires_handoff": response.requires_handoff,
            "handoff_target": response.handoff_target,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Handle handoff if required
        if response.requires_handoff and response.handoff_target:
            await self._initiate_handoff(agent, response)

        return response

    async def _initiate_handoff(self, source_agent: KycAgent, response: AgentResponse) -> None:
        """Initiate a handoff from one agent to another.

        Args:
            source_agent: The agent initiating the handoff
            response: The response containing handoff information
        """
        target_agent = self.registry.get(response.handoff_target)  # type: ignore
        if not target_agent:
            await self._broadcast_activity({
                "type": "handoff_failed",
                "source": source_agent.name,
                "target": response.handoff_target,
                "reason": "Target agent not found",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return

        # Create inter-agent message
        agent_message = AgentMessage(
            id=str(uuid.uuid4()),
            source_agent=source_agent.name,
            target_agent=response.handoff_target,
            content=response.message,
            message_type="request",
            metadata=response.handoff_context,
            correlation_id=str(uuid.uuid4()),
        )

        await self._broadcast_activity({
            "type": "inter_agent_message",
            "source": source_agent.name,
            "target": response.handoff_target,
            "message_type": agent_message.message_type,
            "content": agent_message.content[:100] + "..." if len(agent_message.content) > 100 else agent_message.content,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Queue the message for processing
        await self._message_queue.put(agent_message)

        # Process the queued message
        await self._process_agent_message(agent_message)

    async def _process_agent_message(self, message: AgentMessage) -> AgentResponse | None:
        """Process an inter-agent message.

        Args:
            message: The agent message to process

        Returns:
            Response from the target agent
        """
        if not message.target_agent:
            return None

        target_agent = self.registry.get(message.target_agent)
        if not target_agent:
            return None

        # Process the message
        response = await target_agent.handle_agent_message(message)

        await self._broadcast_activity({
            "type": "agent_response",
            "agent": target_agent.name,
            "in_response_to": message.source_agent,
            "requires_handoff": response.requires_handoff,
            "timestamp": datetime.utcnow().isoformat(),
        })

        # Handle chain of handoffs
        if response.requires_handoff and response.handoff_target:
            await self._initiate_handoff(target_agent, response)

        return response

    async def route_by_capability(
        self,
        capability: AgentCapability,
        message: str,
        context: dict | None = None,
    ) -> AgentResponse | None:
        """Route a message to an agent based on capability.

        Args:
            capability: The required capability
            message: The message to process
            context: Optional context

        Returns:
            Response from the capable agent or None if not found
        """
        agent = self.registry.get_capable_agent(capability)
        if not agent:
            await self._broadcast_activity({
                "type": "routing_failed",
                "capability": capability.value,
                "reason": "No agent with capability found",
                "timestamp": datetime.utcnow().isoformat(),
            })
            return None

        await self._broadcast_activity({
            "type": "capability_routing",
            "capability": capability.value,
            "routed_to": agent.name,
            "timestamp": datetime.utcnow().isoformat(),
        })

        return await agent.process(message, context)

    async def _broadcast_activity(self, activity: dict[str, Any]) -> None:
        """Broadcast an activity event.

        Args:
            activity: Activity data to broadcast
        """
        if self.on_activity:
            self.on_activity(activity)

    def get_agent_status(self) -> list[dict[str, Any]]:
        """Get status of all registered agents.

        Returns:
            List of agent status dictionaries
        """
        return [
            {
                "name": agent.name,
                "display_name": agent.display_name,
                "capabilities": [c.value for c in agent.capabilities],
                "initialized": agent._initialized,
            }
            for agent in self.registry.get_all()
        ]
