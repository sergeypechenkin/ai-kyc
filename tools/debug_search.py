"""Debug script to check indexed chunks."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from azure.identity import DefaultAzureCredential
from azure.search.documents import SearchClient
from src.infrastructure.config import get_settings

settings = get_settings()
credential = DefaultAzureCredential()
client = SearchClient(
    endpoint=settings.azure_search_endpoint,
    index_name=settings.azure_search_index_name,
    credential=credential
)

# Get all documents to see chunks
results = list(client.search("*", top=30))
print(f"Total chunks: {len(results)}")

for r in results:
    content = r["content"]
    if "4.50" in content or "maintenance fee" in content.lower():
        print("=" * 80)
        print(f"FOUND in Chunk {r['chunk_index']} from {r['source']}")
        print("-" * 80)
        print(content[:1500])
        print()
