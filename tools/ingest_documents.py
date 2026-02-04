"""Document ingestion script for Azure AI Search.

This script processes PDF documents and indexes them in Azure AI Search
for use with document grounding in the KYC demo.
"""

import argparse
import asyncio
import os
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.indexes import SearchIndexClient
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


def chunk_text(text: str, chunk_size: int = 1000, overlap: int = 200) -> list[str]:
    """Split text into overlapping chunks.

    Args:
        text: Text to split
        chunk_size: Maximum characters per chunk
        overlap: Number of overlapping characters between chunks

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


def extract_text_from_pdf(pdf_path: Path) -> str:
    """Extract text from a PDF file.

    Args:
        pdf_path: Path to the PDF file

    Returns:
        Extracted text content
    """
    try:
        import fitz  # PyMuPDF
    except ImportError:
        print("PyMuPDF not installed. Install with: pip install PyMuPDF")
        print("Using mock content for demo purposes...")
        return get_mock_content(pdf_path.name)

    text_parts = []
    with fitz.open(pdf_path) as doc:
        for page in doc:
            text_parts.append(page.get_text())

    return "\n".join(text_parts)


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

        # Extract text
        text = extract_text_from_pdf(pdf_path)

        # Chunk the text
        chunks = chunk_text(text)

        for i, chunk in enumerate(chunks):
            doc_id += 1
            documents.append({
                "id": str(doc_id),
                "content": chunk,
                "title": pdf_path.stem.replace("-", " ").replace("_", " ").title(),
                "source": pdf_path.name,
                "chunk_index": i,
                "page_number": 0,  # Would need PDF page tracking for accuracy
            })

    if documents:
        result = search_client.upload_documents(documents)
        print(f"Indexed {len(documents)} chunks from {len(list(data_dir.glob('*.pdf')))} documents")
        return len(documents)

    return 0


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
    args = parser.parse_args()

    settings = get_settings()

    if not settings.azure_search_configured:
        print("Azure AI Search is not configured.")
        print("Set AZURE_SEARCH_ENDPOINT and AZURE_SEARCH_API_KEY in .env")
        sys.exit(1)

    credential = AzureKeyCredential(settings.azure_search_api_key)

    # Create index if requested
    if args.create_index:
        index_client = SearchIndexClient(
            endpoint=settings.azure_search_endpoint,
            credential=credential,
        )
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
