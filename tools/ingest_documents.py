"""Document ingestion script for Azure AI Search.

This script processes PDF documents and indexes them in Azure AI Search
for use with document grounding in the KYC demo.
"""

import argparse
import asyncio
import os
import re
import sys
from collections import Counter
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from azure.identity import ClientSecretCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
from dotenv import load_dotenv
from azure.search.documents.indexes.models import (
    SearchIndex,
    SimpleField,
    SearchableField,
    SearchFieldDataType,
)

from src.infrastructure.config import get_settings


def create_search_index(index_client: SearchIndexClient, index_name: str) -> None:
    """Create the search index if it doesn't exist.

    Args:
        index_client: Azure Search Index client
        index_name: Name of the index to create
    """
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchableField(name="title", type=SearchFieldDataType.String),
        SimpleField(name="source", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32),
        SimpleField(name="page_number", type=SearchFieldDataType.Int32),
    ]

    index = SearchIndex(name=index_name, fields=fields)

    try:
        index_client.create_or_update_index(index)
        print(f"Created/updated index: {index_name}")
    except Exception as e:
        print(f"Error creating index: {e}")
        raise


def chunk_text(text: str, chunk_size: int = 2000, overlap: int = 500) -> list[str]:
    """Split text into overlapping chunks.

    Args:
        text: Text to split
        chunk_size: Maximum characters per chunk (default 2000 for footnote-inlined content)
        overlap: Number of overlapping characters between chunks (default 500)

    Returns:
        List of text chunks
    """
    chunks = []
    start = 0
    text_length = len(text)

    while start < text_length:
        end = start + chunk_size

        # Try to break at a sentence or paragraph
        if end < text_length:
            # Look for a good break point
            for sep in ["\n\n", "\n", ". ", " "]:
                break_point = text.rfind(sep, start, end)
                if break_point > start:
                    end = break_point + len(sep)
                    break

        chunk = text[start:end].strip()
        if chunk:
            chunks.append(chunk)

        start = end - overlap

    return chunks


# Footnote marker pattern: (1), [1], †, ‡, §, *
FOOTNOTE_MARKER_PATTERN = re.compile(r'[\(\[]?(\d+)[\)\]]?|([†‡§\*])')


def detect_footnotes(page_dict: dict, page_height: float) -> dict[str, str]:
    """Detect footnotes from structured PDF page data.
    
    Uses font size comparison (footnotes typically <80% of body font size)
    and y-position (bottom 20% of page) to identify footnote content.
    
    Args:
        page_dict: Result from page.get_text("dict")
        page_height: Height of the page in points
        
    Returns:
        Dictionary mapping footnote markers to their text content
    """
    # Collect all font sizes to determine body text size
    font_sizes: list[float] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:  # Skip non-text blocks
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("text", "").strip():
                    font_sizes.append(span.get("size", 12))
    
    if not font_sizes:
        return {}
    
    # Body font size is the most common size
    body_font_size = Counter(font_sizes).most_common(1)[0][0]
    footnote_size_threshold = body_font_size * 0.8
    
    # Bottom 20% of page is footnote region
    footnote_y_threshold = page_height * 0.80
    
    # Collect potential footnote content from bottom of page
    footnote_texts: list[tuple[str, float]] = []  # (text, y_position)
    
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        
        block_y = block.get("bbox", [0, 0, 0, 0])[1]  # y0 position
        
        for line in block.get("lines", []):
            line_text_parts = []
            is_footnote_region = False
            
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                span_size = span.get("size", 12)
                span_y = span.get("origin", [0, 0])[1]
                
                # Check if in footnote region (bottom of page + smaller font)
                if span_y > footnote_y_threshold or span_size < footnote_size_threshold:
                    is_footnote_region = True
                
                line_text_parts.append(span_text)
            
            if is_footnote_region and line_text_parts:
                full_line = "".join(line_text_parts).strip()
                if full_line:
                    footnote_texts.append((full_line, block_y))
    
    # Parse footnote markers and their content
    footnotes: dict[str, str] = {}
    
    for text, _ in footnote_texts:
        # Match patterns like "(1) footnote text" or "† footnote text" or "* footnote text"
        match = re.match(r'^([\(\[]?\d+[\)\]]?|[†‡§\*])\s*(.+)$', text)
        if match:
            marker = match.group(1)
            content = match.group(2).strip()
            # Normalize marker: (1) -> (1), 1) -> (1), etc.
            if marker.isdigit():
                marker = f"({marker})"
            elif marker.endswith(')') and not marker.startswith('('):
                marker = f"({marker[:-1]})"
            footnotes[marker] = content
    
    return footnotes


