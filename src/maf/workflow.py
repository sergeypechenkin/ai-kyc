"""MAF Workflow Orchestration for KYC Demo.

Implements a multi-agent workflow using Microsoft Agent Framework.
Routes messages to customer or employee agent based on role.
"""

import os
from typing import Any, AsyncIterator
from enum import Enum

from agent_framework import (
    ChatAgent,
    ChatMessage,
    Executor,
    WorkflowBuilder,
    WorkflowContext,
    WorkflowOutputEvent,
    WorkflowStatusEvent,
    AgentRunEvent,
    handler,
    Role,
)
from agent_framework.azure import AzureOpenAIChatClient
from azure.identity import DefaultAzureCredential, ClientSecretCredential
from dotenv import load_dotenv

# OpenTelemetry for agent tracing
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("ai-kyc.agents")
except ImportError:
    _tracer = None

from src.maf.agents.customer_agent import (
    CUSTOMER_AGENT_INSTRUCTIONS,
    get_customer_agent_tools,
)
from src.maf.agents.bank_employee_agent import (
    BANK_EMPLOYEE_INSTRUCTIONS,
    get_bank_employee_agent_tools,
)


class ChatRole(str, Enum):
    """Role of the chat participant."""
    CUSTOMER = "customer"
    EMPLOYEE = "employee"


class KycAgentExecutor(Executor):
    """Executor that wraps a KYC agent (customer or employee).
    
    Routes messages based on role and maintains conversation history.
    """
    
    agent: ChatAgent
    role: ChatRole
    conversation_history: list[ChatMessage]
    
    def __init__(
        self,
        agent: ChatAgent,
        role: ChatRole,
        executor_id: str,
    ):
        """Initialize the executor.
        
        Args:
            agent: The ChatAgent to use
            role: The role this executor handles
            executor_id: Unique ID for this executor
        """
        self.agent = agent
        self.role = role
        self.conversation_history = []
        super().__init__(id=executor_id)
    
    @handler
    async def handle_message(
        self,
        input_data: dict[str, Any],
        ctx: WorkflowContext[None, str],
    ) -> None:
        """Handle incoming message.
        
        Args:
            input_data: Dict with 'message', 'role', and optionally 'context'
            ctx: Workflow context for yielding output
        """
        message = input_data.get("message", "")
        role = input_data.get("role", ChatRole.CUSTOMER)
        context = input_data.get("context", {})
        
        # Only process if role matches
        if role != self.role:
            # Pass through to next executor or yield empty
            return
        
        # Add user message to history
        user_message = ChatMessage(role=Role.USER, text=message)
        self.conversation_history.append(user_message)
        
        # Run the agent with tracing
        if _tracer:
            with _tracer.start_as_current_span(
                f"agent.{self.role.value}",
                attributes={
                    "gen_ai.system": "azure_openai",
                    "gen_ai.operation.name": "chat",
                    "gen_ai.agent.name": self.role.value,
                    "gen_ai.request.model": os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"),
                    "gen_ai.prompt": message[:500],  # Truncate for telemetry
                }
            ) as span:
                response = await self.agent.run(self.conversation_history)
                
                # Extract response text
                response_text = ""
                for msg in response.messages:
                    if msg.role == Role.ASSISTANT:
                        if hasattr(msg, 'text') and msg.text:
                            response_text = msg.text
                        elif hasattr(msg, 'contents') and msg.contents:
                            for content in msg.contents:
                                if hasattr(content, 'text'):
                                    response_text = content.text
                                    break
                
                # Add response to span
                span.set_attribute("gen_ai.response.model", os.getenv("AZURE_OPENAI_DEPLOYMENT", "gpt-4o"))
                span.set_attribute("gen_ai.completion", response_text[:500] if response_text else "")
        else:
            # Fallback without tracing
            response = await self.agent.run(self.conversation_history)
            
            # Extract response text
            response_text = ""
            for msg in response.messages:
                if msg.role == Role.ASSISTANT:
                    if hasattr(msg, 'text') and msg.text:
                        response_text = msg.text
                    elif hasattr(msg, 'contents') and msg.contents:
                        for content in msg.contents:
                            if hasattr(content, 'text'):
                                response_text = content.text
                                break
        
        # Add to history
        self.conversation_history.append(
            ChatMessage(role=Role.ASSISTANT, text=response_text)
        )
        
        # Yield the response
        await ctx.yield_output(response_text)
    
    def clear_history(self) -> None:
        """Clear conversation history."""
        self.conversation_history = []


