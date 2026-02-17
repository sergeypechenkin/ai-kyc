"""MAF HTTP Server Entry Point.

This module provides the HTTP server wrapper for the MAF-based KYC workflow.
Supports both standalone HTTP server mode and integration with FastAPI.
"""

import asyncio
import os
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import AsyncIterator
from contextlib import asynccontextmanager

from dotenv import load_dotenv

# Load environment variables first
load_dotenv(override=True)

# Configure Azure Monitor for OpenTelemetry (Application Insights)
app_insights_conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if app_insights_conn_str:
    try:
        from azure.monitor.opentelemetry import configure_azure_monitor
        configure_azure_monitor(
            connection_string=app_insights_conn_str,
            enable_live_metrics=True,
        )
        print("[OK] Application Insights configured")
        
        # Enable OpenAI instrumentation for gen_ai metrics
        try:
            from opentelemetry.instrumentation.openai import OpenAIInstrumentor
            OpenAIInstrumentor().instrument()
            print("[OK] OpenAI instrumentation enabled")
        except ImportError:
            print("[INFO] opentelemetry-instrumentation-openai not installed, LLM metrics will be limited")
        except Exception as e:
            print(f"[WARN] Failed to instrument OpenAI: {e}")
            
    except ImportError:
        print("[WARN] azure-monitor-opentelemetry not installed, skipping App Insights")
    except Exception as e:
        print(f"[WARN] Failed to configure App Insights: {e}")

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, File, Form, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from azure.core.exceptions import HttpResponseError

# Fun message for content filter violations
CONTENT_FILTER_MESSAGE = """Nice try! That reminds me of a story...

A guy walked into a bank and tried to convince the teller he was actually the bank's CEO using a fake ID. The teller smiled, pressed a button, and said "Funny, the *real* CEO is standing right behind you." Turns out it was Bring Your Boss to Work Day. He's now the proud owner of a 5-year membership at the state correctional facility. 🏦⛓️

Anyway, how can I *actually* help you today?"""

def _is_content_filter_error(e: Exception) -> bool:
    """Check if an exception is a content filter violation."""
    error_str = str(e).lower()
    return (
        "content_filter" in error_str or 
        "content management policy" in error_str or
        "responsibleaipolicyviolation" in error_str
    )
# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from src.maf.workflow import KycWorkflow, ChatRole, get_workflow
from src.infrastructure.mock_data import CustomerRepository
from src.infrastructure.document_search import DocumentSearchService
from src.infrastructure.document_validation import DocumentValidationService
from src.maf.activity import set_activity_callback


class ChatRequest(BaseModel):
    """Chat request model."""
    message: str
    role: str = "customer"  # "customer" or "employee"
    context: dict | None = None


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    agent: str
    role: str


class ConfigRequest(BaseModel):
    """Configuration request model."""
    grounding_enabled: bool


# Global state
_workflow: KycWorkflow | None = None
_customer_repo: CustomerRepository | None = None
_search_service: DocumentSearchService | None = None
_document_validation: DocumentValidationService | None = None

# Session document tracking: session_id -> list of document info
_session_documents: dict[str, list[dict]] = {}
# Customer to session mapping: customer_id -> session_id
_customer_session_map: dict[str, str] = {}


async def init_services():
    """Initialize all services and workflow."""
    global _workflow, _customer_repo, _search_service, _document_validation
    
    # Initialize repositories
    _customer_repo = CustomerRepository()
    
    # Initialize document validation service with customer repo for risk checks
    _document_validation = DocumentValidationService(customer_repo=_customer_repo)
    
    # Initialize search service
    search_endpoint = os.getenv("AZURE_SEARCH_ENDPOINT")
    
    if search_endpoint:
        _search_service = DocumentSearchService()
    
    # Initialize workflow
    _workflow = await get_workflow()
    grounding_enabled = os.getenv("ENABLE_DOCUMENT_GROUNDING", "false").lower() == "true"
    
    await _workflow.initialize(
        customer_repository=_customer_repo,
        search_service=_search_service,
        grounding_enabled=grounding_enabled,
    )
    
    # Set up activity callback for tools to broadcast events
    async def activity_callback(event_type: str, agent_name: str, data: dict | None):
        await manager.broadcast_activity(event_type, agent_name, data or {})
    
    set_activity_callback(activity_callback)
    
    print("[OK] MAF Workflow initialized")