def inline_footnotes(text: str, footnote_map: dict[str, str]) -> str:
    """Inline footnote content after first occurrence of each marker.
    
    Replaces markers like (1), †, * with [Note: footnote text] format.
    Only replaces the first occurrence of each marker (the reference),
    not the footnote definition itself.
    
    Args:
        text: Main text content with footnote markers
        footnote_map: Dictionary mapping markers to footnote text
        
    Returns:
        Text with footnotes inlined after their markers
    """
    if not footnote_map:
        return text
    
    inlined_markers: set[str] = set()
    
    def replace_marker(match: re.Match) -> str:
        full_match = match.group(0)
        
        # Normalize the matched marker
        normalized = full_match
        if full_match.isdigit():
            normalized = f"({full_match})"
        elif full_match.endswith(')') and not full_match.startswith('('):
            normalized = f"({full_match[:-1]})"
        elif full_match.startswith('[') and full_match.endswith(']'):
            # Convert [1] to (1) for lookup
            normalized = f"({full_match[1:-1]})"
        
        # Only inline first occurrence
        if normalized in footnote_map and normalized not in inlined_markers:
            inlined_markers.add(normalized)
            footnote_text = footnote_map[normalized]
            return f"{full_match} [Note: {footnote_text}]"
        
        return full_match
    
    # Pattern to match footnote markers in text
    # Matches: (1), [1], 1), †, ‡, §, *
    marker_pattern = re.compile(r'[\(\[]\d+[\)\]]|\d+\)|[†‡§\*]')
    
    return marker_pattern.sub(replace_marker, text)


def extract_main_text(page_dict: dict, page_height: float) -> str:
    """Extract main body text from structured page data, excluding footnote region.
    
    Args:
        page_dict: Result from page.get_text("dict")
        page_height: Height of the page in points
        
    Returns:
        Main text content (excluding footnotes at bottom)
    """
    # Collect font sizes to determine body text size
    font_sizes: list[float] = []
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                if span.get("text", "").strip():
                    font_sizes.append(span.get("size", 12))
    
    if not font_sizes:
        return ""
    
    body_font_size = Counter(font_sizes).most_common(1)[0][0]
    footnote_size_threshold = body_font_size * 0.8
    footnote_y_threshold = page_height * 0.80
    
    text_parts: list[str] = []
    
    for block in page_dict.get("blocks", []):
        if block.get("type") != 0:
            continue
        
        block_lines: list[str] = []
        
        for line in block.get("lines", []):
            line_parts: list[str] = []
            include_line = True
            
            for span in line.get("spans", []):
                span_text = span.get("text", "")
                span_size = span.get("size", 12)
                span_y = span.get("origin", [0, 0])[1]
                
                # Skip if this is clearly in footnote region with small font
                # But keep superscript markers that appear inline
                if span_y > footnote_y_threshold and span_size < footnote_size_threshold:
                    # Check if this looks like a footnote definition line
                    if re.match(r'^[\(\[]?\d+[\)\]]?\s|^[†‡§\*]\s', span_text.strip()):
                        include_line = False
                        break
                
                line_parts.append(span_text)
            
            if include_line and line_parts:
                block_lines.append("".join(line_parts))
        
        if block_lines:
            text_parts.append("\n".join(block_lines))
    
    return "\n\n".join(text_parts)


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF file with footnotes inlined.
    
    Uses structured PDF parsing to detect footnotes by font size and position,
    then inlines footnote content after the first occurrence of each marker.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Extracted text content with footnotes inlined
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF not installed. Install with: pip install PyMuPDF")
        print("Using mock content for demo purposes...")
        return get_mock_content(pdf_path.name)

    page_texts: list[str] = []
    
    with fitz.open(pdf_path) as doc:
        for page in doc:
            page_height = page.rect.height
            page_dict = page.get_text("dict")
            
            # Detect footnotes from this page
            footnotes = detect_footnotes(page_dict, page_height)
            
            # Extract main text (excluding footnote definitions)
            main_text = extract_main_text(page_dict, page_height)
            
            # Inline footnotes into main text
            if footnotes:
                main_text = inline_footnotes(main_text, footnotes)
                print(f"  - Page {page.number + 1}: Found {len(footnotes)} footnote(s)")
            
            if main_text.strip():
                page_texts.append(main_text)
    
    return "\n\n".join(page_texts)


