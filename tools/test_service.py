"""Test the document search service directly."""
import asyncio
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.infrastructure.document_search import DocumentSearchService

async def test():
    service = DocumentSearchService()
    
    # Test with increased top_k
    results = await service.search("account maintenance fee", top_k=5)
    print(f"Got {len(results)} results")
    for i, r in enumerate(results):
        score = r.get("score", 0)
        has_fee = "4.50" in r["content"]
        print(f"Result {i+1}: score={score:.2f}, has_fee_amount={has_fee}")
        if has_fee:
            print("-" * 40)
            print(r["content"][:600])
            print()

asyncio.run(test())
