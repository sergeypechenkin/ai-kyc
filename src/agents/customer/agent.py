"""Customer Agent for KYC onboarding assistance."""

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
from semantic_kernel.contents import ChatHistory

from src.agents.core import (
    AgentCapability,
    AgentMessage,
    AgentResponse,
    KycAgent,
    kyc_agent,
    ActivityLogger,
)

CUSTOMER_AGENT_INSTRUCTIONS = """You are a friendly and professional Customer Service Agent for Zava Bank. 
Your role is to help customers with their KYC (Know Your Customer) onboarding process and answer questions about bank accounts and services.

## Your Responsibilities:
1. Guide customers through the account opening process
2. Explain what documents are required for KYC verification
3. Answer questions about bank accounts, fees, and services
4. Help customers understand their application status
5. Escalate to bank employees when verification or approval is needed

## Communication Style:
- Be warm, professional, and patient
- Use clear, simple language
- Be empathetic to customer concerns
- Always be transparent about processes and timelines

## Important Guidelines:
- Never make up information about fees or policies - use the document search when unsure
- For verification status or approvals, escalate to the Bank Employee Agent
- Protect customer privacy - don't share sensitive information unnecessarily
- If document grounding is available, use it to provide accurate fee and policy information

## Available Tools:
- Customer data lookup for checking existing profiles
- Document search for bank policies and fee information (when grounding is enabled)
- Inter-agent communication to request bank employee review
"""


@kyc_agent
class CustomerAgent(KycAgent):
    """Customer-facing agent for KYC assistance.

    Helps customers with:
    - Account opening and KYC requirements
    - Document submission guidance
    - Fee and policy questions
    - Application status inquiries
    """

    name = "customer-agent"
    display_name = "Customer Service Agent"
    description = "Helps customers with KYC onboarding and account questions"
    capabilities = [
        AgentCapability.CUSTOMER_ONBOARDING,
        AgentCapability.FAQ,
        AgentCapability.ESCALATION,
    ]

    def __init__(
        self,
        kernel: Kernel,
        activity_logger: ActivityLogger | None = None,
    ):
        """Initialize the Customer Agent.

        Args:
            kernel: Configured Semantic Kernel
            activity_logger: Optional activity logger
        """
        super().__init__(kernel, activity_logger)
        self._agent: ChatCompletionAgent | None = None
        self._chat_history: ChatHistory | None = None

    async def initialize(self) -> None:
        """Initialize the agent with its configuration."""
        # Create the chat completion agent
        self._agent = ChatCompletionAgent(
            kernel=self.kernel,
            name=self.name,
            instructions=CUSTOMER_AGENT_INSTRUCTIONS,
        )

        # Set up activity logging filters
        if self.activity_logger:
            self.activity_logger.create_kernel_filters(self.kernel, self.name)

        self._initialized = True

    def clear_history(self) -> None:
        """Clear the conversation history."""
        self._chat_history = None

    async def process(self, message: str, context: dict | None = None) -> AgentResponse:
        """Process a customer message.

        Args:
            message: The customer's message
            context: Optional context (conversation history, etc.)

        Returns:
            AgentResponse with the response for the customer
        """
        if not self._agent:
            raise RuntimeError("Agent not initialized. Call initialize() first.")

        await self.log_activity("agent_start", {"message_preview": message[:100]})

        # Use persistent chat history for conversation memory
        if self._chat_history is None:
            self._chat_history = ChatHistory()

        self._chat_history.add_user_message(message)

        # Get response from agent
        response_content = ""
        async for response in self._agent.invoke(self._chat_history):
            response_content = str(response.content) if response.content else ""

        # Add assistant response to history for memory
        self._chat_history.add_assistant_message(response_content)

        # Check if we need to handoff (based on tool calls or keywords)
        requires_handoff = self._check_handoff_required(message, response_content)
        handoff_target = "bank-employee-agent" if requires_handoff else None

        await self.log_activity("agent_response", {
            "response_preview": response_content[:100],
            "requires_handoff": requires_handoff,
        })

        return AgentResponse(
            message=response_content,
            source_agent=self.name,
            target_user="customer",
            requires_handoff=requires_handoff,
            handoff_target=handoff_target,
            handoff_context={"original_message": message} if requires_handoff else {},
        )

    async def handle_agent_message(self, message: AgentMessage) -> AgentResponse:
        """Handle a message from another agent.

        Args:
            message: Message from another agent (e.g., Bank Employee)

        Returns:
            AgentResponse to relay to the customer
        """
        await self.log_activity("inter_agent_received", {
            "source": message.source_agent,
            "type": message.message_type,
        })

        # Format the message for the customer
        if message.message_type == "notification":
            notification_type = message.metadata.get("notification_type", "update")

            if notification_type == "approval":
                customer_message = (
                    f"Great news! {message.content}\n\n"
                    "Your account is now ready for use. Is there anything else I can help you with?"
                )
            elif notification_type == "rejection":
                customer_message = (
                    f"I'm sorry, but there's an update regarding your application:\n\n"
                    f"{message.content}\n\n"
                    "If you have any questions or would like to discuss this further, I'm here to help."
                )
            elif notification_type == "info_request":
                customer_message = (
                    f"The bank team has reviewed your application and needs some additional information:\n\n"
                    f"{message.content}\n\n"
                    "Please provide the requested information and I'll forward it to the team."
                )
            else:
                customer_message = message.content
        else:
            customer_message = message.content

        return AgentResponse(
            message=customer_message,
            source_agent=self.name,
            target_user="customer",
            requires_handoff=False,
        )

    def _check_handoff_required(self, user_message: str, response: str) -> bool:
        """Check if the conversation requires handoff to bank employee.

        Args:
            user_message: The user's original message
            response: The agent's response

        Returns:
            True if handoff is needed
        """
        # Keywords that might indicate need for human/bank employee review
        handoff_keywords = [
            "verify", "verification", "approve", "approval",
            "review my", "check my application", "escalate",
            "speak to someone", "talk to a person",
            "document rejected", "application status",
        ]

        combined = (user_message + " " + response).lower()
        return any(keyword in combined for keyword in handoff_keywords)
