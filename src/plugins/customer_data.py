"""Customer data plugin for accessing customer information."""

from typing import TYPE_CHECKING

from semantic_kernel.functions import kernel_function

from src.plugins.base_plugin import KycPlugin

if TYPE_CHECKING:
    from src.infrastructure.mock_data import CustomerRepository


class CustomerDataPlugin(KycPlugin):
    """Plugin for accessing customer data.

    Provides functions for looking up customer information,
    account details, and KYC document status.
    """

    name = "customer_data"
    description = "Access customer profiles, accounts, and KYC documents"

    def __init__(self, customer_repository: "CustomerRepository"):
        """Initialize with customer repository.

        Args:
            customer_repository: Repository for customer data access
        """
        super().__init__(customer_repository=customer_repository)
        self._repo = customer_repository

    @kernel_function(
        name="get_customer_by_email",
        description="Look up a customer by their email address. Returns customer profile including name, address, and contact info.",
    )
    def get_customer_by_email(self, email: str) -> str:
        """Get customer information by email.

        Args:
            email: Customer's email address

        Returns:
            Customer information as formatted string, or not found message
        """
        customer = self._repo.get_by_email(email)
        if not customer:
            return f"No customer found with email: {email}"

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

    @kernel_function(
        name="get_customer_by_id",
        description="Look up a customer by their customer ID. Returns full customer profile.",
    )
    def get_customer_by_id(self, customer_id: str) -> str:
        """Get customer information by ID.

        Args:
            customer_id: Customer's unique ID

        Returns:
            Customer information as formatted string
        """
        customer = self._repo.get_by_id(customer_id)
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

    @kernel_function(
        name="get_customer_kyc_status",
        description="Get the KYC verification status for a customer, including document status and verification history.",
    )
    def get_customer_kyc_status(self, customer_id: str) -> str:
        """Get KYC status for a customer.

        Args:
            customer_id: Customer's unique ID

        Returns:
            KYC status information
        """
        status = self._repo.get_kyc_status(customer_id)
        if not status:
            return f"No KYC records found for customer: {customer_id}"

        docs_info = "\n".join(
            f"  - {doc['doc_type']}: {doc['status']} (expires: {doc['expiry_date']})"
            for doc in status.get("documents", [])
        )

        return (
            f"KYC Status for Customer {customer_id}:\n"
            f"- Overall Status: {status['overall_status']}\n"
            f"- Last Review: {status['last_review_date']}\n"
            f"- Documents:\n{docs_info}"
        )

    @kernel_function(
        name="get_customer_accounts",
        description="Get all bank accounts for a customer, including account types and balances.",
    )
    def get_customer_accounts(self, customer_id: str) -> str:
        """Get accounts for a customer.

        Args:
            customer_id: Customer's unique ID

        Returns:
            Account information
        """
        accounts = self._repo.get_accounts(customer_id)
        if not accounts:
            return f"No accounts found for customer: {customer_id}"

        accounts_info = "\n".join(
            f"- {acc['account_type']} ({acc['account_number']}): €{acc['balance']:.2f} - {acc['status']}"
            for acc in accounts
        )

        return f"Accounts for Customer {customer_id}:\n{accounts_info}"

    @kernel_function(
        name="search_customers",
        description="Search for customers by name. Returns a list of matching customers.",
    )
    def search_customers(self, name: str) -> str:
        """Search customers by name.

        Args:
            name: Name to search for (first or last name)

        Returns:
            List of matching customers
        """
        customers = self._repo.search_by_name(name)
        if not customers:
            return f"No customers found matching: {name}"

        results = "\n".join(
            f"- {c['id']}: {c['first_name']} {c['last_name']} ({c['email']})"
            for c in customers
        )

        return f"Customers matching '{name}':\n{results}"
