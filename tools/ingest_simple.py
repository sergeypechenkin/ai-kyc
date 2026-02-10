"""Simple document ingestion with detailed logging."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from dotenv import load_dotenv
load_dotenv()

print("Step 1: Imports...")
from azure.identity import ClientSecretCredential
from azure.search.documents import SearchClient
from src.infrastructure.config import get_settings

print("Step 2: Settings...")
settings = get_settings()

print("Step 3: Credentials...")
credential = ClientSecretCredential(
    tenant_id=os.environ["AZURE_TENANT_ID"],
    client_id=os.environ["AZURE_CLIENT_ID"],
    client_secret=os.environ["AZURE_CLIENT_SECRET"],
)

print("Step 4: Search client...")
search_client = SearchClient(
    endpoint=settings.azure_search_endpoint,
    index_name=settings.azure_search_index_name,
    credential=credential,
)

print("Step 5: Loading PyMuPDF...")
import fitz
print(f"  PyMuPDF version: {fitz.version}")

print("Step 6: Finding PDFs...")
data_dir = Path(__file__).parent.parent / "data" / "bank-documents"
pdfs = list(data_dir.glob("*.pdf"))
print(f"  Found {len(pdfs)} PDFs")

documents = []
doc_id = 0

for pdf_path in pdfs:
    print(f"\nStep 7: Processing {pdf_path.name}...")
    
    print("  7a: Opening PDF...")
    doc = fitz.open(str(pdf_path))
    print(f"  7b: PDF has {len(doc)} pages")
    
    text_parts = []
    for i, page in enumerate(doc):
        print(f"  7c: Extracting page {i+1}/{len(doc)}...", end=" ", flush=True)
        text = page.get_text()
        text_parts.append(text)
        print(f"({len(text)} chars)")
    
    doc.close()
    print("  7d: PDF closed")
    
    full_text = "\n".join(text_parts)
    print(f"  7e: Total text: {len(full_text)} chars")
    
    # Simple chunking
    chunk_size = 1000
    chunks = [full_text[i:i+chunk_size] for i in range(0, len(full_text), chunk_size)]
    print(f"  7f: Created {len(chunks)} chunks")
    
    for i, chunk in enumerate(chunks):
        doc_id += 1
        documents.append({
            "id": str(doc_id),
            "content": chunk,
            "title": pdf_path.stem.replace("-", " ").replace("_", " ").title(),
            "source": pdf_path.name,
            "chunk_index": i,
            "page_number": 0,
        })

print(f"\nStep 8: Uploading {len(documents)} documents...")
result = search_client.upload_documents(documents)
succeeded = sum(1 for r in result if r.succeeded)
print(f"  Uploaded: {succeeded}/{len(documents)}")

print("\n✓ Done!")