async def shutdown_services():
    """Cleanup services on shutdown."""
    global _workflow, _customer_repo, _search_service
    _workflow = None
    _customer_repo = None
    _search_service = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """FastAPI lifespan handler."""
    await init_services()
    yield
    await shutdown_services()


# Create FastAPI app
app = FastAPI(
    title="KYC MAF API",
    description="KYC Demo Application powered by Microsoft Agent Framework",
    version="2.0.0",
    lifespan=lifespan,
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "framework": "Microsoft Agent Framework",
        "version": "2.0.0",
    }


@app.post("/api/chat", response_model=ChatResponse)
async def chat(request: ChatRequest) -> ChatResponse:
    """Process a chat message.
    
    Args:
        request: Chat request with message and role
        
    Returns:
        Chat response with agent reply
    """
    if _workflow is None:
        raise HTTPException(status_code=503, detail="Workflow not initialized")
    
    role = ChatRole.CUSTOMER if request.role == "customer" else ChatRole.EMPLOYEE
    agent_name = "customer-agent" if role == ChatRole.CUSTOMER else "bank-employee-agent"
    
    try:
        response = await _workflow.process_message(
            message=request.message,
            role=role,
            context=request.context,
        )
    except HttpResponseError as e:
        # Check for content filter violation (HTTP 400)
        if _is_content_filter_error(e):
            print(f"[WARN] Content filter triggered (HttpResponseError): {e}")
            response = CONTENT_FILTER_MESSAGE
        else:
            raise
    except Exception as e:
        # Agent framework may wrap content filter errors
        if _is_content_filter_error(e):
            print(f"[WARN] Content filter triggered (Exception): {e}")
            response = CONTENT_FILTER_MESSAGE
        else:
            raise
    
    return ChatResponse(
        response=response,
        agent=agent_name,
        role=request.role,
    )


@app.post("/api/config")
async def update_config(request: ConfigRequest):
    """Update workflow configuration.
    
    Args:
        request: Configuration request
        
    Returns:
        Updated configuration
    """
    if _workflow is None:
        raise HTTPException(status_code=503, detail="Workflow not initialized")
    
    _workflow.set_grounding_enabled(request.grounding_enabled)
    
    return {
        "grounding_enabled": request.grounding_enabled,
        "status": "updated",
    }


@app.get("/api/config")
async def get_config():
    """Get current configuration."""
    grounding_enabled = os.getenv("ENABLE_DOCUMENT_GROUNDING", "false").lower() == "true"
    return {
        "grounding_enabled": grounding_enabled,
        "framework": "Microsoft Agent Framework",
    }


@app.get("/api/config/grounding")
async def get_grounding_config():
    """Get document grounding configuration."""
    from src.maf.tools.document_search import _grounding_enabled
    return {"enabled": _grounding_enabled}


@app.put("/api/config/grounding")
async def set_grounding_config(config: dict):
    """Enable or disable document grounding."""
    if _workflow is None:
        raise HTTPException(status_code=503, detail="Workflow not initialized")
    
    enabled = config.get("enabled", False)
    _workflow.set_grounding_enabled(enabled)
    print(f"[DEBUG] Grounding set to: {enabled}")
    return {"enabled": enabled}


# Document upload configuration
DOCUMENTS_DIR = Path(__file__).parent.parent.parent / "data" / "customer-documents"


class RiskAssessmentResponse(BaseModel):
    """Risk assessment for a customer based on ID document."""
    risk_score: int = 0
    risk_tier: str = "low"  # low, medium, high
    is_pep: bool = False
    required_documents: list[str] = []
    proof_of_funds_months: int = 0  # 0 = not required, 6 or 12
    approval_workflow: str = "auto_approve"  # auto_approve, employee_review, compliance_escalation
    alerts: list[str] = []  # Risk warnings/alerts


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
    document_date: str = ""
    is_valid_timeframe: bool = True
    validity_message: str = ""
    validation_errors: list[str] = []
    validation_warnings: list[str] = []
    validation_messages: list[str] = []  # Success messages (e.g., "Name matches", "Date valid")
    mismatch_with_primary: bool = False  # True if secondary doc doesn't match primary ID
    risk_assessment: RiskAssessmentResponse | None = None  # Risk assessment for primary docs
    error: str | None = None


