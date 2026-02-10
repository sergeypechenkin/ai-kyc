"""Bank Employee Agent for KYC verification and processing."""

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior
from semantic_kernel.contents import ChatHistory

from src.agents.core import (
    AgentCapability,
    AgentMessage,
    AgentResponse,
    KycAgent,
    kyc_agent,
    ActivityLogger,
)

BANK_EMPLOYEE_INSTRUCTIONS = """You are a Bank Employee Agent for Zava Bank, specializing in KYC verification and compliance.
Your role is to assist bank employees with reviewing customer applications, verifying documents, and making decisions on KYC compliance.

## IMPORTANT - WAIT FOR REQUESTS:
- Do NOT automatically fetch or display pending reviews
- Do NOT call any tools until the employee asks for something specific
- Start with a simple greeting and wait for the employee to tell you what they need
- Only call get_pending_reviews when the employee asks to see pending cases/reviews

## Your Responsibilities:
1. Review and verify customer documents (passports, driving licenses, utility bills)
2. Approve or reject KYC applications based on verification results
3. Request additional documents when needed
4. Look up customer information and account status
5. Communicate decisions back to the Customer Agent for customer notification

## Verification Standards:
- All documents must be valid and not expired
- Photo ID must match customer profile
- Proof of address must be within last 3 months
- Watch for PEP (Politically Exposed Persons) indicators
- Follow AML (Anti-Money Laundering) guidelines

## Decision Guidelines:
- APPROVE: All documents verified, no red flags
- REJECT: Fraudulent documents, failed identity check, AML concerns
- REQUEST MORE INFO: Missing documents, expired documents, unclear information

## Communication:
- Be thorough and professional in your assessments
- Document all decisions with clear reasoning
- Use the notification system to inform the Customer Agent of decisions
- Escalate unusual cases or complex situations

## Available Tools:
- Customer data lookup for profile and account information
- KYC verification tools for document checking
- Inter-agent communication to notify Customer Agent
- Document search for compliance guidelines (when grounding is enabled)

## Greeting:
When first contacted, simply greet the employee and ask how you can help. For example:
"Hello! I'm the KYC verification assistant. How can I help you today?"
"""


@kyc_agent
class BankEmployeeAgent(KycAgent):
    """Bank employee agent for KYC verification.

    Handles:
    - Document verification
    - KYC approval/rejection
    - Customer data review
    - Compliance checking
    """

    name = "bank-employee-agent"
    display_name = "Bank Employee Agent"
    description = "Verifies KYC documents and processes applications"
    capabilities = [
        AgentCapability.KYC_VERIFICATION,
        AgentCapability.CUSTOMER_LOOKUP,
        AgentCapability.DECISION_MAKING,
    ]

    def __init__(
        self,
        kernel: Kernel,
        activity_logger: ActivityLogger | None = None,
    ):
        """Initialize the Bank Employee Agent.

        Args:
            kernel: Configured Semantic Kernel
            activity_logger: Optional activity logger
        """
        super().__init__(kernel, activity_logger)
        self._agent: ChatCompletionAgent | None = None
        self._chat_history: ChatHistory | None = None

    async def initialize(self) -> None:
        """Initialize the agent with its configuration."""
        # Create the chat completion agent with auto function calling
        self._agent = ChatCompletionAgent(
            kernel=self.kernel,
            name=self.name,
            instructions=BANK_EMPLOYEE_INSTRUCTIONS,
            function_choice_behavior=FunctionChoiceBehavior.Auto(
                maximum_auto_invoke_attempts=1
            ),
        )

        # Set up activity logging filters
        if self.activity_logger:
            self.activity_logger.create_kernel_filters(self.kernel, self.name)

        self._initialized = True

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._chat_history = None

    async def process(self, message: str, context: dict | None = None) -> AgentResponse:
        """Process a bank employee's message.

        Args:
            message: The employee's message/query
            context: Optional context

        Returns:
            AgentResponse with the response
        """
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        await self.log_activity("agent_start", {"message_preview": message[:100]})

        # Use persistent chat history for conversation memory
        if self._chat_history is None:
            self._chat_history = ChatHistory()

        self._chat_history.add_user_message(message)

        # Get response from agent - pass kernel to enable function calling
        response_content = ""
        async for response in self._agent.invoke(self._chat_history, kernel=self.kernel):
            response_content = str(response.content) if response.content else ""

        # Add assistant response to history for memory
        self._chat_history.add_assistant_message(response_content)

        # Check if we need to notify customer agent
        requires_handoff = self._should_notify_customer(response_content)

        await self.log_activity("agent_response", {
            "response_preview": response_content[:100],
            "requires_handoff": requires_handoff,
        })

        return AgentResponse(
            message=response_content,
            source_agent=self.name,
            target_user="employee",
            requires_handoff=requires_handoff,
            handoff_target="customer-agent" if requires_handoff else None,
            handoff_context=self._extract_notification_context(response_content) if requires_handoff else {},
        )

    async def handle_agent_message(self, message: AgentMessage) -> AgentResponse:
        """Handle a message from another agent.

        Args:
            message: Message from another agent (e.g., Customer Agent)

        Returns:
            AgentResponse with the bank employee's response
        """
        await self.log_activity("inter_agent_received", {
            "source": message.source_agent,
            "type": message.message_type,
        })

        if not self._agent:
            raise RuntimeError("Agent not initialized")

        # Process the inter-agent request
        if message.message_type == "request":
            # Build context from the request
            customer_id = message.metadata.get("customer_id", "unknown")
            request_type = message.metadata.get("request_type", "review")
            details = message.metadata.get("details", message.content)

            prompt = (
                f"Incoming request from Customer Service Agent:\n\n"
                f"Customer ID: {customer_id}\n"
                f"Request Type: {request_type}\n"
                f"Details: {details}\n\n"
                f"Please review this request and take appropriate action. "
                f"Use available tools to look up customer information and verify documents as needed."
            )
        else:
            prompt = message.content

        # Process through the agent
        chat_history = ChatHistory()
        chat_history.add_user_message(prompt)

        response_content = ""
        async for response in self._agent.invoke(chat_history, kernel=self.kernel):
            response_content = str(response.content) if response.content else ""

        # Determine if we need to send a response back to customer agent
        should_respond = self._should_notify_customer(response_content)

        return AgentResponse(
            message=response_content,
            source_agent=self.name,
            target_user="employee",  # Show in employee chat
            requires_handoff=should_respond,
            handoff_target="customer-agent" if should_respond else None,
            handoff_context=self._extract_notification_context(response_content) if should_respond else {},
        )

    def _should_notify_customer(self, response: str) -> bool:
        """Check if the response requires customer notification.

        Args:
            response: The agent's response

        Returns:
            True if customer should be notified
        """
        notification_triggers = [
            "approved", "rejected", "approval", "rejection",
            "notify customer", "inform customer", "customer must be notified",
            "additional documents", "documents needed", "request additional",
        ]
        response_lower = response.lower()
        return any(trigger in response_lower for trigger in notification_triggers)

    def _extract_notification_context(self, response: str) -> dict:
        """Extract notification context from response.

        Args:
            response: The agent's response

        Returns:
            Context dictionary for the notification
        """
        response_lower = response.lower()

        if "approved" in response_lower or "approval" in response_lower:
            notification_type = "approval"
        elif "rejected" in response_lower or "rejection" in response_lower:
            notification_type = "rejection"
        elif "additional" in response_lower or "documents needed" in response_lower:
            notification_type = "info_request"
        else:
            notification_type = "update"

        return {
            "notification_type": notification_type,
            "original_response": response,
        }