def get_mock_content(filename: str) -> str:
    """Get mock content for demo when PDF extraction isn't available.

    Args:
        filename: Name of the file

    Returns:
        Mock content string
    """
    if "fees" in filename.lower() or "charges" in filename.lower():
        return """
        Guide to Fees and Charges for Personal Accounts
        
        Current Account Fees:
        - Monthly maintenance fee: €4.50 (waived if credit balance >€2,500)
        - ATM withdrawal (Zava Bank): Free
        - ATM withdrawal (other Irish banks): €0.35
        - ATM withdrawal (international): €2.50 + 1.75% foreign exchange fee
        - Overdraft arrangement fee: €25 per annum
        - Overdraft interest rate: 13.5% APR (variable)
        - Unpaid item fee: €10.16 per item
        
        Payment and Transfer Fees:
        - SEPA credit transfer (online): Free
        - SEPA credit transfer (branch): €5.00
        - SEPA direct debit: Free
        - Standing order: Free
        - International transfer (SWIFT): €25 + correspondent bank charges
        
        Debit Card Information:
        - Card type: Visa Debit
        - Contactless limit: €50 per transaction
        - Daily ATM withdrawal limit: €700
        - Daily purchase limit: €2,500
        - Card replacement (lost/stolen): €5.00
        """
    else:
        return """
        Information Leaflet for Zava Bank Personal Account
        
        Account Opening Requirements:
        To open a personal bank account, you'll need:
        1. Valid photo ID (Passport, Driving License, or National ID Card)
        2. Proof of address (utility bill, bank statement, or government letter dated within 3 months)
        3. PPS Number (for Irish residents)
        
        For non-residents, additional documentation may be required:
        - Proof of employment or student status in Ireland
        - Reference from existing bank
        
        KYC Verification Process:
        1. Submit required documents online or in branch
        2. Documents are reviewed within 3-5 business days
        3. Additional information may be requested
        4. Account activated upon successful verification
        
        Savings Account Features:
        - Regular Saver Account: Up to 3.00% AER (max €1,000/month)
        - Demand Deposit: 0.50% AER (instant access)
        - Fixed Term Deposit (1 year): 2.75% AER
        """


async def ingest_documents(data_dir: Path, search_client: SearchClient) -> int:
    """Ingest documents from the data directory.

    Args:
        data_dir: Directory containing documents to ingest
        search_client: Azure Search client

    Returns:
        Number of documents indexed
    """
    documents = []
    doc_id = 0

    for pdf_path in data_dir.glob("*.pdf"):
        print(f"Processing: {pdf_path.name}")
        
        doc_title = pdf_path.stem.replace("-", " ").replace("_", " ").title()

        # Extract text
        text = extract_text_from_pdf(pdf_path)

        # Chunk the text
        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks):
            doc_id += 1
            
            # For short chunks, add document context to improve searchability
            content = chunk
            if len(chunk) < 500:
                # Add document title and common search terms as context
                content = f"[From: {doc_title}]\n\n{chunk}"
                
                # Add synonyms/related terms for better search matching
                # This helps match user queries like "withdrawal" to document terms like "withdraw"
                lower_chunk = chunk.lower()
                if "withdraw" in lower_chunk or "atm" in lower_chunk:
                    content += "\n\n[Related: ATM withdrawal limit, cash withdrawal, maximum daily withdrawal, debit card limit]"
            
            documents.append({
                "id": str(doc_id),
                "content": content,
                "title": doc_title,
                "source": pdf_path.name,
                "chunk_index": i,
                "page_number": 0,  # Would need PDF page tracking for accuracy
            })
        
        # Extract key facts (amounts, limits) and index them separately for better search
        key_facts = extract_key_facts(text, doc_title, pdf_path.name)
        for fact in key_facts:
            doc_id += 1
            documents.append({
                "id": str(doc_id),
                **fact
            })

    if documents:
        result = search_client.upload_documents(documents)
        print(f"Indexed {len(documents)} chunks from {len(list(data_dir.glob('*.pdf')))} documents")
        return len(documents)

    return 0