@app.post("/api/documents/upload")
async def upload_document(
    file: UploadFile = File(...),
    doc_type: str = Form(default="auto"),
    customer_id: str = Form(default=""),
    session_id: str = Form(default="default"),
):
    """Upload a document and extract information."""
    print(f"[INFO] Upload request: file={file.filename}, size={file.size if hasattr(file, 'size') else 'unknown'}, type={file.content_type}, doc_type={doc_type}, session={session_id}")
    
    # Validate file type
    allowed_types = ["application/pdf", "image/jpeg", "image/png", "image/tiff"]
    if file.content_type not in allowed_types:
        print(f"[ERROR] Invalid file type: {file.content_type}")
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

    # Save file with unique name (preserve original filename)
    file_ext = Path(file.filename or "document").suffix or ".pdf"
    safe_filename = file.filename or f"document_{doc_type}{file_ext}"
    # Generate unique path to avoid overwrites
    import uuid
    unique_id = str(uuid.uuid4())[:8]
    # Create a safe version of doc_type for filename (replace spaces, limit length)
    safe_doc_type = doc_type.replace(" ", "_").replace("/", "-")[:30] if doc_type else "document"
    file_path = doc_dir / f"{safe_doc_type}_{unique_id}_{safe_filename}"
    
    print(f"[INFO] Saving file to: {file_path}")
    try:
        with open(file_path, "wb") as f:
            shutil.copyfileobj(file.file, f)
        print(f"[INFO] File saved successfully: {file_path.stat().st_size} bytes")
    except Exception as e:
        print(f"[ERROR] Failed to save file: {type(e).__name__}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to save file: {str(e)}")

    # Try to extract data using Document Intelligence
    print(f"[INFO] Starting document extraction for: {file_path}")
    extracted_data = None
    result = None
    try:
        from src.infrastructure.document_intelligence import DocumentIntelligenceService
        doc_intel = DocumentIntelligenceService()
        if doc_intel.is_available:
            if doc_type == "auto":
                result = await doc_intel.extract_auto_detect(file_path)
            elif doc_type in ["passport", "driving_license", "id_card"]:
                result = await doc_intel.extract_id_document(file_path)
            else:
                result = await doc_intel.extract_address_document(file_path)
            extracted_data = ExtractedData(**result)
            # Fallback: if extraction didn't detect doc type, use the requested doc_type
            if not extracted_data.document_type and doc_type not in ["auto"]:
                extracted_data.document_type = doc_type
                if result:
                    result["document_type"] = doc_type
            print(f"[INFO] Extraction successful: {extracted_data.document_type}")
    except Exception as e:
        print(f"[WARN] Document Intelligence extraction failed: {e}")
        import traceback
        print(f"[DEBUG] Traceback: {traceback.format_exc()}")
    
    if extracted_data is None:
        extracted_data = ExtractedData(
            error="Document Intelligence not configured. Please enter information manually."
        )
    
    # Perform cross-document validation
    if _document_validation and result:
        print(f"[INFO] Validating document in session={session_id}, doc_type={extracted_data.document_type}")
        print(f"[INFO] Existing session docs: {[d.doc_type for d in _document_validation.get_session_documents(session_id)]}")
        validation_result = _document_validation.validate_document(
            session_id=session_id,
            extracted_data=result
        )
        extracted_data.validation_errors = validation_result.errors
        extracted_data.validation_warnings = validation_result.warnings
        extracted_data.validation_messages = validation_result.validation_messages
        extracted_data.mismatch_with_primary = validation_result.mismatch_with_primary
        print(f"[INFO] Validation result: errors={validation_result.errors}, warnings={validation_result.warnings}, messages={validation_result.validation_messages}")
        
        # Include risk assessment if available (for primary documents)
        if validation_result.risk_assessment:
            ra = validation_result.risk_assessment
            extracted_data.risk_assessment = RiskAssessmentResponse(
                risk_score=ra.risk_score,
                risk_tier=ra.risk_tier,
                is_pep=ra.is_pep,
                required_documents=ra.required_documents,
                proof_of_funds_months=ra.proof_of_funds_months,
                approval_workflow=ra.approval_workflow,
                alerts=ra.alerts,
            )
            print(f"[INFO] Risk assessment: score={ra.risk_score}, tier={ra.risk_tier}, workflow={ra.approval_workflow}")
        
        # Mark as invalid if there are validation errors
        if not validation_result.is_valid:
            extracted_data.is_valid_timeframe = False
    
    # Track document upload in session
    import uuid
    doc_id = str(uuid.uuid4())[:12]  # Unique ID for each document
    
    # Use the doc_type from the request if it's a specific type (not "auto" or standard types)
    # This preserves the original requested document type like "Bank statements for last 12 months"
    display_type = doc_type
    if doc_type in ["auto", "passport", "driving_license", "id_card", "proof_of_address", "supporting_document"]:
        display_type = extracted_data.document_type or doc_type or "Unknown"
    
    doc_info = {
        "id": doc_id,
        "type": display_type,
        "name": file.filename or file_path.name,
        "path": str(file_path.relative_to(DOCUMENTS_DIR.parent)),
        "uploaded_at": datetime.now().isoformat(),
        "verified": False,
    }
    
    if session_id not in _session_documents:
        _session_documents[session_id] = []
    _session_documents[session_id].append(doc_info)
    print(f"[INFO] Tracked document in session {session_id}: {doc_info['name']} ({doc_info['type']})")
    
    # If we have a customer name from extraction, look up and map customer_id
    full_name = f"{extracted_data.first_name} {extracted_data.last_name}".strip()
    if full_name and _customer_repo:
        # Try to match customer by name using search
        matching_customers = _customer_repo.search_by_name(full_name)
        if matching_customers:
            customer_id_found = matching_customers[0].get("customer_id")
            if customer_id_found:
                _customer_session_map[customer_id_found] = session_id
                print(f"[INFO] Mapped customer {customer_id_found} to session {session_id}")

    print(f"[INFO] Upload complete: {file.filename} - {extracted_data.document_type if extracted_data else 'no extraction'}")
    return {
        "success": True,
        "file_path": str(file_path.relative_to(DOCUMENTS_DIR.parent)),
        "extracted_data": extracted_data.model_dump(),
        "message": "Document uploaded successfully"
    }


