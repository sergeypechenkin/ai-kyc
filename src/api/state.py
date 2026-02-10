"""Application state management."""

import asyncio
from typing import Any

from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from semantic_kernel import Kernel
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion

from src.agents.core import (
    ActivityEvent,
    ActivityLogger,
    AgentOrchestrator,
    AgentRegistry,
)
from src.agents.customer import CustomerAgent
from src.agents.bank_employee import BankEmployeeAgent
from src.infrastructure.config import get_settings
from src.infrastructure.mock_data import CustomerRepository
from src.infrastructure.document_search import DocumentSearchService
from src.infrastructure.document_intelligence import DocumentIntelligenceService
from src.plugins import (
    CustomerDataPlugin,
    DocumentSearchPlugin,
    InterAgentPlugin,
    KycVerificationPlugin,
    PluginRegistry,
)
from src.plugins.account_creation import AccountCreationPlugin


class AppState:
    """Application state container.

    Holds all shared resources: agents, plugins, repositories, and configuration.
    """

    def __init__(self):
        """Initialize the application state."""
        self.settings = get_settings()
        self.registry = AgentRegistry()
        self.plugin_registry = PluginRegistry()
        self.orchestrator: AgentOrchestrator | None = None
        self.activity_logger: ActivityLogger | None = None
        self.customer_repository: CustomerRepository | None = None
        self.document_search: DocumentSearchService | None = None
        self.document_search_plugin: DocumentSearchPlugin | None = None
        self.document_intelligence: DocumentIntelligenceService | None = None
        self._grounding_enabled = self.settings.enable_document_grounding
        self._activity_subscribers: list[asyncio.Queue] = []
        self._initialized = False

    @property
    def grounding_enabled(self) -> bool:
        """Check if document grounding is enabled."""
        return self._grounding_enabled

    @grounding_enabled.setter
    def grounding_enabled(self, value: bool) -> None:
        """Set document grounding state.
        
        Also updates the document search plugin if it exists.
        """
        self._grounding_enabled = value
        if self.document_search_plugin:
            self.document_search_plugin.grounding_enabled = value

    async def initialize(self) -> None:
        """Initialize all components."""
        if self._initialized:
            return

        # Initialize repositories
        self.customer_repository = CustomerRepository()
        self.document_search = DocumentSearchService()
        self.document_intelligence = DocumentIntelligenceService()

        # Initialize activity logger with broadcast callback
        self.activity_logger = ActivityLogger(
            on_event=self._broadcast_activity
        )

        # Create kernels for each agent
        customer_kernel = self._create_kernel("customer")
        employee_kernel = self._create_kernel("employee")

        # Create and register agents
        customer_agent = CustomerAgent(
            kernel=customer_kernel,
            activity_logger=self.activity_logger,
        )
        employee_agent = BankEmployeeAgent(
            kernel=employee_kernel,
            activity_logger=self.activity_logger,
        )

        self.registry.register(customer_agent)
        self.registry.register(employee_agent)

        # Create orchestrator
        self.orchestrator = AgentOrchestrator(
            registry=self.registry,
            on_activity=lambda data: asyncio.create_task(
                self.activity_logger.log(
                    event_type=data.get("type", "unknown"),
                    data=data,
                )
            ),
        )

        # Initialize plugins
        await self._initialize_plugins(customer_kernel, employee_kernel)

        # Initialize agents
        await self.registry.initialize_all()

        self._initialized = True

    def _create_kernel(self, purpose: str) -> Kernel:
        """Create a Semantic Kernel instance.

        Args:
            purpose: Description of the kernel's purpose

        Returns:
            Configured Kernel instance
        """
        kernel = Kernel()

        # Add Azure OpenAI chat completion if configured
        # Using Managed Identity / Service Principal via DefaultAzureCredential
        if self.settings.azure_openai_configured:
            credential = DefaultAzureCredential()
            token_provider = get_bearer_token_provider(
                credential, "https://cognitiveservices.azure.com/.default"
            )
            chat_service = AzureChatCompletion(
                deployment_name=self.settings.azure_openai_deployment_name,
                endpoint=self.settings.azure_openai_endpoint,
                ad_token_provider=token_provider,
                api_version=self.settings.azure_openai_api_version,
            )
            kernel.add_service(chat_service)

        return kernel

    async def _initialize_plugins(
        self,
        customer_kernel: Kernel,
        employee_kernel: Kernel,
    ) -> None:
        """Initialize and register plugins with kernels.

        Args:
            customer_kernel: Kernel for Customer Agent
            employee_kernel: Kernel for Bank Employee Agent
        """
        # Create shared plugins
        customer_data_plugin = CustomerDataPlugin(
            customer_repository=self.customer_repository  # type: ignore
        )
        kyc_plugin = KycVerificationPlugin(
            customer_repository=self.customer_repository  # type: ignore
        )
        account_creation_plugin = AccountCreationPlugin(
            customer_repository=self.customer_repository  # type: ignore
        )

        # Register plugins
        self.plugin_registry.register(customer_data_plugin)
        self.plugin_registry.register(kyc_plugin)
        self.plugin_registry.register(account_creation_plugin)

        # Add plugins to kernels
        customer_kernel.add_plugin(customer_data_plugin, "customer_data")
        employee_kernel.add_plugin(customer_data_plugin, "customer_data")
        employee_kernel.add_plugin(kyc_plugin, "kyc_verification")
        customer_kernel.add_plugin(account_creation_plugin, "account_creation")
        employee_kernel.add_plugin(account_creation_plugin, "account_creation")

        # Always add document search plugin (it checks grounding_enabled internally)
        # This allows dynamic toggling at runtime
        if self.document_search:
            self.document_search_plugin = DocumentSearchPlugin(
                search_service=self.document_search,
                grounding_enabled=self._grounding_enabled,
            )
            self.plugin_registry.register(self.document_search_plugin)
            customer_kernel.add_plugin(self.document_search_plugin, "document_search")
            employee_kernel.add_plugin(self.document_search_plugin, "document_search")

        # Add inter-agent plugins (after orchestrator is created)
        if self.orchestrator:
            customer_inter_agent = InterAgentPlugin(
                orchestrator=self.orchestrator,
                current_agent="customer-agent",
            )
            employee_inter_agent = InterAgentPlugin(
                orchestrator=self.orchestrator,
                current_agent="bank-employee-agent",
            )
            customer_kernel.add_plugin(customer_inter_agent, "inter_agent")
            employee_kernel.add_plugin(employee_inter_agent, "inter_agent")

    def subscribe_to_activities(self) -> asyncio.Queue:
        """Subscribe to activity events.

        Returns:
            Queue that will receive activity events
        """
        queue: asyncio.Queue = asyncio.Queue()
        self._activity_subscribers.append(queue)
        return queue

    def unsubscribe_from_activities(self, queue: asyncio.Queue) -> None:
        """Unsubscribe from activity events.

        Args:
            queue: The queue to unsubscribe
        """
        if queue in self._activity_subscribers:
            self._activity_subscribers.remove(queue)

    async def _broadcast_activity(self, event: ActivityEvent) -> None:
        """Broadcast an activity event to all subscribers.

        Args:
            event: The activity event to broadcast
        """
        event_dict = event.model_dump()
        event_dict["timestamp"] = event.timestamp.isoformat()

        for queue in self._activity_subscribers:
            try:
                await queue.put(event_dict)
            except Exception:
                pass  # Ignore errors for individual subscribers


# Global state instance
_app_state: AppState | None = None


def get_app_state() -> AppState:
    """Get the global application state instance."""
    global _app_state
    if _app_state is None:
        _app_state = AppState()
    return _app_state


def reset_app_state() -> None:
    """Reset the global application state (clears all history)."""
    global _app_state
    _app_state = None
