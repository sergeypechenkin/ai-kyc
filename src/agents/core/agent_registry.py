"""Agent registry for dynamic agent discovery and management."""

from typing import Callable, TypeVar

from semantic_kernel import Kernel

from src.agents.core.base_agent import KycAgent
from src.agents.core.models import AgentCapability, AgentMetadata

T = TypeVar("T", bound=KycAgent)

# Global registry of agent classes
_agent_classes: dict[str, type[KycAgent]] = {}


def kyc_agent(cls: type[T]) -> type[T]:
    """Decorator to register an agent class with the registry.

    Usage:
        @kyc_agent
        class CustomerAgent(KycAgent):
            name = "customer-agent"
            ...
    """
    if not issubclass(cls, KycAgent):
        raise TypeError(f"{cls.__name__} must inherit from KycAgent")

    if not hasattr(cls, "name") or not cls.name:
        raise ValueError(f"{cls.__name__} must define a 'name' attribute")

    _agent_classes[cls.name] = cls
    return cls


class AgentRegistry:
    """Registry for managing agent instances.

    Provides dynamic agent discovery, instantiation, and capability-based routing.
    """

    def __init__(self):
        """Initialize the registry."""
        self._agents: dict[str, KycAgent] = {}
        self._factory_funcs: dict[str, Callable[[], KycAgent]] = {}

    @property
    def registered_classes(self) -> dict[str, type[KycAgent]]:
        """Get all registered agent classes."""
        return _agent_classes.copy()

    def register(self, agent: KycAgent) -> None:
        """Register an agent instance.

        Args:
            agent: Agent instance to register
        """
        self._agents[agent.name] = agent

    def register_factory(self, name: str, factory: Callable[[], KycAgent]) -> None:
        """Register a factory function for lazy agent instantiation.

        Args:
            name: Agent name
            factory: Factory function that creates the agent
        """
        self._factory_funcs[name] = factory

    def get(self, name: str) -> KycAgent | None:
        """Get an agent by name.

        Args:
            name: Agent name

        Returns:
            Agent instance or None if not found
        """
        if name in self._agents:
            return self._agents[name]

        # Try lazy instantiation
        if name in self._factory_funcs:
            agent = self._factory_funcs[name]()
            self._agents[name] = agent
            return agent

        return None

    def get_all(self) -> list[KycAgent]:
        """Get all registered agent instances."""
        return list(self._agents.values())

    def get_metadata(self) -> list[AgentMetadata]:
        """Get metadata for all registered agents."""
        return [agent.metadata for agent in self._agents.values()]

    def find_by_capability(self, capability: AgentCapability) -> list[KycAgent]:
        """Find agents that have a specific capability.

        Args:
            capability: The capability to search for

        Returns:
            List of agents with the capability
        """
        return [agent for agent in self._agents.values() if agent.has_capability(capability)]

    def get_capable_agent(self, capability: AgentCapability) -> KycAgent | None:
        """Get the first agent with a specific capability.

        Args:
            capability: The capability to search for

        Returns:
            First matching agent or None
        """
        agents = self.find_by_capability(capability)
        return agents[0] if agents else None

    async def initialize_all(self) -> None:
        """Initialize all registered agents."""
        for agent in self._agents.values():
            if not agent._initialized:
                await agent.initialize()
                agent._initialized = True

    def create_from_class(
        self,
        agent_class: type[KycAgent],
        kernel: Kernel,
        **kwargs,
    ) -> KycAgent:
        """Create and register an agent from a class.

        Args:
            agent_class: The agent class to instantiate
            kernel: Semantic Kernel instance
            **kwargs: Additional arguments for the agent constructor

        Returns:
            The created agent instance
        """
        agent = agent_class(kernel=kernel, **kwargs)
        self.register(agent)
        return agent