@app.post("/api/chat/clear")
async def clear_chat(role: str | None = None):
    """Clear chat history.
    
    Args:
        role: Optional role to clear ("customer" or "employee"), or all if None
        
    Returns:
        Confirmation
    """
    if _workflow is None:
        raise HTTPException(status_code=503, detail="Workflow not initialized")
    
    chat_role = None
    if role == "customer":
        chat_role = ChatRole.CUSTOMER
    elif role == "employee":
        chat_role = ChatRole.EMPLOYEE
    
    _workflow.clear_history(chat_role)
    
    return {"status": "cleared", "role": role or "all"}


@app.post("/api/documents/clear-session")
async def clear_document_session(session_id: str):
    """Clear all documents for a session (e.g., when user wants to upload a new primary document).
    
    Args:
        session_id: Session identifier
        
    Returns:
        Confirmation
    """
    # Clear session document tracking
    if session_id in _session_documents:
        del _session_documents[session_id]
    
    # Remove any customer mappings for this session
    customers_to_remove = [cid for cid, sid in _customer_session_map.items() if sid == session_id]
    for cid in customers_to_remove:
        del _customer_session_map[cid]
    
    if _document_validation:
        _document_validation.clear_session(session_id)
        return {"status": "cleared", "session_id": session_id}
    return {"status": "no_validation_service", "session_id": session_id}


class ComplianceSubmission(BaseModel):
    """Request model for submitting a case for compliance review."""
    session_id: str
    customer_name: str
    first_name: str = ""
    last_name: str = ""
    date_of_birth: str = ""
    address: str = ""
    document_number: str = ""
    risk_tier: str = "high"
    risk_score: int = 0
    nationality: str = ""
    alerts: list[str] = []