def extract_key_facts(text: str, doc_title: str, source: str) -> list[dict]:
    """Extract key banking facts (limits, amounts) for separate indexing.
    
    This ensures important numerical facts like ATM limits are easily searchable
    even if they appear briefly in documents.
    
    Args:
        text: Full document text
        doc_title: Document title
        source: Source filename
        
    Returns:
        List of fact documents to index
    """
    facts = []
    
    # Pattern for ATM/withdrawal limits
    import re
    
    # Match patterns like "ATM withdraw domestic daily limits: 1750 EUR"
    limit_patterns = [
        (r'ATM\s+withdraw[al]?\s+(?:domestic\s+)?(?:daily\s+)?limits?[:\s]+(\d+(?:[.,]\d+)?)\s*(EUR|€)', 
         'ATM withdrawal limit', 
         'ATM daily withdrawal limit, cash withdrawal limit, maximum ATM withdrawal, debit card ATM limit, how much can I withdraw'),
        (r'(?:daily|maximum)\s+(?:cash\s+)?withdraw[al]?\s+limit[:\s]+(\d+(?:[.,]\d+)?)\s*(EUR|€)',
         'Cash withdrawal limit',
         'daily withdrawal limit, ATM limit, maximum withdrawal'),
        (r'overdraft\s+(?:arrangement\s+)?fee[:\s]+[€]?(\d+(?:[.,]\d+)?)',
         'Overdraft fee',
         'overdraft charge, overdraft arrangement cost'),
    ]
    
    for pattern, fact_type, search_terms in limit_patterns:
        matches = re.finditer(pattern, text, re.IGNORECASE)
        for match in matches:
            amount = match.group(1)
            currency = match.group(2) if match.lastindex >= 2 else 'EUR'
            
            # Create a rich, searchable fact entry
            fact_content = f"""[Key Banking Fact from {doc_title}]

{fact_type}: {amount} {currency}

Original text: "{match.group(0)}"

Related search terms: {search_terms}

This is an official limit from Zava Bank documentation."""
            
            facts.append({
                "content": fact_content,
                "title": f"{doc_title} - {fact_type}",
                "source": source,
                "chunk_index": 999,  # Mark as extracted fact
                "page_number": 0,
            })
    
    return facts


def main():
    """Main entry point for the ingestion script."""
    parser = argparse.ArgumentParser(description="Ingest documents into Azure AI Search")
    parser.add_argument(
        "--data-dir",
        type=Path,
        default=Path(__file__).parent.parent / "data" / "bank-documents",
        help="Directory containing documents to ingest",
    )
    parser.add_argument(
        "--create-index",
        action="store_true",
        help="Create or update the search index",
    )
    parser.add_argument(
        "--recreate-index",
        action="store_true",
        help="Delete and recreate the search index (purges all existing data)",
    )
    args = parser.parse_args()

    settings = get_settings()

    if not settings.azure_search_configured:
        print("Azure AI Search is not configured.")
        print("Set AZURE_SEARCH_ENDPOINT in .env")
        sys.exit(1)

    # Load environment variables and use Service Principal credentials
    load_dotenv()
    
    client_id = os.environ.get("AZURE_CLIENT_ID")
    client_secret = os.environ.get("AZURE_CLIENT_SECRET")
    tenant_id = os.environ.get("AZURE_TENANT_ID")
    
    if not all([client_id, client_secret, tenant_id]):
        print("Service Principal credentials not configured.")
        print("Set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID in .env")
        sys.exit(1)
    
    credential = ClientSecretCredential(
        tenant_id=tenant_id,
        client_id=client_id,
        client_secret=client_secret,
    )
    print(f"Using Azure Search endpoint: {settings.azure_search_endpoint}")
    print(f"Index name: {settings.azure_search_index_name}")

    # Handle index operations
    if args.recreate_index or args.create_index:
        index_client = SearchIndexClient(
            endpoint=settings.azure_search_endpoint,
            credential=credential,
        )
        
        # Delete existing index if recreating
        if args.recreate_index:
            try:
                index_client.delete_index(settings.azure_search_index_name)
                print(f"Deleted existing index: {settings.azure_search_index_name}")
            except Exception as e:
                print(f"Index deletion skipped (may not exist): {e}")
        
        create_search_index(index_client, settings.azure_search_index_name)

    # Create search client
    search_client = SearchClient(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.azure_search_index_name,
        credential=credential,
    )

    # Run ingestion
    count = asyncio.run(ingest_documents(args.data_dir, search_client))
    print(f"Ingestion complete. Total chunks indexed: {count}")


if __name__ == "__main__":
    main()
