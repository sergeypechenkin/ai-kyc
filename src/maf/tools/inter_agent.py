"""Inter-agent communication tools for MAF agents.

Enables agents to communicate with each other through the workflow.
"""

from typing import Callable, Awaitable
import uuid
from agent_framework import ai_function
from src.maf.activity import broadcast_activity_sync

# Type for message handler callback
MessageHandler = Callable[[str, str, str, dict], Awaitable[None]]

# Module-level handler for inter-agent messages
_message_handler: MessageHandler | None = None
_current_agent: str = ""


def init_inter_agent_tools(
    current_agent: str,
    message_handler: MessageHandler | None = None,
) -> None:
    """Initialize inter-agent tools.
    
    Args:
        current_agent: Name of the agent using these tools
        message_handler: Async callback for handling messages
    """
    global _message_handler, _current_agent
    _current_agent = current_agent
    _message_handler = message_handler


@ai_function
async def request_bank_review(customer_id: str, request_type: str, details: str) -> str:
    """Request the Bank Employee Agent to review a customer's KYC documents.
    
    Use when a customer needs verification, approval, or document review.
    
    Args:
        customer_id: Customer's ID
        request_type: Type of request (verification, approval, review)
        details: Additional details about the request
        
    Returns:
        Confirmation message
    """
    # Broadcast inter-agent communication
    broadcast_activity_sync("inter_agent", _current_agent, {
        "action": "request_bank_review",
        "from": _current_agent,
        "to": "bank-employee-agent",
        "customer_id": customer_id,
        "request_type": request_type,
        "details": details[:100]
    })
    
    if _message_handler:
        await _message_handler(
            "bank-employee-agent",
            f"Review request for customer {customer_id}: {details}",
            "request",
            {
                "customer_id": customer_id,
                "request_type": request_type,
                "details": details,
                "source_agent": _current_agent,
            },
        )
    
    return (
        f"Request submitted to Bank Employee Agent:\n"
        f"- Customer: {customer_id}\n"
        f"- Type: {request_type}\n"
        f"- Details: {details}\n"
        f"The bank team will review and respond shortly."
    )


@ai_function
async def notify_customer_agent(
    customer_id: str,
    notification_type: str,
    message_content: str,
) -> str:
    """Send a notification to the Customer Agent about a decision.
    
    Use when the bank has made a decision that the customer needs to know about.
    
    Args:
        customer_id: Customer's ID
        notification_type: Type of notification (approval, rejection, info_request)
        message_content: The message to send
        
    Returns:
        Confirmation message
    """
    # Broadcast inter-agent communication
    broadcast_activity_sync("inter_agent", _current_agent, {
        "action": "notify_customer_agent",
        "from": _current_agent,
        "to": "customer-agent",
        "customer_id": customer_id,
        "notification_type": notification_type,
        "message_preview": message_content[:100]
    })
    
    if _message_handler:
        await _message_handler(
            "customer-agent",
            f"Update for customer {customer_id}: {message_content}",
            "notification",
            {
                "customer_id": customer_id,
                "notification_type": notification_type,
                "message": message_content,
                "source_agent": _current_agent,
            },
        )
    
    return (
        f"Notification sent to Customer Agent:\n"
        f"- Customer: {customer_id}\n"
        f"- Type: {notification_type}\n"
        f"- Message: {message_content}\n"
        f"The customer will be informed."
    )


@ai_function
def get_available_agents() -> str:
    """Get list of available agents in the system.
    
    Returns:
        List of agents with descriptions
    """
    agents = [
        ("customer-agent", "Customer Service Agent - Helps customers with onboarding and questions"),
        ("bank-employee-agent", "Bank Employee Agent - Verifies KYC documents and processes applications"),
    ]
    
    lines = ["Available Agents:"]
    for name, desc in agents:
        lines.append(f"  - {name}: {desc}")
    
    return "\n".join(lines)


# Export tools organized by agent type
CUSTOMER_INTER_AGENT_TOOLS = [
    request_bank_review,
    get_available_agents,
]

EMPLOYEE_INTER_AGENT_TOOLS = [
    notify_customer_agent,
    get_available_agents,
]
