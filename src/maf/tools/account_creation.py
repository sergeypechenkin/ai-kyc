"""Account creation tools for MAF agents.

Converted from src/plugins/account_creation.py
"""

from typing import TYPE_CHECKING
from agent_framework import ai_function

if TYPE_CHECKING:
    from src.infrastructure.mock_data import CustomerRepository

# Module-level repository reference (set during initialization)
_customer_repo: "CustomerRepository | None" = None


def init_account_creation_tools(customer_repository: "CustomerRepository") -> None:
    """Initialize account creation tools with repository.
    
    Args:
        customer_repository: Repository for customer data
    """
    global _customer_repo
    _customer_repo = customer_repository


@ai_function
async def create_new_customer_account(
    first_name: str,
    last_name: str,
    email: str,
    phone: str = "",
    address: str = "",
    date_of_birth: str = "",
    nationality: str = "",
) -> str:
    """Create a new customer with a checking account.
    
    Use this when a customer wants to open a new bank account and has provided their details.
    
    Args:
        first_name: Customer's first name
        last_name: Customer's last name
        email: Customer's email address
        phone: Customer's phone number
        address: Customer's address
        date_of_birth: Date of birth (YYYY-MM-DD)
        nationality: Customer's nationality
        
    Returns:
        Confirmation message with account details
    """
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    # Check if email already exists
    existing = _customer_repo.get_by_email(email)
    if existing:
        return f"A customer with email {email} already exists (ID: {existing['id']}). Cannot create duplicate account."

    # Create customer
    customer = _customer_repo.create_customer({
        "first_name": first_name,
        "last_name": last_name,
        "email": email,
        "phone": phone,
        "address": address,
        "date_of_birth": date_of_birth,
        "nationality": nationality,
    })

    # Create checking account
    account = _customer_repo.create_account(
        customer_id=customer["id"],
        account_type="current",
        initial_balance=0.0,
    )

    return f"""Successfully created new customer and checking account!

**Customer Details:**
- Customer ID: {customer['id']}
- Name: {first_name} {last_name}
- Email: {email}

**Account Details:**
- Account ID: {account['id']}
- Account Number: {account['account_number']}
- Account Type: Current (Checking)
- Status: Pending KYC

The account is now pending KYC verification. The customer will need to submit identity documents (passport or driving license) and proof of address (utility bill) to complete verification."""


@ai_function
async def confirm_extracted_document_data(
    first_name: str,
    last_name: str,
    date_of_birth: str = "",
    nationality: str = "",
    address: str = "",
    document_type: str = "",
) -> str:
    """Show extracted document data for user confirmation.
    
    Use this after document upload to verify the information is correct before creating account.
    
    Args:
        first_name: Extracted first name
        last_name: Extracted last name  
        date_of_birth: Extracted date of birth
        nationality: Extracted nationality
        address: Extracted address
        document_type: Type of document processed
        
    Returns:
        Formatted confirmation message
    """
    return f"""I've extracted the following information from your {document_type or 'document'}:

**Personal Information:**
- First Name: {first_name or '(not detected)'}
- Last Name: {last_name or '(not detected)'}
- Date of Birth: {date_of_birth or '(not detected)'}
- Nationality: {nationality or '(not detected)'}
- Address: {address or '(not detected)'}

**Is this information correct?**

Please confirm by saying "Yes, that's correct" or let me know what needs to be corrected. You'll also need to provide:
- Email address
- Phone number (optional)

Once confirmed, I'll create your new checking account."""


@ai_function
async def record_kyc_document(
    customer_id: str,
    document_type: str,
    document_number: str = "",
    expiry_date: str = "",
    issuing_country: str = "",
) -> str:
    """Record a KYC document for a customer after it has been uploaded.
    
    Args:
        customer_id: Customer's ID
        document_type: Type of document (passport, driving_license, utility_bill)
        document_number: Document number/ID
        expiry_date: Document expiry date (YYYY-MM-DD)
        issuing_country: Country that issued the document
        
    Returns:
        Confirmation message
    """
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    # Verify customer exists
    customer = _customer_repo.get_by_id(customer_id)
    if not customer:
        return f"No customer found with ID: {customer_id}"

    # Record the document
    doc = _customer_repo.add_document(
        customer_id=customer_id,
        document_type=document_type,
        document_number=document_number,
        expiry_date=expiry_date,
        issuing_country=issuing_country,
        status="pending",
    )

    return f"""KYC Document Recorded:
- Customer: {customer['first_name']} {customer['last_name']} ({customer_id})
- Document Type: {document_type}
- Document Number: {document_number or '(not recorded)'}
- Expiry Date: {expiry_date or '(not recorded)'}
- Status: Pending Verification

The document is now queued for verification by a bank employee."""


# Export all tools as a list for easy agent configuration
ACCOUNT_CREATION_TOOLS = [
    create_new_customer_account,
    confirm_extracted_document_data,
    record_kyc_document,
]
