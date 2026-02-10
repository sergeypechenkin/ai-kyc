"""Simple test script to debug PDF extraction."""
import sys
from pathlib import Path

# Test 1: Check if fitz (PyMuPDF) can be imported
print("Test 1: Importing fitz (PyMuPDF)...")
try:
    import fitz
    print(f"  ✓ PyMuPDF version: {fitz.version}")
except ImportError as e:
    print(f"  ✗ Failed to import fitz: {e}")
    print("  Run: pip install PyMuPDF")
    sys.exit(1)

# Test 2: List PDF files
data_dir = Path(__file__).parent.parent / "data" / "bank-documents"
print(f"\nTest 2: Listing PDFs in {data_dir}...")
pdf_files = list(data_dir.glob("*.pdf"))
if not pdf_files:
    print("  ✗ No PDF files found!")
    sys.exit(1)

for pdf in pdf_files:
    size_kb = pdf.stat().st_size / 1024
    print(f"  - {pdf.name} ({size_kb:.1f} KB)")

# Test 3: Try to open the first PDF
first_pdf = pdf_files[0]
print(f"\nTest 3: Opening {first_pdf.name}...")
try:
    doc = fitz.open(str(first_pdf))
    print(f"  ✓ Opened successfully: {len(doc)} pages")
    doc.close()
except Exception as e:
    print(f"  ✗ Failed to open: {e}")
    sys.exit(1)

# Test 4: Extract text from first page
print(f"\nTest 4: Extracting text from first page...")
try:
    doc = fitz.open(str(first_pdf))
    page = doc[0]
    text = page.get_text()
    doc.close()
    print(f"  ✓ Extracted {len(text)} characters")
    print(f"  Preview: {text[:200]}...")
except Exception as e:
    print(f"  ✗ Failed to extract text: {e}")
    sys.exit(1)

# Test 5: Extract text from ALL pages
print(f"\nTest 5: Extracting text from all pages...")
try:
    doc = fitz.open(str(first_pdf))
    full_text = ""
    for i, page in enumerate(doc):
        print(f"  Processing page {i+1}/{len(doc)}...", end="\r")
        full_text += page.get_text()
    doc.close()
    print(f"  ✓ Extracted {len(full_text)} characters from {len(doc)} pages")
except Exception as e:
    print(f"  ✗ Failed: {e}")
    sys.exit(1)

print("\n✓ All tests passed! PDF extraction is working.")
