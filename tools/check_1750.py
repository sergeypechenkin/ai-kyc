"""Check if 1750 is in the index."""
from azure.search.documents import SearchClient
from azure.identity import DefaultAzureCredential
from src.infrastructure.config import get_settings

settings = get_settings()
client = SearchClient(
    endpoint=settings.azure_search_endpoint,
    index_name=settings.azure_search_index_name,
    credential=DefaultAzureCredential()
)

# Get all documents and check for 1750
results = client.search('*', top=50)
print('Checking all indexed documents for 1750:')
found_docs = []
count = 0
for r in results:
    count += 1
    content = r.get('content', '')
    title = r.get('title', 'N/A')
    doc_id = r.get('id', 'N/A')
    if '1750' in content:
        found_docs.append({
            'id': doc_id,
            'title': title,
            'content': content
        })
        
print(f'Total docs checked: {count}')
print(f'Documents containing 1750: {len(found_docs)}')
for doc in found_docs:
    print(f"\nDoc ID: {doc['id']}")
    print(f"Title: {doc['title']}")
    idx = doc['content'].find('1750')
    print(f"Context around 1750: ...{doc['content'][max(0,idx-50):idx+100]}...")
