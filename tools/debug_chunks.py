"""Debug script to test the improved relevance scoring."""
import asyncio
import re
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.document_search import DocumentSearchService

def relevance_score(content: str, query: str) -> int:
    """Score based on having query terms near euro amounts."""
    content_lower = content.lower()
    query_words = [w.lower() for w in query.split() if len(w) > 2]
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

async def test():
    service = DocumentSearchService()
    query = "account maintenance fee"
    
    print(f"=== Testing improved relevance for '{query}' ===")
    results = await service.search(query, top_k=10)
    
    # Apply relevance scoring
    results_scored = [(r, relevance_score(r["content"], query)) for r in results]
    results_scored.sort(key=lambda x: (-x[1], -x[0].get("score", 0)))
    
    print(f"Total results: {len(results)}")
    print()
    
    for i, (r, score) in enumerate(results_scored[:5], 1):
        has_450 = "4.50" in r["content"]
        has_maint = "maintenance fee" in r["content"].lower()
        print(f"Result {i}: relevance_score={score}, has_450={has_450}, has_maint={has_maint}")
        print(f"  {r['content'][:250]}")
        print()

asyncio.run(test())
