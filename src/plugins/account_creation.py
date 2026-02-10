"""Account creation plugin for new customer onboarding."""

from typing import TYPE_CHECKING

from semantic_kernel.functions import kernel_function

from src.plugins.base_plugin import KycPlugin

if TYPE_CHECKING:
    from src.infrastructure.mock_data import CustomerRepository


class AccountCreationPlugin(KycPlugin):
    """Plugin for creating new customer accounts.

    Handles the account creation workflow including:
    - Processing extracted document data
    - Creating customer records
    - Creating checking accounts
    - Recording KYC documents
    """

    name = "account_creation"
    description = "Create new customer accounts and process onboarding documents"

    def __init__(self, customer_repository: "CustomerRepository"):
        """Initialize with customer repository.

        Args:
            customer_repository: Repository for customer data
        """
        super().__init__(customer_repository=customer_repository)
        self._repo = customer_repository

    @kernel_function(
        name="create_new_customer_account",
        description="Create a new customer with a checking account after verifying their information. Use this when a customer wants to open a new bank account and has provided their details.",
    )
    async def create_new_customer_account(
        self,
        first_name: str,
        last_name: str,
        email: str,
        phone: str = "",
        address: str = "",
        date_of_birth: str = "",
        nationality: str = "",
    ) -> str:
        """Create a new customer with a checking account.

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
        # Check if email already exists
        existing = self._repo.get_by_email(email)
        if existing:
            return f"A customer with email {email} already exists (ID: {existing['id']}). Cannot create duplicate account."

        # Create customer
        customer = self._repo.create_customer({
            "first_name": first_name,
            "last_name": last_name,
            "email": email,
            "phone": phone,
            "address": address,
            "date_of_birth": date_of_birth,
            "nationality": nationality,
        })

        # Create checking account
        account = self._repo.create_account(
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

    @kernel_function(
        name="confirm_extracted_document_data",
        description="Show extracted document data to user for confirmation before creating account. Use this after document upload to verify the information is correct.",
    )
    async def confirm_extracted_document_data(
        self,
        first_name: str,
        last_name: str,
        date_of_birth: str = "",
        nationality: str = "",
        address: str = "",
        document_type: str = "",
    ) -> str:
        """Display extracted data for user confirmation.

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

    @kernel_function(
        name="record_kyc_document",
        description="Record a KYC document for a customer after it has been uploaded.",
    )
    async def record_kyc_document(
        self,
        customer_id: str,
        doc_type: str,
        file_path: str,
        expiry_date: str = "",
    ) -> str:
        """Record a KYC document for a customer.

        Args:
            customer_id: Customer ID
            doc_type: Document type (passport, driving_license, utility_bill)
            file_path: Path where document is stored
            expiry_date: Document expiry date

        Returns:
            Confirmation message
        """
        document = self._repo.add_kyc_document(
            customer_id=customer_id,
            doc_type=doc_type,
            file_path=file_path,
            expiry_date=expiry_date,
        )

        return f"KYC document recorded: {doc_type} (ID: {document['id']}) for customer {customer_id}. Status: Pending verification."