def create_chat_client() -> AzureOpenAIChatClient:
    """Create the Azure OpenAI chat client.
    
    Supports both Foundry and Azure OpenAI endpoints.
    Uses ClientSecretCredential for Service Principal auth if configured.
    
    Returns:
        Configured AzureOpenAIChatClient
    """
    load_dotenv(override=True)
    
    # Use Azure OpenAI endpoint
    endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
    deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
    
    if not endpoint or not deployment:
        raise ValueError(
            "Missing configuration. Set AZURE_OPENAI_ENDPOINT and AZURE_OPENAI_DEPLOYMENT_NAME"
        )
    
    # Check for Service Principal credentials
    tenant_id = os.getenv("AZURE_TENANT_ID")
    client_id = os.getenv("AZURE_CLIENT_ID")
    client_secret = os.getenv("AZURE_CLIENT_SECRET")
    
    if tenant_id and client_id and client_secret:
        # Use Service Principal authentication
        print("[INFO] Using Service Principal authentication for Azure OpenAI")
        credential = ClientSecretCredential(
            tenant_id=tenant_id,
            client_id=client_id,
            client_secret=client_secret
        )
    else:
        # Fall back to DefaultAzureCredential (Azure CLI, Managed Identity, etc.)
        print("[INFO] Using DefaultAzureCredential for Azure OpenAI")
        credential = DefaultAzureCredential()
    
    return AzureOpenAIChatClient(
        endpoint=endpoint,
        deployment_name=deployment,
        credential=credential,
    )


