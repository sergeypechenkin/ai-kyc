"""Document search tools for MAF agents.

Converted from src/plugins/document_search.py
Uses Azure AI Search for document grounding.
"""

import re
from typing import TYPE_CHECKING
from agent_framework import ai_function
from src.maf.activity import broadcast_activity_sync

if TYPE_CHECKING:
    from src.infrastructure.document_search import DocumentSearchService

# Module-level service reference (set during initialization)
_search_service: "DocumentSearchService | None" = None
_grounding_enabled: bool = True


def init_document_search_tools(
    search_service: "DocumentSearchService",
    grounding_enabled: bool = True
) -> None:
    """Initialize document search tools with service.
    
    Args:
        search_service: Azure AI Search service
        grounding_enabled: Whether document grounding is enabled
    """
    global _search_service, _grounding_enabled
    _search_service = search_service
    _grounding_enabled = grounding_enabled


def set_grounding_enabled(enabled: bool) -> None:
    """Enable or disable document grounding.
    
    Args:
        enabled: Whether grounding should be enabled
    """
    global _grounding_enabled
    _grounding_enabled = enabled


@ai_function
async def search_bank_documents(query: str) -> str:
    """Search bank documentation for information.
    
    Search for information about fees, charges, account features, or KYC requirements.
    Use this when customers ask about bank policies, fees, account types, or procedures.
    
    Args:
        query: Search query (e.g., "overdraft fees", "account opening requirements")
        
    Returns:
        Relevant document excerpts with citations
    """
    print(f"[DEBUG] search_bank_documents called, grounding_enabled={_grounding_enabled}")
    
    # Broadcast tool call
    broadcast_activity_sync("tool_call", "System", {
        "tool": "search_bank_documents",
        "args": {"query": query},
        "grounding_enabled": _grounding_enabled
    })
    
    if not _grounding_enabled:
        broadcast_activity_sync("grounding", "System", {
            "status": "disabled",
            "query": query
        })
        return "Document grounding is disabled. I cannot search bank documents at this time. Please answer based on general banking knowledge."
    
    if _search_service is None:
        return "Error: Document search service not initialized"
    
    results = await _search_service.search(query, top_k=10)

    if not results:
        broadcast_activity_sync("grounding", "System", {
            "status": "no_results",
            "query": query,
            "results_count": 0
        })
        return f"No relevant information found for: {query}"

    # Broadcast grounding search
    broadcast_activity_sync("grounding", "System", {
        "status": "found",
        "query": query,
        "results_count": len(results),
        "sources": [r.get("source", "unknown")[:50] for r in results[:5]]
    })

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


@ai_function
async def get_fee_information(fee_type: str) -> str:
    """Get specific fee information from the bank's fee schedule.
    
    Use for questions about specific transaction fees, maintenance fees, or service charges.
    
    Args:
        fee_type: Type of fee (e.g., "overdraft", "ATM withdrawal", "maintenance")
        
    Returns:
        Fee details with source citation
    """
    # Broadcast tool call
    broadcast_activity_sync("tool_call", "System", {
        "tool": "get_fee_information",
        "args": {"fee_type": fee_type},
        "grounding_enabled": _grounding_enabled
    })
    
    if not _grounding_enabled:
        broadcast_activity_sync("grounding", "System", {
            "status": "disabled",
            "query": f"fee: {fee_type}"
        })
        return "Document grounding is disabled. I cannot look up specific fee information at this time. Please answer based on general banking knowledge."
    
    if _search_service is None:
        return "Error: Document search service not initialized"
    
    query = f"{fee_type} fee"
    results = await _search_service.search(query, top_k=10)

    if not results:
        return f"No fee information found for: {fee_type}"

    # Prioritize results that contain the fee type AND a euro amount nearby
    fee_type_lower = fee_type.lower()
    
    def relevance_score(content: str) -> int:
        """Score based on having fee type near euro amounts."""
        content_lower = content.lower()
        score = 0
        
        # Must contain fee type
        if fee_type_lower not in content_lower:
            return 0
        
        score += 10
        
        # Check for euro amounts
        euro_pattern = r'€\d+[.,]?\d*'
        euro_matches = list(re.finditer(euro_pattern, content))
        if euro_matches:
            score += 5
        
        # Bonus if fee type appears within 150 chars of euro amounts
        fee_type_pos = content_lower.find(fee_type_lower)
        for match in euro_matches:
            if abs(match.start() - fee_type_pos) < 150:
                score += 20
                break
        
        return score

    results_scored = [(r, relevance_score(r["content"])) for r in results]
    results_scored.sort(key=lambda x: -x[1])
    
    # Filter to only results with score > 0
    results = [r for r, s in results_scored if s > 0]

    if not results:
        return f"No specific fee information found for: {fee_type}. Try searching with different terms."

    # Return only the most relevant result
    result = results[0]
    return (
        f"**Fee Information for '{fee_type}'**\n\n"
        f"Source: {result['source']}\n\n"
        f"{result['content']}"
    )


# Export all tools as a list for easy agent configuration
DOCUMENT_SEARCH_TOOLS = [
    search_bank_documents,
    get_fee_information,
]