@app.post("/api/compliance/submit")
async def submit_for_compliance_review(submission: ComplianceSubmission):
    """Submit a customer's documents for compliance review.
    
    Args:
        submission: Details of the submission
        
    Returns:
        Confirmation with review ID
    """
    from src.maf.tools.kyc_verification import add_pending_submission
    
    # Generate a temporary customer ID if not mapped
    customer_id = None
    for cid, sid in _customer_session_map.items():
        if sid == submission.session_id:
            customer_id = cid
            break
    
    if not customer_id:
        # Generate a new ID for this submission
        import random
        customer_id = f"NEW-{random.randint(1000, 9999)}"
        _customer_session_map[customer_id] = submission.session_id
    
    # Add to pending submissions with full customer details
    pending_entry = {
        "customer_id": customer_id,
        "customer_name": submission.customer_name,
        "first_name": submission.first_name,
        "last_name": submission.last_name,
        "date_of_birth": submission.date_of_birth,
        "nationality": submission.nationality,
        "address": submission.address,
        "document_number": submission.document_number,
        "status": "pending_compliance_review",
        "submitted_date": datetime.now().isoformat(),
        "risk_tier": submission.risk_tier,
        "risk_score": submission.risk_score,
        "alerts": submission.alerts,
        "session_id": submission.session_id,
    }
    
    add_pending_submission(pending_entry)
    
    print(f"[INFO] Submitted for compliance review: {customer_id} ({submission.customer_name}) - Risk: {submission.risk_tier}")
    
    return {
        "status": "submitted",
        "customer_id": customer_id,
        "message": f"Case submitted for compliance review. Risk tier: {submission.risk_tier.upper()}"
    }


@app.get("/api/compliance/pending")
async def get_compliance_pending():
    """Get list of all pending compliance reviews.
    
    Returns list of pending reviews with customer info, risk tier, and status.
    Used by the bank employee UI to show a clickable list.
    """
    from src.maf.tools.kyc_verification import get_pending_submissions
    
    pending = []
    
    # Get all pending submissions
    for submission in get_pending_submissions():
        pending.append({
            "customer_id": submission.get("customer_id", ""),
            "customer_name": submission.get("customer_name", ""),
            "status": submission.get("status", ""),
            "submitted_date": submission.get("submitted_date", ""),
            "risk_tier": submission.get("risk_tier", ""),
            "risk_score": submission.get("risk_score", 0),
        })
    
    # Also add CSV-based pending reviews if customer_repo is available
    if _customer_repo:
        csv_pending = _customer_repo.get_pending_reviews()
        existing_ids = {p["customer_id"] for p in pending}
        for review in csv_pending:
            if review.get("customer_id") not in existing_ids:
                pending.append({
                    "customer_id": review.get("customer_id", ""),
                    "customer_name": review.get("customer_name", ""),
                    "status": review.get("status", "pending"),
                    "submitted_date": review.get("submitted_date", ""),
                    "risk_tier": review.get("risk_tier", ""),
                    "risk_score": review.get("risk_score", 0),
                })
    
    return {"reviews": pending}


