"""Customer data tools for MAF agents.

Converted from src/plugins/customer_data.py
"""

from typing import TYPE_CHECKING
from agent_framework import ai_function
from src.maf.activity import broadcast_activity_sync

if TYPE_CHECKING:
    from src.infrastructure.mock_data import CustomerRepository

# Module-level repository reference (set during initialization)
_customer_repo: "CustomerRepository | None" = None


def init_customer_tools(customer_repository: "CustomerRepository") -> None:
    """Initialize customer tools with repository.
    
    Args:
        customer_repository: Repository for customer data access
    """
    global _customer_repo
    _customer_repo = customer_repository


@ai_function
def get_customer_by_email(email: str) -> str:
    """Look up a customer by their email address.
    
    Returns customer profile including name, address, and contact info.
    
    Args:
        email: Customer's email address
        
    Returns:
        Customer information as formatted string, or not found message
    """
    broadcast_activity_sync("tool_call", "System", {
        "tool": "get_customer_by_email",
        "args": {"email": email}
    })
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    customer = _customer_repo.get_by_email(email)
    if not customer:
        broadcast_activity_sync("tool_result", "System", {
            "tool": "get_customer_by_email",
            "result": "not_found"
        })
        return f"No customer found with email: {email}"

    broadcast_activity_sync("tool_result", "System", {
        "tool": "get_customer_by_email",
        "result": "found",
        "customer_id": customer["id"]
    })
    
    return (
        f"Customer Found:\n"
        f"- ID: {customer['id']}\n"
        f"- Name: {customer['first_name']} {customer['last_name']}\n"
        f"- Email: {customer['email']}\n"
        f"- Phone: {customer['phone']}\n"
        f"- Address: {customer['address']}\n"
        f"- Date of Birth: {customer['date_of_birth']}\n"
        f"- Nationality: {customer['nationality']}"
    )


@ai_function
def get_customer_by_id(customer_id: str) -> str:
    """Look up a customer by their customer ID.
    
    Returns full customer profile.
    
    Args:
        customer_id: Customer's unique ID
        
    Returns:
        Customer information as formatted string
    """
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    customer = _customer_repo.get_by_id(customer_id)
    if not customer:
        return f"No customer found with ID: {customer_id}"

    return (
        f"Customer Found:\n"
        f"- ID: {customer['id']}\n"
        f"- Name: {customer['first_name']} {customer['last_name']}\n"
        f"- Email: {customer['email']}\n"
        f"- Phone: {customer['phone']}\n"
        f"- Address: {customer['address']}\n"
        f"- Date of Birth: {customer['date_of_birth']}\n"
        f"- Nationality: {customer['nationality']}"
    )


@ai_function
def get_customer_kyc_status(customer_id: str) -> str:
    """Get the KYC verification status for a customer.
    
    Includes document status and verification history.
    
    Args:
        customer_id: Customer's unique ID
        
    Returns:
        KYC status information
    """
    broadcast_activity_sync("tool_call", "System", {
        "tool": "get_customer_kyc_status",
        "args": {"customer_id": customer_id}
    })
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    customer = _customer_repo.get_by_id(customer_id)
    if not customer:
        return f"No customer found with ID: {customer_id}"

    # Use get_kyc_status which returns docs and status together
    kyc_status = _customer_repo.get_kyc_status(customer_id)
    
    if not kyc_status:
        broadcast_activity_sync("tool_result", "System", {
            "tool": "get_customer_kyc_status",
            "result": "no_kyc_data"
        })
        return f"No KYC data found for customer {customer_id}"

    docs = kyc_status.get("documents", [])
    overall_status = kyc_status.get("overall_status", "unknown")
    last_review = kyc_status.get("last_review_date", "N/A")

    broadcast_activity_sync("tool_result", "System", {
        "tool": "get_customer_kyc_status",
        "customer_id": customer_id,
        "docs_count": len(docs),
        "overall_status": overall_status
    })

    status_lines = [
        f"KYC Status for {customer['first_name']} {customer['last_name']} ({customer_id}):",
        f"",
        f"Overall Status: {overall_status.upper()}",
        f"Last Review: {last_review}",
        "",
        "Documents:",
    ]

    for doc in docs:
        doc_type = doc.get("doc_type", doc.get("document_type", "unknown"))
        doc_status = doc.get("status", "unknown")
        expiry = doc.get("expiry_date", "N/A")
        status_lines.append(
            f"  - {doc_type}: {doc_status} (expires: {expiry})"
        )

    if not docs:
        status_lines.append("  No documents on file")

    return "\n".join(status_lines)


@ai_function
def get_customer_accounts(customer_id: str) -> str:
    """Get all accounts for a customer.
    
    Args:
        customer_id: Customer's unique ID
        
    Returns:
        Account information
    """
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    customer = _customer_repo.get_by_id(customer_id)
    if not customer:
        return f"No customer found with ID: {customer_id}"

    accounts = _customer_repo.get_accounts(customer_id)
    if not accounts:
        return f"No accounts found for customer {customer_id}"

    lines = [f"Accounts for customer {customer_id}:"]
    for acc in accounts:
        lines.append(
            f"  - {acc['account_type'].title()}: {acc['account_number']} "
            f"(Status: {acc['status']}, Balance: ${acc.get('balance', 0):.2f})"
        )

    return "\n".join(lines)


@ai_function
def search_customers(query: str) -> str:
    """Search for customers by name or email.
    
    Args:
        query: Search query (name or email fragment)
        
    Returns:
        List of matching customers
    """
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    results = _customer_repo.search(query)
    if not results:
        return f"No customers found matching: {query}"

    lines = [f"Found {len(results)} customer(s) matching '{query}':"]
    for customer in results[:10]:  # Limit to 10 results
        lines.append(
            f"  - {customer['id']}: {customer['first_name']} {customer['last_name']} "
            f"({customer['email']})"
        )

    return "\n".join(lines)


# Export all tools as a list for easy agent configuration
CUSTOMER_DATA_TOOLS = [
    get_customer_by_email,
    get_customer_by_id,
    get_customer_kyc_status,
    get_customer_accounts,
    search_customers,
]
