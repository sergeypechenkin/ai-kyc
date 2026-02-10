"""Debug PDF extraction to see what's happening."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import fitz

data_dir = Path(__file__).parent.parent / "data" / "bank-documents"

for pdf_path in data_dir.glob("*.pdf"):
    print(f"=== {pdf_path.name} ===")
    
    with fitz.open(pdf_path) as doc:
        print(f"  Pages: {len(doc)}")
        
        # Check first page text
        if len(doc) > 0:
            page = doc[0]
            text = page.get_text()
            print(f"  First page text length: {len(text)} chars")
            print(f"  First 200 chars: {text[:200]}")
            
            # Check if structured extraction works
            page_dict = page.get_text("dict")
            blocks = page_dict.get("blocks", [])
            print(f"  Blocks on first page: {len(blocks)}")
    
    print()

# Now test the actual extraction function
print("=== Testing extract_text_from_pdf ===")
from tools.ingest_documents import extract_text_from_pdf, chunk_text

for pdf_path in data_dir.glob("*.pdf"):
    print(f"\n{pdf_path.name}:")
    text = extract_text_from_pdf(pdf_path)
    print(f"  Extracted text length: {len(text)} chars")
    
    chunks = chunk_text(text)
    print(f"  Number of chunks: {len(chunks)}")
    
    if chunks:
        print(f"  First chunk preview: {chunks[0][:200]}")