class KycWorkflow:
    """Multi-agent workflow for KYC operations.
    
    Routes messages to customer or employee agent based on role.
    """
    
    def __init__(self):
        """Initialize the workflow."""
        self._chat_client: AzureOpenAIChatClient | None = None
        self._customer_agent: ChatAgent | None = None
        self._employee_agent: ChatAgent | None = None
        self._customer_executor: KycAgentExecutor | None = None
        self._employee_executor: KycAgentExecutor | None = None
        self._initialized = False
    
    async def initialize(
        self,
        customer_repository=None,
        search_service=None,
        grounding_enabled: bool = True,
    ) -> None:
        """Initialize the workflow with dependencies.
        
        Args:
            customer_repository: Repository for customer data
            search_service: Document search service
            grounding_enabled: Whether document grounding is enabled
        """
        # Initialize tools with dependencies
        if customer_repository:
            from src.maf.tools.customer_data import init_customer_tools
            from src.maf.tools.kyc_verification import init_kyc_tools
            from src.maf.tools.account_creation import init_account_creation_tools
            
            init_customer_tools(customer_repository)
            init_kyc_tools(customer_repository)
            init_account_creation_tools(customer_repository)
        
        if search_service:
            from src.maf.tools.document_search import init_document_search_tools
            init_document_search_tools(search_service, grounding_enabled)
        
        # Initialize inter-agent tools for each agent
        from src.maf.tools.inter_agent import init_inter_agent_tools
        
        # Create chat client
        self._chat_client = create_chat_client()
        
        # Create customer agent
        init_inter_agent_tools("customer-agent", self._handle_inter_agent_message)
        self._customer_agent = self._chat_client.create_agent(
            name="customer-agent",
            instructions=CUSTOMER_AGENT_INSTRUCTIONS,
            tools=get_customer_agent_tools(),
        )
        
        # Create employee agent  
        init_inter_agent_tools("bank-employee-agent", self._handle_inter_agent_message)
        self._employee_agent = self._chat_client.create_agent(
            name="bank-employee-agent",
            instructions=BANK_EMPLOYEE_INSTRUCTIONS,
            tools=get_bank_employee_agent_tools(),
        )
        
        # Create executors
        self._customer_executor = KycAgentExecutor(
            agent=self._customer_agent,
            role=ChatRole.CUSTOMER,
            executor_id="customer-executor",
        )
        
        self._employee_executor = KycAgentExecutor(
            agent=self._employee_agent,
            role=ChatRole.EMPLOYEE,
            executor_id="employee-executor",
        )
        
        self._initialized = True
    
    async def _handle_inter_agent_message(
        self,
        target_agent: str,
        content: str,
        message_type: str,
        metadata: dict,
    ) -> None:
        """Handle inter-agent messages.
        
        Args:
            target_agent: Target agent name
            content: Message content
            message_type: Type of message
            metadata: Additional metadata
        """
        # In a full implementation, this would queue messages
        # For now, we log the inter-agent communication
        print(f"[Inter-Agent] {metadata.get('source_agent')} -> {target_agent}: {content}")
    
    async def process_message(
        self,
        message: str,
        role: ChatRole,
        context: dict | None = None,
    ) -> str:
        """Process a message and return response.
        
        Args:
            message: User message
            role: Chat role (customer or employee)
            context: Optional context
            
        Returns:
            Agent response text
        """
        if not self._initialized:
            raise RuntimeError("Workflow not initialized. Call initialize() first.")
        
        # Route to appropriate executor
        if role == ChatRole.CUSTOMER:
            executor = self._customer_executor
        else:
            executor = self._employee_executor
        
        if executor is None:
            raise RuntimeError(f"No executor for role: {role}")
        
        # Add user message to history
        user_message = ChatMessage(role=Role.USER, text=message)
        executor.conversation_history.append(user_message)
        
        # Run the agent
        response = await executor.agent.run(executor.conversation_history)
        
        # Extract response text
        response_text = ""
        for msg in response.messages:
            if msg.role == Role.ASSISTANT:
                if hasattr(msg, 'text') and msg.text:
                    response_text = msg.text
                elif hasattr(msg, 'contents') and msg.contents:
                    for content in msg.contents:
                        if hasattr(content, 'text'):
                            response_text = content.text
                            break
        
        # Add to history
        executor.conversation_history.append(
            ChatMessage(role=Role.ASSISTANT, text=response_text)
        )
        
        return response_text
    
    async def process_message_stream(
        self,
        message: str,
        role: ChatRole,
        context: dict | None = None,
    ) -> AsyncIterator[str]:
        """Process a message and stream response.
        
        Args:
            message: User message
            role: Chat role (customer or employee)
            context: Optional context
            
        Yields:
            Response text chunks
        """
        if not self._initialized:
            raise RuntimeError("Workflow not initialized. Call initialize() first.")
        
        # Route to appropriate executor
        if role == ChatRole.CUSTOMER:
            executor = self._customer_executor
        else:
            executor = self._employee_executor
        
        if executor is None:
            raise RuntimeError(f"No executor for role: {role}")
        
        # Add user message to history
        user_message = ChatMessage(role=Role.USER, text=message)
        executor.conversation_history.append(user_message)
        
        # Run the agent with streaming
        full_response = ""
        async for update in executor.agent.run_stream(executor.conversation_history):
            if hasattr(update, 'text') and update.text:
                chunk = update.text
                full_response += chunk
                yield chunk
            elif hasattr(update, 'contents') and update.contents:
                for content in update.contents:
                    if hasattr(content, 'text') and content.text:
                        chunk = content.text
                        full_response += chunk
                        yield chunk
        
        # Add full response to history
        executor.conversation_history.append(
            ChatMessage(role=Role.ASSISTANT, text=full_response)
        )
    
    def clear_history(self, role: ChatRole | None = None) -> None:
        """Clear conversation history.
        
        Args:
            role: Specific role to clear, or None for all
        """
        if role is None or role == ChatRole.CUSTOMER:
            if self._customer_executor:
                self._customer_executor.clear_history()
        
        if role is None or role == ChatRole.EMPLOYEE:
            if self._employee_executor:
                self._employee_executor.clear_history()
    
    def set_grounding_enabled(self, enabled: bool) -> None:
        """Enable or disable document grounding.
        
        Args:
            enabled: Whether grounding should be enabled
        """
        from src.maf.tools.document_search import set_grounding_enabled
        set_grounding_enabled(enabled)


# Singleton workflow instance
_workflow: KycWorkflow | None = None


async def get_workflow() -> KycWorkflow:
    """Get the singleton workflow instance.
    
    Returns:
        Initialized KycWorkflow
    """
    global _workflow
    if _workflow is None:
        _workflow = KycWorkflow()
    return _workflow
