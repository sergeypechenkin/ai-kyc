"""Document search plugin for grounding with Azure AI Search."""

from typing import TYPE_CHECKING

from semantic_kernel.functions import kernel_function

from src.plugins.base_plugin import KycPlugin

if TYPE_CHECKING:
    from src.infrastructure.document_search import DocumentSearchService


class DocumentSearchPlugin(KycPlugin):
    """Plugin for searching bank documentation.

    Uses Azure AI Search to find relevant information from:
    - Guide to fees and charges
    - Personal account information leaflets
    - KYC guidelines and procedures
    """

    name = "document_search"
    description = "Search bank documentation for fees, account information, and KYC guidelines"

    def __init__(self, search_service: "DocumentSearchService"):
        """Initialize with document search service.

        Args:
            search_service: Azure AI Search service
        """
        super().__init__(search_service=search_service)
        self._search = search_service

    @kernel_function(
        name="search_bank_documents",
        description="Search bank documentation for information about fees, charges, account features, or KYC requirements. Use this when customers ask about bank policies, fees, account types, or procedures.",
    )
    async def search_bank_documents(self, query: str) -> str:
        """Search bank documents for relevant information.

        Args:
            query: Search query (e.g., "overdraft fees", "account opening requirements")

        Returns:
            Relevant document excerpts with citations
        """
        results = await self._search.search(query, top_k=3)

        if not results:
            return f"No relevant information found for: {query}"

        formatted_results = []
        for i, result in enumerate(results, 1):
            formatted_results.append(
                f"[Source {i}: {result['source']}]\n{result['content']}"
            )

        return (
            f"Found {len(results)} relevant document(s):\n\n"
            + "\n\n---\n\n".join(formatted_results)
        )

    @kernel_function(
        name="get_fee_information",
        description="Get specific fee information from the bank's fee schedule. Use for questions about specific transaction fees, maintenance fees, or service charges.",
    )
    async def get_fee_information(self, fee_type: str) -> str:
        """Get information about a specific fee type.

        Args:
            fee_type: Type of fee (e.g., "overdraft", "ATM withdrawal", "maintenance")

        Returns:
            Fee details with source citation
        """
        query = f"fee charge {fee_type}"
        results = await self._search.search(query, top_k=2)

        if not results:
            return f"No fee information found for: {fee_type}"

        formatted = []
        for result in results:
            formatted.append(
                f"From {result['source']}:\n{result['content']}"
            )

        return "\n\n".join(formatted)

    @kernel_function(
        name="get_account_requirements",
        description="Get requirements for opening or maintaining a bank account. Use for questions about documentation needed, eligibility, or account features.",
    )
    async def get_account_requirements(self, account_type: str = "personal") -> str:
        """Get account requirements and features.

        Args:
            account_type: Type of account (default: "personal")

        Returns:
            Account requirements and features
        """
        query = f"{account_type} account requirements features eligibility"
        results = await self._search.search(query, top_k=3)

        if not results:
            return f"No information found for {account_type} accounts"

        formatted = []
        for result in results:
            formatted.append(
                f"From {result['source']}:\n{result['content']}"
            )

        return "\n\n".join(formatted)
