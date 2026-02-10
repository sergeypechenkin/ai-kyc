"""Test Azure Search connection and upload."""
import sys
import os
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

print("Test 1: Loading settings...")
try:
    from src.infrastructure.config import get_settings
    settings = get_settings()
    print(f"  ✓ Search endpoint: {settings.azure_search_endpoint}")
    print(f"  ✓ Index name: {settings.azure_search_index_name}")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\nTest 2: Creating credential...")
try:
    from azure.identity import DefaultAzureCredential
    credential = DefaultAzureCredential()
    print("  ✓ DefaultAzureCredential created")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\nTest 3: Creating SearchIndexClient...")
try:
    from azure.search.documents.indexes import SearchIndexClient
    index_client = SearchIndexClient(
        endpoint=settings.azure_search_endpoint,
        credential=credential,
    )
    print("  ✓ SearchIndexClient created")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\nTest 4: Listing indexes (this verifies authentication)...")
try:
    indexes = list(index_client.list_indexes())
    print(f"  ✓ Found {len(indexes)} indexes:")
    for idx in indexes:
        print(f"    - {idx.name}")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\nTest 5: Creating SearchClient...")
try:
    from azure.search.documents import SearchClient
    search_client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=credential,
    )
    print("  ✓ SearchClient created")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\nTest 6: Uploading a test document...")
try:
    test_doc = {
        "id": "test-doc-1",
        "content": "This is a test document for Azure AI Search.",
        "title": "Test Document",
        "source": "test.txt",
        "chunk_index": 0,
        "page_number": 1,
    }
    result = search_client.upload_documents([test_doc])
    print(f"  ✓ Upload result: {result[0].succeeded}")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\nTest 7: Searching for the test document...")
try:
    results = search_client.search("test document", top=5)
    count = 0
    for r in results:
        count += 1
        print(f"  - {r['title']}: {r['content'][:50]}...")
    print(f"  ✓ Found {count} documents")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\n✓ All Azure Search tests passed!")
