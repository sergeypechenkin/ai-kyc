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
    
    The plugin can be dynamically enabled/disabled via the grounding_enabled flag.
    When disabled, agents will use their base knowledge instead of document search.
    """

    name = "document_search"
    description = "Search bank documentation for fees, account information, and KYC guidelines"

    def __init__(self, search_service: "DocumentSearchService", grounding_enabled: bool = True):
        """Initialize with document search service.

        Args:
            search_service: Azure AI Search service
            grounding_enabled: Whether document grounding is enabled
        """
        super().__init__(search_service=search_service)
        self._search = search_service
        self._grounding_enabled = grounding_enabled

    @property
    def grounding_enabled(self) -> bool:
        """Check if grounding is enabled."""
        return self._grounding_enabled

    @grounding_enabled.setter
    def grounding_enabled(self, value: bool) -> None:
        """Set grounding enabled state."""
        self._grounding_enabled = value

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
        if not self._grounding_enabled:
            return "Document grounding is disabled. I cannot search bank documents at this time. Please answer based on general banking knowledge."
        
        import re
        
        results = await self._search.search(query, top_k=10)

        if not results:
            return f"No relevant information found for: {query}"

        # For fee-related queries, prioritize results with query terms near euro amounts
        fee_keywords = ["fee", "charge", "cost", "price", "rate"]
        is_fee_query = any(kw in query.lower() for kw in fee_keywords)
        
        if is_fee_query:
            query_words = [w.lower() for w in query.split() if len(w) > 2]
            
            def relevance_score(content: str) -> int:
                """Score based on having query terms near euro amounts."""
                content_lower = content.lower()
                score = 0
                
                # Points for each query word found
                for word in query_words:
                    if word in content_lower:
                        score += 5
                
                # Check for euro amounts
                euro_pattern = r'€\d+[.,]?\d*'
                euro_matches = list(re.finditer(euro_pattern, content))
                if euro_matches:
                    score += 5
                
                # Bonus if query words appear within 200 chars of euro amounts
                for word in query_words:
                    word_pos = content_lower.find(word)
                    if word_pos >= 0:
                        for match in euro_matches:
                            if abs(match.start() - word_pos) < 200:
                                score += 15
                                break
                
                return score
            
            results_scored = [(r, relevance_score(r["content"])) for r in results]
            results_scored.sort(key=lambda x: (-x[1], -x[0].get("score", 0)))
            results = [r for r, _ in results_scored]

        formatted_results = []
        for i, result in enumerate(results[:5], 1):  # Return top 5
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
        if not self._grounding_enabled:
            return "Document grounding is disabled. I cannot look up specific fee information at this time. Please answer based on general banking knowledge."
        
        import re
        
        query = f"{fee_type} fee"
        results = await self._search.search(query, top_k=10)

        if not results:
            return f"No fee information found for: {fee_type}"

        # Prioritize results that contain the fee type AND a euro amount nearby
        fee_type_lower = fee_type.lower()
        
        def relevance_score(content: str) -> int:
            """Score based on having fee type near euro amounts."""
            content_lower = content.lower()
            score = 0
            
            # Check if fee type appears in content
            if fee_type_lower in content_lower:
                score += 10
            
            # Check for euro amounts (€X.XX pattern)
            euro_pattern = r'€\d+[.,]?\d*'
            if re.search(euro_pattern, content):
                score += 5
            
            # Bonus if fee type and euro amount appear within 200 chars of each other
            fee_pos = content_lower.find(fee_type_lower)
            if fee_pos >= 0:
                euro_matches = list(re.finditer(euro_pattern, content))
                for match in euro_matches:
                    if abs(match.start() - fee_pos) < 200:
                        score += 20
                        break
            
            return score
        
        # Sort by relevance score (descending), then by original search score
        results_scored = [(r, relevance_score(r["content"])) for r in results]
        results_scored.sort(key=lambda x: (-x[1], -x[0].get("score", 0)))
        prioritized = [r for r, _ in results_scored]

        formatted = []
        for result in prioritized[:5]:  # Return top 5 after reordering
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
        if not self._grounding_enabled:
            return "Document grounding is disabled. I cannot look up account requirements at this time. Please answer based on general banking knowledge."
        
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