@app.get("/api/customers/{customer_id}")
async def get_customer(customer_id: str):
    """Get customer information.
    
    Args:
        customer_id: Customer ID
        
    Returns:
        Customer information
    """
    from src.maf.tools.kyc_verification import get_pending_submissions
    
    # Check pending submissions (both NEW-xxxx and inter-agent submissions)
    for submission in get_pending_submissions():
        if submission.get("customer_id") == customer_id:
            return {
                "customer_id": customer_id,
                "first_name": submission.get("first_name", ""),
                "last_name": submission.get("last_name", ""),
                "date_of_birth": submission.get("date_of_birth", ""),
                "nationality": submission.get("nationality", ""),
                "address": submission.get("address", ""),
                "email": "",
                "document_number": submission.get("document_number", ""),
            }
    
    if _customer_repo is None:
        raise HTTPException(status_code=503, detail="Customer repository not initialized")
    
    customer = _customer_repo.get_by_id(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    
    return {
        "customer_id": customer.get("customer_id", customer_id),
        "first_name": customer.get("first_name", ""),
        "last_name": customer.get("last_name", ""),
        "date_of_birth": customer.get("date_of_birth", ""),
        "nationality": customer.get("nationality", ""),
        "address": customer.get("address", ""),
        "email": customer.get("email", ""),
    }


@app.get("/api/customers/{customer_id}/documents")
async def get_customer_documents(customer_id: str):
    """Get list of documents uploaded for a customer.
    
    Args:
        customer_id: Customer ID
        
    Returns:
        List of documents with paths
    """
    documents = []
    
    # First, check session-tracked documents via customer_session_map
    session_id = _customer_session_map.get(customer_id)
    if session_id and session_id in _session_documents:
        documents = _session_documents[session_id]
        print(f"[INFO] Found {len(documents)} documents for customer {customer_id} in session {session_id}")
        return {"documents": documents}
    
    # Also check pending submissions for upload_session_id
    from src.maf.tools.kyc_verification import get_pending_submissions
    for submission in get_pending_submissions():
        if submission.get("customer_id") == customer_id:
            upload_sid = submission.get("upload_session_id") or submission.get("session_id", "")
            if upload_sid and upload_sid in _session_documents:
                documents = _session_documents[upload_sid]
                print(f"[INFO] Found {len(documents)} documents for customer {customer_id} via submission session {upload_sid}")
                return {"documents": documents}
    
    # Fallback: check customer-specific folder
    customer_docs_dir = DOCUMENTS_DIR / customer_id
    if customer_docs_dir.exists():
        for file_path in customer_docs_dir.iterdir():
            if file_path.is_file():
                # Determine document type from filename
                filename = file_path.name.lower()
                doc_type = "Unknown"
                if "passport" in filename:
                    doc_type = "Passport"
                elif "license" in filename or "driving" in filename:
                    doc_type = "Driving License"
                elif "bill" in filename or "utility" in filename or "proof" in filename:
                    doc_type = "Proof of Address"
                elif "bank" in filename or "statement" in filename:
                    doc_type = "Bank Statement"
                elif "income" in filename or "employment" in filename or "payslip" in filename:
                    doc_type = "Proof of Income"
                elif "wealth" in filename or "source" in filename:
                    doc_type = "Source of Wealth"
                else:
                    doc_type = "Supporting Document"
                
                documents.append({
                    "id": file_path.stem,
                    "type": doc_type,
                    "name": file_path.name,
                    "path": f"customer-documents/{customer_id}/{file_path.name}",
                    "uploaded_at": datetime.fromtimestamp(file_path.stat().st_mtime).isoformat(),
                    "verified": False,
                })
    
    return {"documents": documents}


@app.get("/api/customers/{customer_id}/risk-assessment")
async def get_customer_risk_assessment(customer_id: str):
    """Get risk assessment for a customer.
    
    Args:
        customer_id: Customer ID
        
    Returns:
        Risk assessment details
    """
    from src.maf.tools.kyc_verification import get_pending_submissions
    
    # Check pending submissions (both NEW-xxxx and inter-agent)
    for submission in get_pending_submissions():
        if submission.get("customer_id") == customer_id:
            risk_tier = submission.get("risk_tier", "medium")
            # Return the stored risk assessment
            return {
                "risk_score": submission.get("risk_score", 0),
                "risk_tier": risk_tier,
                "is_pep": False,  # PEP check already done at upload time
                "pep_details": None,
                "country_risk_reason": submission.get("details", ""),
                "required_documents": [],
                "approval_workflow": "compliance_escalation" if risk_tier == "high" else "employee_review",
                "alerts": submission.get("alerts", []),
            }
    
    if _customer_repo is None:
        raise HTTPException(status_code=503, detail="Customer repository not initialized")
    
    customer = _customer_repo.get_by_id(customer_id)
    if not customer:
        raise HTTPException(status_code=404, detail=f"Customer {customer_id} not found")
    
    nationality = customer.get("nationality", "")
    full_name = f"{customer.get('first_name', '')} {customer.get('last_name', '')}".strip()
    
    # Get country risk
    country_risk = _customer_repo.get_country_risk(nationality) if nationality else None
    
    # Check PEP
    pep_matches = _customer_repo.check_pep(full_name) if full_name else []
    
    # Calculate risk score
    risk_score = 0
    alerts = []
    pep_details = None
    country_risk_reason = None
    
    if country_risk:
        risk_score = max(risk_score, country_risk.get("risk_score", 0))
        country_risk_reason = country_risk.get("reason", "")
        if country_risk.get("risk_level", "").lower() in ("high", "critical"):
            alerts.append(f"⚠️ HIGH RISK COUNTRY: {nationality} - {country_risk_reason}")
        elif country_risk.get("risk_level", "").lower() == "medium":
            alerts.append(f"⚡ MEDIUM RISK COUNTRY: {nationality} - {country_risk_reason}")
    
    if pep_matches:
        risk_score = min(100, risk_score + 40)
        pep_details = pep_matches[0].get("position", "PEP Match")
        for match in pep_matches:
            alerts.append(f"🔴 PEP MATCH: {match.get('name', 'Unknown')} - {match.get('position', '')} ({match.get('country', '')})")
    
    # Determine tier and requirements
    if risk_score <= 30:
        risk_tier = "low"
        required_documents = []
        approval_workflow = "auto_approve"
    elif risk_score <= 70:
        risk_tier = "medium"
        required_documents = ["Bank statements for last 6 months", "Proof of income/employment"]
        approval_workflow = "employee_review"
    else:
        risk_tier = "high"
        required_documents = ["Bank statements for last 12 months", "Proof of income/employment", "Source of wealth declaration"]
        approval_workflow = "compliance_escalation"
        alerts.append("⛔ COMPLIANCE ESCALATION REQUIRED - High risk score")
    
    return {
        "risk_score": risk_score,
        "risk_tier": risk_tier,
        "is_pep": bool(pep_matches),
        "pep_details": pep_details,
        "country_risk_reason": country_risk_reason,
        "required_documents": required_documents,
        "approval_workflow": approval_workflow,
        "alerts": alerts,
    }


@app.get("/api/documents/view/{path:path}")
async def view_document(path: str):
    """Serve a document file for viewing.
    
    Args:
        path: Document path relative to data folder
        
    Returns:
        Document file
    """
    from fastapi.responses import FileResponse
    
    # Build full path - path should be like "customer-documents/C015/passport.pdf"
    base_path = Path(__file__).parent.parent.parent / "data"
    file_path = base_path / path
    
    # Security check - ensure path is within data directory
    try:
        file_path.resolve().relative_to(base_path.resolve())
    except ValueError:
        raise HTTPException(status_code=403, detail="Access denied")
    
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Determine content type
    suffix = file_path.suffix.lower()
    content_type = {
        ".pdf": "application/pdf",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".tiff": "image/tiff",
    }.get(suffix, "application/octet-stream")
    
    return FileResponse(file_path, media_type=content_type)


# WebSocket connection manager
class ConnectionManager:
    """Manages WebSocket connections."""
    
    def __init__(self):
        self.active_connections: dict[str, list[WebSocket]] = {
            "customer": [],
            "employee": [],
            "activity": [],
        }
    
    async def connect(self, websocket: WebSocket, channel: str):
        """Accept and track connection."""
        await websocket.accept()
        if channel in self.active_connections:
            self.active_connections[channel].append(websocket)
    
    def disconnect(self, websocket: WebSocket, channel: str):
        """Remove connection."""
        if channel in self.active_connections:
            if websocket in self.active_connections[channel]:
                self.active_connections[channel].remove(websocket)
    
    async def broadcast(self, message: dict, channel: str):
        """Broadcast message to channel."""
        if channel in self.active_connections:
            for connection in self.active_connections[channel]:
                try:
                    await connection.send_json(message)
                except Exception:
                    pass
    
    async def broadcast_activity(self, event_type: str, agent_name: str = "", data: dict = None):
        """Broadcast an activity event to all activity channel subscribers."""
        import datetime
        event = {
            "type": "activity",
            "data": {
                "id": str(datetime.datetime.now().timestamp()),
                "type": event_type,
                "agent_name": agent_name,
                "timestamp": datetime.datetime.now().isoformat(),
                "duration_ms": (data or {}).pop("durationMs", None),
                "data": data or {},
            }
        }
        await self.broadcast(event, "activity")


manager = ConnectionManager()


@app.websocket("/ws/{channel}")
async def websocket_endpoint(websocket: WebSocket, channel: str):
    """WebSocket endpoint for real-time chat.
    
    Args:
        websocket: WebSocket connection
        channel: Channel name ("customer" or "employee")
    """
    if channel not in ["customer", "employee", "activity"]:
        await websocket.close(code=4000, reason="Invalid channel")
        return
    
    # Activity channel is listen-only
    if channel == "activity":
        await manager.connect(websocket, channel)
        try:
            # Keep connection alive, activity events sent via broadcast_activity()
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            manager.disconnect(websocket, channel)
        return
    
    await manager.connect(websocket, channel)
    
    try:
        while True:
            data = await websocket.receive_json()
            print(f"[DEBUG] Received on {channel}: {data}")
            
            if _workflow is None:
                await websocket.send_json({
                    "type": "error",
                    "error": "Workflow not initialized",
                })
                continue
            
            # Handle document_event separately
            msg_type = data.get("type")
            if msg_type == "document_event":
                payload = data.get("payload", {})
                if payload.get("confirmed"):
                    message = "Verified document upload event received."
                    context = {
                        "document_event": payload,
                        "source": "upload",
                    }
                    print(f"[DEBUG] Document event: {payload.get('docType')}")
                else:
                    continue  # Skip unconfirmed document events
            else:
                # Support both 'message' and 'content' from frontend
                message = data.get("message") or data.get("content", "")
                context = data.get("context", {})
            
            print(f"[DEBUG] Processing message: {message}")
            
            role = ChatRole.CUSTOMER if channel == "customer" else ChatRole.EMPLOYEE
            agent_name = "customer-agent" if role == ChatRole.CUSTOMER else "bank-employee-agent"
            
            # Broadcast activity: message received
            await manager.broadcast_activity(
                "user_message",
                agent_name,
                {"message": message[:100] + "..." if len(message) > 100 else message}
            )
            
            # Send typing indicator
            await websocket.send_json({
                "type": "typing",
                "agent": agent_name,
            })
            
            # Broadcast activity: agent thinking
            import time
            start_time = time.time()
            await manager.broadcast_activity("agent_thinking", agent_name)
            
            try:
                # Stream response
                full_response = ""
                print(f"[DEBUG] Starting stream for: {message}")
                async for chunk in _workflow.process_message_stream(
                    message=message,
                    role=role,
                    context=context,
                ):
                    full_response += chunk
                    print(f"[DEBUG] Chunk: {chunk}")
                    await websocket.send_json({
                        "type": "chunk",
                        "content": chunk,
                        "agent": agent_name,
                    })
                
                duration_ms = (time.time() - start_time) * 1000
                print(f"[DEBUG] Full response: {full_response}")
                
                # Broadcast activity: agent response
                await manager.broadcast_activity(
                    "agent_response",
                    agent_name,
                    {
                        "message": full_response[:100] + "..." if len(full_response) > 100 else full_response,
                        "durationMs": duration_ms,
                    }
                )
                
                # Send complete message
                await websocket.send_json({
                    "type": "message",
                    "content": full_response,
                    "agent": agent_name,
                    "role": channel,
                })
                
            except HttpResponseError as e:
                # Check for content filter violation (HTTP 400)
                if _is_content_filter_error(e):
                    print(f"[WARN] Content filter triggered (HttpResponseError): {e}")
                    await websocket.send_json({
                        "type": "message",
                        "content": CONTENT_FILTER_MESSAGE,
                        "agent": agent_name,
                        "role": channel,
                    })
                else:
                    raise
            except Exception as e:
                # Check for content filter from agent framework
                if _is_content_filter_error(e):
                    print(f"[WARN] Content filter triggered (Exception): {e}")
                    await websocket.send_json({
                        "type": "message",
                        "content": CONTENT_FILTER_MESSAGE,
                        "agent": agent_name,
                        "role": channel,
                    })
                else:
                    import traceback
                    print(f"[ERROR] {e}")
                    traceback.print_exc()
                    
                    # Broadcast activity: error
                    await manager.broadcast_activity(
                        "error",
                        agent_name,
                        {"error": str(e)}
                    )
                    
                    await websocket.send_json({
                        "type": "error",
                        "error": str(e),
                    })
    
    except WebSocketDisconnect:
        manager.disconnect(websocket, channel)


def main():
    """Run the server."""
    import argparse
    
    parser = argparse.ArgumentParser(description="KYC MAF Server")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind to")
    parser.add_argument("--port", type=int, default=8000, help="Port to bind to")
    parser.add_argument("--reload", action="store_true", help="Enable auto-reload")
    args = parser.parse_args()
    
    uvicorn.run(
        "src.maf.server:app",
        host=args.host,
        port=args.port,
        reload=args.reload,
    )


if __name__ == "__main__":
    main()
