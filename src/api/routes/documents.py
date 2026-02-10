"""Document upload and processing API endpoints."""

import logging
import shutil
from pathlib import Path
from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel

from src.api.state import get_app_state

logger = logging.getLogger(__name__)

router = APIRouter()

# Document storage directory
DOCUMENTS_DIR = Path(__file__).parent.parent.parent.parent / "data" / "customer-documents"


class ExtractedData(BaseModel):
    """Extracted data from a document."""
    first_name: str = ""
    last_name: str = ""
    date_of_birth: str = ""
    nationality: str = ""
    address: str = ""
    document_number: str = ""
    expiry_date: str = ""
    document_type: str = ""
    document_date: str = ""  # Date of the document (for proof of address)
    is_valid_timeframe: bool = True  # Whether document is within required timeframe
    validity_message: str = ""  # Message about document validity
    error: str | None = None


class DocumentUploadResponse(BaseModel):
    """Response from document upload."""
    success: bool
    file_path: str
    extracted_data: ExtractedData | None = None
    message: str = ""


class CustomerCreateRequest(BaseModel):
    """Request to create a new customer."""
    first_name: str
    last_name: str
    email: str
    phone: str = ""
    address: str = ""
    date_of_birth: str = ""
    nationality: str = ""


class CustomerCreateResponse(BaseModel):
    """Response from customer creation."""
    success: bool
    customer_id: str = ""
    account_id: str = ""
    account_number: str = ""
    message: str = ""


@router.post("/upload", response_model=DocumentUploadResponse)
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(default="auto"),
    customer_id: str = Form(default=""),
):
    """Upload a document and extract information using Document Intelligence.

    Args:
        file: The document file (PDF or image)
        doc_type: Type of document (passport, driving_license, utility_bill) or "auto" for auto-detection
        customer_id: Optional customer ID if document is for existing customer
    """
    state = get_app_state()

    # Validate file type
    allowed_types = ["application/pdf", "image/jpeg", "image/png", "image/tiff"]
    if file.content_type not in allowed_types:
        raise HTTPException(
            status_code=400,
            detail=f"File type {file.content_type} not allowed. Use PDF or images."
        )

    # Create storage directory
    if customer_id:
        doc_dir = DOCUMENTS_DIR / customer_id
    else:
        doc_dir = DOCUMENTS_DIR / "pending"
    doc_dir.mkdir(parents=True, exist_ok=True)

    # Save file
    file_ext = Path(file.filename or "document").suffix or ".pdf"
    file_path = doc_dir / f"document_{doc_type}{file_ext}"
    
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    # Extract data using Document Intelligence with auto-detection
    extracted_data = None
    if state.document_intelligence and state.document_intelligence.is_available:
        # Auto-detect: try ID document first, then address document
        logger.info(f"Extracting document with doc_type={doc_type}, file={file_path}")
        if doc_type == "auto":
            result = await state.document_intelligence.extract_auto_detect(file_path)
        elif doc_type in ["passport", "driving_license", "id_card"]:
            result = await state.document_intelligence.extract_id_document(file_path)
        else:
            result = await state.document_intelligence.extract_address_document(file_path)
        
        logger.info(f"Extraction result: {result}")
        extracted_data = ExtractedData(**result)
    else:
        logger.warning("Document Intelligence not available")
        # Return empty extraction if service not available
        extracted_data = ExtractedData(
            error="Document Intelligence not configured. Please enter information manually."
        )

    return DocumentUploadResponse(
        success=True,
        file_path=str(file_path.relative_to(DOCUMENTS_DIR.parent)),
        extracted_data=extracted_data,
        message="Document uploaded successfully"
    )


@router.post("/create-customer", response_model=CustomerCreateResponse)
async def create_customer_with_account(request: CustomerCreateRequest):
    """Create a new customer and checking account.

    This creates the customer record and a new checking account with pending_kyc status.
    """
    state = get_app_state()

    if not state.customer_repository:
        raise HTTPException(status_code=500, detail="Customer repository not available")

    # Check if email already exists
    existing = state.customer_repository.get_by_email(request.email)
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Customer with email {request.email} already exists"
        )

    # Create customer
    customer = state.customer_repository.create_customer({
        "first_name": request.first_name,
        "last_name": request.last_name,
        "email": request.email,
        "phone": request.phone,
        "address": request.address,
        "date_of_birth": request.date_of_birth,
        "nationality": request.nationality,
    })

    # Create checking account
    account = state.customer_repository.create_account(
        customer_id=customer["id"],
        account_type="current",
        initial_balance=0.0,
    )

    # Move pending documents to customer folder if any
    pending_dir = DOCUMENTS_DIR / "pending"
    if pending_dir.exists():
        customer_dir = DOCUMENTS_DIR / customer["id"]
        customer_dir.mkdir(parents=True, exist_ok=True)
        for doc_file in pending_dir.iterdir():
            if doc_file.is_file():
                # Add document record
                doc_type = doc_file.stem  # passport, driving_license, etc.
                new_path = customer_dir / doc_file.name
                shutil.move(str(doc_file), str(new_path))
                state.customer_repository.add_kyc_document(
                    customer_id=customer["id"],
                    doc_type=doc_type,
                    file_path=str(new_path.relative_to(DOCUMENTS_DIR.parent)),
                )

    return CustomerCreateResponse(
        success=True,
        customer_id=customer["id"],
        account_id=account["id"],
        account_number=account["account_number"],
        message=f"Customer {customer['first_name']} {customer['last_name']} created with checking account"
    )


@router.get("/pending-uploads")
async def get_pending_uploads() -> dict[str, Any]:
    """Get list of pending document uploads not yet assigned to a customer."""
    pending_dir = DOCUMENTS_DIR / "pending"
    if not pending_dir.exists():
        return {"files": []}

    files = [
        {"name": f.name, "type": f.stem, "size": f.stat().st_size}
        for f in pending_dir.iterdir()
        if f.is_file()
    ]
    return {"files": files}
