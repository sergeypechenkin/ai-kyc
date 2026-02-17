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
from azure.identity import ClientSecretCredential
from dotenv import load_dotenv

# OpenTelemetry for agent tracing
try:
    from opentelemetry import trace
    _tracer = trace.get_tracer("ai-kyc.agents")
except ImportError:
    _tracer = None

from src.maf.telemetry import track_agent_operation

from src.maf.agents.customer_agent import (
    CUSTOMER_AGENT_INSTRUCTIONS,
    get_customer_agent_tools,
)
from src.maf.agents.bank_employee_agent import (
    BANK_EMPLOYEE_INSTRUCTIONS,
    get_bank_employee_agent_tools,
)


def _get_deployment_name() -> str:
    return (
        os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")
        or os.getenv("AZURE_OPENAI_DEPLOYMENT")
        or "gpt-4o"
    )


def _extract_response_text(response: Any) -> str:
    response_text = ""
    for msg in response.messages:
        if msg.role == Role.ASSISTANT:
            if hasattr(msg, "text") and msg.text:
                response_text = msg.text
            elif hasattr(msg, "contents") and msg.contents:
                for content in msg.contents:
                    if hasattr(content, "text"):
                        response_text = content.text
                        break
    return response_text


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
                    "gen_ai.request.model": _get_deployment_name(),
                    "gen_ai.prompt": message[:500],  # Truncate for telemetry
                }
            ) as span:
                response = await self.agent.run(self.conversation_history)
                response_text = _extract_response_text(response)
                
                # Add response to span
                span.set_attribute("gen_ai.response.model", _get_deployment_name())
                span.set_attribute("gen_ai.completion", response_text[:500] if response_text else "")
        else:
            # Fallback without tracing
            response = await self.agent.run(self.conversation_history)
            response_text = _extract_response_text(response)
        
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
    
    if not (tenant_id and client_id and client_secret):
        raise ValueError(
            "Missing Service Principal credentials for Azure OpenAI. "
            "Set AZURE_TENANT_ID, AZURE_CLIENT_ID, and AZURE_CLIENT_SECRET."
        )

    # Use Service Principal authentication only
    print("[INFO] Using Service Principal authentication for Azure OpenAI")
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret
    )
    
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
        response_text = ""
        with track_agent_operation(
            agent_name=role.value,
            operation="chat",
            attributes={
                "gen_ai.system": "azure_openai",
                "gen_ai.operation.name": "chat",
                "gen_ai.agent.name": role.value,
                "gen_ai.request.model": _get_deployment_name(),
                "gen_ai.prompt_length": len(message),
            },
        ) as span:
            response = await executor.agent.run(executor.conversation_history)
            response_text = _extract_response_text(response)
            if span:
                span.set_attribute("gen_ai.response.model", _get_deployment_name())
                span.set_attribute("gen_ai.completion_length", len(response_text))
        
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
        
        # Check for document event in context
        if context and context.get("document_event"):
            doc_event = context["document_event"]
            doc_type = doc_event.get("docType", "document")
            extracted = doc_event.get("extractedData", {})
            
            # Store extracted data for inter-agent tools
            from src.maf.tools.inter_agent import store_extracted_data
            store_data: dict = {}
            if extracted.get("first_name"):
                store_data["first_name"] = extracted["first_name"]
            if extracted.get("last_name"):
                store_data["last_name"] = extracted["last_name"]
            if extracted.get("date_of_birth"):
                store_data["date_of_birth"] = extracted["date_of_birth"]
            if extracted.get("nationality"):
                store_data["nationality"] = extracted["nationality"]
            if extracted.get("address"):
                store_data["address"] = extracted["address"]
            if extracted.get("document_number"):
                store_data["document_number"] = extracted["document_number"]
            
            risk = extracted.get("risk_assessment")
            if risk:
                store_data["risk_tier"] = risk.get("risk_tier", "")
                store_data["risk_score"] = risk.get("risk_score", 0)
                store_data["alerts"] = risk.get("alerts", [])
            
            upload_session_id = doc_event.get("sessionId", "")
            store_extracted_data(store_data, upload_session_id)
            
            # Format document information for the agent
            doc_info_parts = [f"[SYSTEM: Document verified - {doc_type}]"]
            
            if extracted.get("first_name"):
                doc_info_parts.append(f"Name: {extracted.get('first_name')} {extracted.get('last_name', '')}")
            if extracted.get("date_of_birth"):
                doc_info_parts.append(f"DOB: {extracted.get('date_of_birth')}")
            if extracted.get("nationality"):
                doc_info_parts.append(f"Nationality: {extracted.get('nationality')}")
            if extracted.get("address"):
                doc_info_parts.append(f"Address: {extracted.get('address')}")
            if extracted.get("document_number"):
                doc_info_parts.append(f"Doc#: {extracted.get('document_number')}")
            
            # Add risk assessment if present
            if risk:
                doc_info_parts.append(f"Risk Tier: {risk.get('risk_tier', 'unknown')}")
                doc_info_parts.append(f"Risk Score: {risk.get('risk_score', 0)}")
                doc_info_parts.append(f"Workflow: {risk.get('approval_workflow', 'unknown')}")
                if risk.get("required_documents"):
                    docs = ", ".join(risk["required_documents"])
                    doc_info_parts.append(f"Additional Docs Needed: {docs}")
                if risk.get("alerts"):
                    for alert in risk["alerts"]:
                        doc_info_parts.append(f"Alert: {alert}")
            
            # Prepend document info to the message
            message = "\n".join(doc_info_parts) + "\n\n" + message
        
        # Add user message to history
        user_message = ChatMessage(role=Role.USER, text=message)
        executor.conversation_history.append(user_message)
        
        # Run the agent with streaming
        full_response = ""
        with track_agent_operation(
            agent_name=role.value,
            operation="chat.stream",
            attributes={
                "gen_ai.system": "azure_openai",
                "gen_ai.operation.name": "chat",
                "gen_ai.agent.name": role.value,
                "gen_ai.request.model": _get_deployment_name(),
                "gen_ai.prompt_length": len(message),
            },
        ) as span:
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
            if span:
                span.set_attribute("gen_ai.response.model", _get_deployment_name())
                span.set_attribute("gen_ai.completion_length", len(full_response))
        
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
        
        Clears conversation history to prevent agents from retaining
        grounded information when grounding is disabled.
        
        Args:
            enabled: Whether grounding should be enabled
        """
        from src.maf.tools.document_search import set_grounding_enabled
        set_grounding_enabled(enabled)
        
        # Clear conversation history to prevent memory contamination
        # When grounding is disabled, agents shouldn't remember grounded info
        self.clear_history()


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
