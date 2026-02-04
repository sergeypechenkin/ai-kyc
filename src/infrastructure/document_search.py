"""Document search service for Azure AI Search integration."""

from typing import Any

from src.infrastructure.config import get_settings


class DocumentSearchService:
    """Service for searching bank documents using Azure AI Search.

    When Azure AI Search is not configured, returns mock results
    for demonstration purposes.
    """

    def __init__(self):
        """Initialize the document search service."""
        self._settings = get_settings()
        self._client = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        """Initialize Azure AI Search client if configured."""
        if not self._settings.azure_search_configured:
            return

        try:
            from azure.identity import DefaultAzureCredential
            from azure.search.documents import SearchClient

            credential = DefaultAzureCredential()
            self._client = SearchClient(
                endpoint=self._settings.azure_search_endpoint,
                index_name=self._settings.azure_search_index_name,
                credential=credential,
            )
        except ImportError:
            pass  # Azure SDK not installed

    async def search(self, query: str, top_k: int = 3) -> list[dict[str, Any]]:
        """Search for documents matching the query.

        Args:
            query: Search query
            top_k: Maximum number of results

        Returns:
            List of search results with content and source
        """
        if self._client:
            return await self._azure_search(query, top_k)
        else:
            return self._mock_search(query, top_k)

    async def _azure_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Search using Azure AI Search.

        Args:
            query: Search query
            top_k: Maximum results

        Returns:
            List of results
        """
        results = []
        try:
            search_results = self._client.search(  # type: ignore
                search_text=query,
                top=top_k,
                select=["content", "title", "source"],
            )

            for result in search_results:
                results.append({
                    "content": result.get("content", ""),
                    "source": result.get("source", result.get("title", "Unknown")),
                    "score": result.get("@search.score", 0),
                })
        except Exception as e:
            # Log error and fall back to mock
            print(f"Azure Search error: {e}")
            return self._mock_search(query, top_k)

        return results

    def _mock_search(self, query: str, top_k: int) -> list[dict[str, Any]]:
        """Return mock search results for demonstration.

        Args:
            query: Search query
            top_k: Maximum results

        Returns:
            Mock results based on query keywords
        """
        query_lower = query.lower()

        # Mock bank documentation content
        mock_docs = [
            {
                "keywords": ["fee", "charge", "cost", "price", "overdraft"],
                "source": "Guide to Fees and Charges for Personal Accounts",
                "content": """Standard Current Account Fees:
- Monthly maintenance fee: €4.50 (waived if credit balance >€2,500)
- ATM withdrawal (Zava Bank): Free
- ATM withdrawal (other Irish banks): €0.35
- ATM withdrawal (international): €2.50 + 1.75% foreign exchange fee
- Overdraft arrangement fee: €25 per annum
- Overdraft interest rate: 13.5% APR (variable)
- Unpaid item fee: €10.16 per item
- Paper statement: €2.50 (e-statements free)
- Debit card contactless payment: Free""",
            },
            {
                "keywords": ["account", "open", "opening", "requirement", "document", "kyc", "identity"],
                "source": "Information Leaflet for Zava Bank Personal Account",
                "content": """Account Opening Requirements:
To open a personal bank account, you'll need:
1. Valid photo ID (Passport, Driving License, or National ID Card)
2. Proof of address (utility bill, bank statement, or government letter dated within 3 months)
3. PPS Number (for Irish residents)

For non-residents, additional documentation may be required:
- Proof of employment or student status in Ireland
- Reference from existing bank

Processing time: 3-5 business days for standard applications
Same-day activation available for existing customers""",
            },
            {
                "keywords": ["transfer", "payment", "sepa", "international", "wire"],
                "source": "Guide to Fees and Charges for Personal Accounts",
                "content": """Payment and Transfer Fees:
- SEPA credit transfer (online): Free
- SEPA credit transfer (branch): €5.00
- SEPA direct debit: Free
- Standing order: Free
- International transfer (SWIFT): €25 + correspondent bank charges
- International transfer (online): €15 + 0.25% (min €10, max €50)
- Emergency same-day SEPA: €10.00
- Telegraphic transfer: €35.00""",
            },
            {
                "keywords": ["savings", "interest", "deposit", "rate"],
                "source": "Information Leaflet for Zava Bank Personal Account",
                "content": """Savings Account Features:
- Regular Saver Account: Up to 3.00% AER (max €1,000/month)
- Demand Deposit: 0.50% AER (instant access)
- Fixed Term Deposit (1 year): 2.75% AER
- Fixed Term Deposit (2 years): 3.00% AER
- Junior Saver (under 18s): 2.50% AER

Note: Interest rates are subject to DIRT (Deposit Interest Retention Tax) at 33%""",
            },
            {
                "keywords": ["card", "debit", "visa", "contactless", "limit"],
                "source": "Guide to Fees and Charges for Personal Accounts",
                "content": """Debit Card Information:
- Card type: Visa Debit
- Contactless limit: €50 per transaction
- Daily ATM withdrawal limit: €700
- Daily purchase limit: €2,500
- Card replacement (lost/stolen): €5.00
- Card replacement (damaged): Free
- Emergency card abroad: €50.00
- PIN reminder: Free (via app/online)""",
            },
        ]

        # Find matching documents
        results = []
        for doc in mock_docs:
            if any(kw in query_lower for kw in doc["keywords"]):
                results.append({
                    "content": doc["content"],
                    "source": doc["source"],
                    "score": 0.85,  # Mock relevance score
                })

        # If no matches, return generic response
        if not results:
            results.append({
                "content": "For specific information about your query, please contact Zava Bank customer service at 1890 724 724 or visit your local branch.",
                "source": "Zava Bank Customer Service",
                "score": 0.5,
            })

        return results[:top_k]
