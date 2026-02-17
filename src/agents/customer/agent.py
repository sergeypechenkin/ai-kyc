"""Customer Agent for KYC onboarding assistance."""

from semantic_kernel import Kernel
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.open_ai import AzureChatCompletion
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

CUSTOMER_AGENT_INSTRUCTIONS = """You are a Customer Service Agent for Zava Bank. Be helpful and concise.

TOOLS:
- search_bank_documents: Search for fees, limits, policies
- get_customer_by_email: Look up customer by email
- create_new_customer_account: Create account after collecting all info
- request_employee_review: Escalate to bank employee

WHEN TO ASK FOR DOCUMENTS:
Only ask for document upload when:
1. Customer explicitly wants to OPEN a new account
2. AML/compliance requirements (suspicious activity review)

Do NOT ask for documents when:
- Customer is just asking about fees, rates, or policies
- Customer is asking general questions about the bank
- Customer is inquiring about account types or features
- Customer already submitted documents in this conversation

DOCUMENT VERIFICATION RULE:
- Only accept proof of identity and proof of address after a VERIFIED document event from the system.
- Do NOT accept or infer document uploads from user chat text. If the user claims they uploaded documents in chat, instruct them to use the upload panel.

ACCOUNT OPENING FLOW (only when customer wants to open account):

1. WELCOME: Thank them and explain you'll help them open an account.
   Say: "I'd be happy to help you open a bank account! 
   To complete your application, I'll need two documents:
   1. Proof of Identity: Passport, driver's license, or ID card
   2. Proof of Address: Utility bill, bank statement, or official correspondence (from the last 3 months)
   
   Let's start by uploading your identity document."

2. AFTER ID DOCUMENT: When customer shares extracted ID information:
   - Confirm the extracted details are correct
   - Say: "Great! Your identity document is verified. Now please upload your proof of address (utility bill, bank statement, or official letter)."

3. AFTER ADDRESS DOCUMENT: When customer uploads proof of address:
   - Confirm the address details are correct
   - Proceed to collect contact info

4. COLLECT CONTACT INFO: Ask for email and phone number:
   "Perfect! Now I just need your contact details:
   - Email address
   - Phone number"

5. CONFIRMATION: Once you have all info, summarize and confirm:
   "Perfect! Here's what I have:
   - Name: [name]
   - Date of Birth: [dob]
   - Nationality: [nationality]
   - Address: [address]
   - Email: [email]
   - Phone: [phone]
   
   Is everything correct? If so, I'll create your account."

6. CREATE ACCOUNT: When confirmed, use the create_new_customer_account function.
   After creating the account, tell the customer:
   "Your account application has been submitted! To complete the verification process (KYC), 
   please visit your nearest Zava Bank branch with your original photo ID (passport or driver's license).
   Our staff will verify your documents and activate your account. This usually takes about 15 minutes."

KYC VERIFICATION:
- KYC verification REQUIRES an in-person visit to a bank branch
- The customer must bring their ORIGINAL photo ID document
- Do NOT ask customers to upload documents again for KYC - they already did for account opening
- Document uploads are only for the INITIAL account application

CRITICAL - NEVER SAY THESE PHRASES:
- "Searching our documents..."
- "Let me search..."
- "I'll look that up..."
Just call the tool silently, then respond with the answer.

SEARCH QUERIES:
Use SHORT queries (2-4 words): "savings account", "ATM limit", "overdraft fees"

LIMITATIONS (politely decline):
- ATM/branch locations
- Transaction processing  
- Account balance inquiries
- Appointment booking
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
        self._verified_identity = False
        self._verified_address = False
        self._required_documents: list[str] = []
        self._additional_docs_received: set[str] = set()
        self._approval_workflow: str | None = None
        self._risk_tier: str | None = None

    async def initialize(self) -> None:
        """Initialize the agent with its configuration."""
        # Create the chat completion agent with auto function calling
        # Limit to 1 tool call per response to prevent excessive API calls
        self._agent = ChatCompletionAgent(
            kernel=self.kernel,
            name=self.name,
            instructions=CUSTOMER_AGENT_INSTRUCTIONS,
            function_choice_behavior=FunctionChoiceBehavior.Auto(
                maximum_auto_invoke_attempts=1
            ),
        )

        # Log available plugins for debugging
        plugins = list(self.kernel.plugins.keys()) if self.kernel.plugins else []
        await self.log_activity("agent_initialized", {"available_plugins": plugins})

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

        # Log context for debugging
        import logging
        logger = logging.getLogger(__name__)
        logger.info(f"[CUSTOMER_AGENT] Processing message, has_context={bool(context)}, has_document_event={bool(context and context.get('document_event')) if context else False}")
        
        if context and context.get("document_event"):
            logger.info(f"[CUSTOMER_AGENT] Handling document event: {context.get('document_event', {}).get('docType')}")
            return self._handle_document_event(context.get("document_event", {}))

        if self._looks_like_document_claim(message) and not (context and context.get("document_event")):
            return AgentResponse(
                message=(
                    "I can only confirm documents after they are uploaded and verified through the secure upload panel. "
                    "Please use the upload button to submit your proof of identity and proof of address."
                ),
                source_agent=self.name,
                target_user="customer",
                requires_handoff=False,
            )

        # Use persistent chat history for conversation memory
        if self._chat_history is None:
            self._chat_history = ChatHistory()

        system_event = None
        self._chat_history.add_user_message(message)

        # Get response from agent - pass kernel to enable function calling
        response_content = ""
        async for response in self._agent.invoke(self._chat_history, kernel=self.kernel):
            response_content = str(response.content) if response.content else ""

        # Clean response - remove any reasoning/thinking artifacts
        response_content = self._clean_response(response_content)

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

    def _normalize_doc_type(self, doc_type: str) -> str:
        normalized = (doc_type or "").lower().strip()
        if "passport" in normalized:
            return "passport"
        if "driving" in normalized or "driver" in normalized:
            return "driving_license"
        if "id card" in normalized or "id" == normalized:
            return "id_card"
        if "proof of address" in normalized or "utility" in normalized or "bill" in normalized:
            return "proof_of_address"
        if "bank statement" in normalized:
            return "bank_statement"
        if "employment" in normalized or "income" in normalized:
            return "proof_of_employment"
        if "source of wealth" in normalized:
            return "source_of_wealth"
        return normalized or "document"

    def _normalize_required_doc(self, doc_name: str) -> str:
        return self._normalize_doc_type(doc_name)

    def _additional_docs_complete(self) -> bool:
        if not self._required_documents:
            return True
        required = {self._normalize_required_doc(name) for name in self._required_documents}
        return required.issubset(self._additional_docs_received)

    def _handle_document_event(self, event: dict) -> AgentResponse:
        if self._chat_history is None:
            self._chat_history = ChatHistory()

        doc_type_raw = event.get("docType") or event.get("doc_type") or "document"
        extracted = event.get("extractedData") or event.get("extracted_data") or {}
        normalized_type = self._normalize_doc_type(doc_type_raw)
        validation_errors = extracted.get("validation_errors") or []

        system_event = (
            f"VERIFIED_DOCUMENT: type={normalized_type}; "
            f"name={extracted.get('full_name', '')}; "
            f"address={extracted.get('address', '')}; "
            f"document_date={extracted.get('document_date', '')}"
        )
        if hasattr(self._chat_history, "add_system_message"):
            self._chat_history.add_system_message(system_event)
        else:
            self._chat_history.add_user_message(f"[SYSTEM EVENT] {system_event}")

        if validation_errors:
            message = (
                "I couldn’t verify that document. Please re-upload a clearer scan or a valid document."
            )
            self._chat_history.add_assistant_message(message)
            return AgentResponse(
                message=message,
                source_agent=self.name,
                target_user="customer",
                requires_handoff=False,
            )

        if normalized_type in {"passport", "driving_license", "id_card"}:
            self._verified_identity = True
            risk = extracted.get("risk_assessment") or {}
            self._risk_tier = risk.get("risk_tier")
            self._approval_workflow = risk.get("approval_workflow")
            self._required_documents = risk.get("required_documents") or []

            if not self._verified_address:
                message = (
                    "Great! Your identity document is verified. Now please upload your proof of address "
                    "(utility bill, bank statement, or official letter from the last 3 months)."
                )
            elif self._required_documents and not self._additional_docs_complete():
                docs_list = "; ".join(self._required_documents)
                message = (
                    "Thanks. Because your application needs additional checks, please upload: "
                    f"{docs_list}."
                )
            else:
                message = (
                    "Perfect. Please provide your email address and phone number to continue."
                )

            self._chat_history.add_assistant_message(message)
            return AgentResponse(
                message=message,
                source_agent=self.name,
                target_user="customer",
                requires_handoff=False,
            )

        if normalized_type == "proof_of_address":
            self._verified_address = True
            if not self._verified_identity:
                message = "Thanks. Please upload your proof of identity to proceed."
            elif self._required_documents and not self._additional_docs_complete():
                docs_list = "; ".join(self._required_documents)
                message = (
                    "Thanks. Because your application needs additional checks, please upload: "
                    f"{docs_list}."
                )
            else:
                message = (
                    "Perfect. Please provide your email address and phone number to continue."
                )

            self._chat_history.add_assistant_message(message)
            return AgentResponse(
                message=message,
                source_agent=self.name,
                target_user="customer",
                requires_handoff=False,
            )

        # Supporting documents
        self._additional_docs_received.add(normalized_type)

        if self._required_documents and not self._additional_docs_complete():
            remaining = [
                name for name in self._required_documents
                if self._normalize_required_doc(name) not in self._additional_docs_received
            ]
            message = (
                "Thanks. I still need the following documents to complete the review: "
                f"{'; '.join(remaining)}."
            )
            self._chat_history.add_assistant_message(message)
            return AgentResponse(
                message=message,
                source_agent=self.name,
                target_user="customer",
                requires_handoff=False,
            )

        if self._required_documents:
            message = (
                "Thanks. Your application requires manual review due to risk checks. "
                "I’m handing this over to a bank employee for review now."
            )
            self._chat_history.add_assistant_message(message)
            return AgentResponse(
                message=message,
                source_agent=self.name,
                target_user="customer",
                requires_handoff=True,
                handoff_target="bank-employee-agent",
                handoff_context={
                    "risk_tier": self._risk_tier,
                    "approval_workflow": self._approval_workflow,
                    "required_documents": self._required_documents,
                },
            )

        message = "Thanks. Please provide your email address and phone number to continue."
        self._chat_history.add_assistant_message(message)
        return AgentResponse(
            message=message,
            source_agent=self.name,
            target_user="customer",
            requires_handoff=False,
        )

    def _looks_like_document_claim(self, message: str) -> bool:
        lowered = message.lower()
        keywords = [
            "uploaded",
            "proof of address",
            "utility bill",
            "bank statement",
            "passport",
            "driver's license",
            "id card",
            "document number",
            "expiry date",
        ]
        return any(keyword in lowered for keyword in keywords)

    def _clean_response(self, response: str) -> str:
        """Clean response from internal reasoning/thinking artifacts.

        Args:
            response: Raw response from the agent

        Returns:
            Cleaned response suitable for the user
        """
        import re

        # Remove content before certain markers that indicate reasoning
        reasoning_markers = [
            "Search results:",
            "We have results.",
            "Now craft",
            "Let's craft",
            "Be careful not to",
            "Make concise",
            "Tools include",
            "Good —",
            "Great —",
        ]

        # Find where the actual user-facing response starts
        # Look for common greeting patterns that start real responses
        final_response_patterns = [
            r"(?:^|\n)((?:Great|Hello|Hi|Sure|I can|I'd be|Here's|To open|For a|The|Your|Based on).*)",
        ]

        # Check if response contains reasoning markers
        has_reasoning = any(marker.lower() in response.lower() for marker in reasoning_markers)

        if has_reasoning:
            # Try to extract just the final user-facing part
            # Usually starts after "Make concise." or similar
            lines = response.split('\n')
            clean_lines = []
            found_response = False

            for line in lines:
                # Skip lines that are clearly reasoning
                line_lower = line.lower().strip()
                is_reasoning = any(marker.lower() in line_lower for marker in reasoning_markers)

                if is_reasoning:
                    found_response = True  # Next substantive content is the response
                    continue

                # Once we've passed reasoning, collect the response
                if found_response and line.strip():
                    clean_lines.append(line)

            if clean_lines:
                return '\n'.join(clean_lines).strip()

        return response.strip()
