"""KYC verification plugin for bank employee operations."""

from typing import TYPE_CHECKING
from datetime import datetime

from semantic_kernel.functions import kernel_function

from src.plugins.base_plugin import KycPlugin

if TYPE_CHECKING:
    from src.infrastructure.mock_data import CustomerRepository


class KycVerificationPlugin(KycPlugin):
    """Plugin for KYC verification operations.

    Provides functions for bank employees to:
    - Verify customer documents
    - Approve or reject KYC applications
    - Request additional information
    - Update verification status
    """

    name = "kyc_verification"
    description = "Perform KYC verification operations on customer applications"

    def __init__(self, customer_repository: "CustomerRepository"):
        """Initialize with customer repository.

        Args:
            customer_repository: Repository for customer data access
        """
        super().__init__(customer_repository=customer_repository)
        self._repo = customer_repository

    @kernel_function(
        name="verify_document",
        description="Verify a customer's submitted document. Checks document validity, expiry, and matches against customer records.",
    )
    def verify_document(
        self,
        customer_id: str,
        document_type: str,
    ) -> str:
        """Verify a customer document.

        Args:
            customer_id: Customer's ID
            document_type: Type of document (passport, driving_license, utility_bill)

        Returns:
            Verification result
        """
        # Get document from mock data
        doc = self._repo.get_document(customer_id, document_type)

        if not doc:
            return f"No {document_type} found for customer {customer_id}"

        # Check expiry
        expiry = datetime.strptime(doc["expiry_date"], "%Y-%m-%d")
        is_expired = expiry < datetime.now()

        # Simulate verification logic
        verification_result = {
            "document_type": document_type,
            "status": "expired" if is_expired else doc["status"],
            "expiry_date": doc["expiry_date"],
            "verified_at": datetime.now().isoformat(),
        }

        if is_expired:
            return (
                f"Document Verification Failed:\n"
                f"- Document: {document_type}\n"
                f"- Status: EXPIRED\n"
                f"- Expired on: {doc['expiry_date']}\n"
                f"- Action Required: Request updated document from customer"
            )

        if doc["status"] == "verified":
            return (
                f"Document Verification Passed:\n"
                f"- Document: {document_type}\n"
                f"- Status: VERIFIED\n"
                f"- Valid until: {doc['expiry_date']}"
            )

        return (
            f"Document Pending Review:\n"
            f"- Document: {document_type}\n"
            f"- Status: {doc['status'].upper()}\n"
            f"- Valid until: {doc['expiry_date']}"
        )

    @kernel_function(
        name="approve_kyc",
        description="Approve a customer's KYC application. Use after all documents have been verified.",
    )
    def approve_kyc(
        self,
        customer_id: str,
        notes: str = "",
    ) -> str:
        """Approve KYC for a customer.

        Args:
            customer_id: Customer's ID
            notes: Optional approval notes

        Returns:
            Approval confirmation
        """
        # Update status in mock data
        result = self._repo.update_kyc_status(
            customer_id,
            status="approved",
            reviewer="bank-employee-agent",
            notes=notes,
        )

        if not result:
            return f"Failed to approve KYC for customer {customer_id}"

        return (
            f"KYC Approved:\n"
            f"- Customer: {customer_id}\n"
            f"- Status: APPROVED\n"
            f"- Approved at: {datetime.now().isoformat()}\n"
            f"- Notes: {notes or 'None'}\n"
            f"Customer can now proceed with account services."
        )

    @kernel_function(
        name="reject_kyc",
        description="Reject a customer's KYC application with a reason.",
    )
    def reject_kyc(
        self,
        customer_id: str,
        reason: str,
    ) -> str:
        """Reject KYC for a customer.

        Args:
            customer_id: Customer's ID
            reason: Rejection reason

        Returns:
            Rejection confirmation
        """
        result = self._repo.update_kyc_status(
            customer_id,
            status="rejected",
            reviewer="bank-employee-agent",
            notes=reason,
        )

        if not result:
            return f"Failed to update KYC status for customer {customer_id}"

        return (
            f"KYC Rejected:\n"
            f"- Customer: {customer_id}\n"
            f"- Status: REJECTED\n"
            f"- Reason: {reason}\n"
            f"- Rejected at: {datetime.now().isoformat()}\n"
            f"Customer must be notified of the rejection and reason."
        )

    @kernel_function(
        name="request_additional_documents",
        description="Request additional documents from a customer for KYC verification.",
    )
    def request_additional_documents(
        self,
        customer_id: str,
        documents_needed: str,
        reason: str,
    ) -> str:
        """Request additional documents from customer.

        Args:
            customer_id: Customer's ID
            documents_needed: List of documents needed
            reason: Reason for the request

        Returns:
            Request confirmation
        """
        result = self._repo.update_kyc_status(
            customer_id,
            status="pending_documents",
            reviewer="bank-employee-agent",
            notes=f"Documents requested: {documents_needed}. Reason: {reason}",
        )

        return (
            f"Document Request Created:\n"
            f"- Customer: {customer_id}\n"
            f"- Documents Needed: {documents_needed}\n"
            f"- Reason: {reason}\n"
            f"- Status: PENDING_DOCUMENTS\n"
            f"Customer must be notified to submit the requested documents."
        )

    @kernel_function(
        name="get_pending_reviews",
        description="Get list of customers with pending KYC reviews.",
    )
    def get_pending_reviews(self) -> str:
        """Get all pending KYC reviews.

        Returns:
            List of pending reviews
        """
        pending = self._repo.get_pending_reviews()

        if not pending:
            return "No pending KYC reviews at this time."

        lines = []
        for review in pending:
            lines.append(
                f"- {review['customer_id']}: {review['customer_name']} - "
                f"Status: {review['status']} (since {review['submitted_date']})"
            )

        return f"Pending KYC Reviews ({len(pending)}):\n" + "\n".join(lines)
