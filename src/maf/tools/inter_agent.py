"""Inter-agent communication tools for MAF agents.

Enables agents to communicate with each other through the workflow.
"""

from typing import Callable, Awaitable
from datetime import datetime
import uuid
import random
from agent_framework import ai_function
from src.maf.activity import broadcast_activity_sync

# Type for message handler callback
MessageHandler = Callable[[str, str, str, dict], Awaitable[None]]

# Module-level handler for inter-agent messages
_message_handler: MessageHandler | None = None
_current_agent: str = ""

# Accumulated customer data from document events in the current session
_extracted_customer_data: dict = {}
_upload_session_id: str = ""


def store_extracted_data(data: dict, upload_session_id: str = "", document_type: str = "") -> None:
    """Store extracted data from document events for use in inter-agent tools.
    
    Called by the workflow when processing document_event messages.
    Data is accumulated (merged) across multiple document uploads.
    """
    global _extracted_customer_data, _upload_session_id
    for k, v in data.items():
        if v:  # only store non-empty values
            _extracted_customer_data[k] = v
    if upload_session_id:
        _upload_session_id = upload_session_id
    # Track uploaded document types
    if document_type:
        if "uploaded_documents" not in _extracted_customer_data:
            _extracted_customer_data["uploaded_documents"] = []
        if document_type not in _extracted_customer_data["uploaded_documents"]:
            _extracted_customer_data["uploaded_documents"].append(document_type)
    print(f"[DEBUG] Stored extracted data: keys={list(_extracted_customer_data.keys())}, docs={_extracted_customer_data.get('uploaded_documents', [])}, session={_upload_session_id}")


def clear_extracted_data() -> None:
    """Clear stored extracted data (e.g., on new conversation)."""
    global _extracted_customer_data, _upload_session_id
    _extracted_customer_data = {}
    _upload_session_id = ""


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
        customer_id: Customer's name or ID
        request_type: Type of request (verification, approval, review)
        details: Additional details about the request
        
    Returns:
        Confirmation message
    """
    import re as _re
    
    # Generate a proper unique customer ID
    new_customer_id = f"NEW-{random.randint(1000, 9999)}"
    
    # Use accumulated extracted data from document events
    data = _extracted_customer_data
    customer_name = f"{data.get('first_name', '')} {data.get('last_name', '')}".strip() or customer_id
    
    # Try to extract real risk tier from details text or stored data
    _risk_tier = data.get("risk_tier", "")
    if not _risk_tier:
        _risk_match = _re.search(r'\b(low|medium|high)\b', details.lower())
        _risk_tier = _risk_match.group(1) if _risk_match else request_type
    
    _risk_score = data.get("risk_score", 0)
    _alerts = data.get("alerts", [])
    
    # Broadcast inter-agent communication
    broadcast_activity_sync("inter_agent", _current_agent, {
        "action": "request_bank_review",
        "from": _current_agent,
        "to": "bank-employee-agent",
        "customer_id": new_customer_id,
        "customer_name": customer_name,
        "request_type": request_type,
        "details": details[:100]
    })
    
    # Create a pending submission with full customer data
    from src.maf.tools.kyc_verification import add_pending_submission
    
    submission = {
        "customer_id": new_customer_id,
        "customer_name": customer_name,
        "first_name": data.get("first_name", ""),
        "last_name": data.get("last_name", ""),
        "date_of_birth": data.get("date_of_birth", ""),
        "nationality": data.get("nationality", ""),
        "address": data.get("address", ""),
        "document_number": data.get("document_number", ""),
        "status": "pending_compliance_review",
        "submitted_date": datetime.now().isoformat(),
        "risk_tier": _risk_tier,
        "risk_score": _risk_score,
        "alerts": _alerts,
        "uploaded_documents": data.get("uploaded_documents", []),
        "session_id": _upload_session_id or f"inter-agent-{new_customer_id}-{datetime.now().isoformat()}",
        "upload_session_id": _upload_session_id,
        "details": details,
    }
    
    add_pending_submission(submission)
    print(f"[INFO] Created compliance submission: {new_customer_id} ({customer_name}) risk={_risk_tier} session={_upload_session_id}")
    
    if _message_handler:
        await _message_handler(
            "bank-employee-agent",
            f"Review request for customer {new_customer_id} ({customer_name}): {details}",
            "request",
            {
                "customer_id": new_customer_id,
                "request_type": request_type,
                "details": details,
                "source_agent": _current_agent,
            },
        )
    
    return (
        f"Request submitted to Bank Employee Agent:\n"
        f"- Customer: {customer_name} ({new_customer_id})\n"
        f"- Risk: {_risk_tier.upper()}\n"
        f"- Type: {request_type}\n"
        f"- Details: {details}\n"
        f"The bank compliance team will review and respond shortly."
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


@ai_function
async def resubmit_to_compliance(customer_id: str, details: str) -> str:
    """Resubmit a customer's application to the compliance team after uploading additional requested documents.
    
    Use this when the compliance team previously requested additional documents and the customer
    has now uploaded them. This reuses the existing customer ID instead of creating a new one.
    
    Args:
        customer_id: The existing customer ID (e.g., NEW-1234) from the previous submission
        details: Description of what additional documents were uploaded
        
    Returns:
        Confirmation message
    """
    from src.maf.tools.kyc_verification import get_pending_submissions, _save_pending_submissions
    
    data = _extracted_customer_data
    submissions = get_pending_submissions()
    
    # Find the existing submission
    found = None
    for submission in submissions:
        if submission.get("customer_id") == customer_id:
            found = submission
            break
    
    if not found:
        return f"No existing submission found for {customer_id}. Use request_bank_review for new submissions."
    
    # Update the submission status and add new document info
    found["status"] = "resubmitted"
    found["resubmitted_date"] = datetime.now().isoformat()
    found["resubmit_details"] = details
    # Update uploaded documents list with any new docs
    existing_docs = found.get("uploaded_documents", [])
    new_docs = data.get("uploaded_documents", [])
    for doc in new_docs:
        if doc not in existing_docs:
            existing_docs.append(doc)
    found["uploaded_documents"] = existing_docs
    
    _save_pending_submissions(submissions)
    
    customer_name = found.get("customer_name", customer_id)
    
    # Broadcast activity
    broadcast_activity_sync("inter_agent", _current_agent, {
        "action": "resubmit_to_compliance",
        "from": _current_agent,
        "to": "bank-employee-agent",
        "customer_id": customer_id,
        "customer_name": customer_name,
        "details": details[:100]
    })
    
    # Notify the employee agent
    if _message_handler:
        await _message_handler(
            "bank-employee-agent",
            f"Customer {customer_id} ({customer_name}) has uploaded the requested additional documents and resubmitted for compliance review. Details: {details}",
            "resubmission",
            {
                "customer_id": customer_id,
                "source_agent": _current_agent,
                "details": details,
            },
        )
    
    print(f"[INFO] Resubmitted {customer_id} ({customer_name}) for compliance review")
    
    return (
        f"Application resubmitted to compliance team:\n"
        f"- Customer: {customer_name} ({customer_id})\n"
        f"- Additional documents: {details}\n"
        f"The compliance team will review the updated submission."
    )


# Export tools organized by agent type
CUSTOMER_INTER_AGENT_TOOLS = [
    request_bank_review,
    resubmit_to_compliance,
    get_available_agents,
]

EMPLOYEE_INTER_AGENT_TOOLS = [
    notify_customer_agent,
    get_available_agents,
]
