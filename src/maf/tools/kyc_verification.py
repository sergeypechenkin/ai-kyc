"""KYC verification tools for MAF agents.

Converted from src/plugins/kyc_verify.py
"""

import os
import json
from datetime import datetime
from typing import TYPE_CHECKING
from agent_framework import ai_function
from src.maf.activity import broadcast_activity_sync

if TYPE_CHECKING:
    from src.infrastructure.mock_data import CustomerRepository

# Module-level repository reference (set during initialization)
_customer_repo: "CustomerRepository | None" = None

# File path for pending submissions persistence
_PENDING_SUBMISSIONS_FILE = os.path.join(os.path.dirname(__file__), '..', '..', '..', 'data', 'pending_submissions.json')


def _load_pending_submissions() -> list[dict]:
    """Load pending submissions from file."""
    try:
        if os.path.exists(_PENDING_SUBMISSIONS_FILE):
            with open(_PENDING_SUBMISSIONS_FILE, 'r') as f:
                data = json.load(f)
                print(f"[DEBUG] Loaded {len(data)} pending submissions from file")
                return data
    except Exception as e:
        print(f"[WARNING] Failed to load pending submissions: {e}")
    return []


def _save_pending_submissions(submissions: list[dict]) -> None:
    """Save pending submissions to file."""
    try:
        os.makedirs(os.path.dirname(_PENDING_SUBMISSIONS_FILE), exist_ok=True)
        with open(_PENDING_SUBMISSIONS_FILE, 'w') as f:
            json.dump(submissions, f, indent=2, default=str)
        print(f"[DEBUG] Saved {len(submissions)} pending submissions to file")
    except Exception as e:
        print(f"[WARNING] Failed to save pending submissions: {e}")


# Pending compliance submissions from document uploads (shared with server.py)
# Load from file on module load
_pending_submissions: list[dict] = _load_pending_submissions()
print(f"[DEBUG] kyc_verification module loaded with {len(_pending_submissions)} pending submissions")


def init_kyc_tools(customer_repository: "CustomerRepository") -> None:
    """Initialize KYC tools with repository.
    
    Args:
        customer_repository: Repository for customer data access
    """
    global _customer_repo
    _customer_repo = customer_repository


def add_pending_submission(submission: dict) -> None:
    """Add a new pending submission for compliance review.
    
    Args:
        submission: Dict with customer_id, customer_name, status, submitted_date, risk_tier, session_id
    """
    global _pending_submissions
    # Avoid duplicates by session_id
    _pending_submissions = [s for s in _pending_submissions if s.get("session_id") != submission.get("session_id")]
    _pending_submissions.append(submission)
    _save_pending_submissions(_pending_submissions)
    print(f"[DEBUG] Added pending submission: {submission.get('customer_id')} - Total: {len(_pending_submissions)}")


def get_pending_submissions() -> list[dict]:
    """Get pending submissions added via document upload."""
    return _pending_submissions


@ai_function
def verify_document(customer_id: str, document_type: str) -> str:
    """Verify a customer's submitted document.
    
    Checks document validity, expiry, and matches against customer records.
    
    Args:
        customer_id: Customer's ID
        document_type: Type of document (passport, driving_license, utility_bill)
        
    Returns:
        Verification result
    """
    broadcast_activity_sync("tool_call", "System", {
        "tool": "verify_document",
        "args": {"customer_id": customer_id, "document_type": document_type}
    })
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    doc = _customer_repo.get_document(customer_id, document_type)
    if not doc:
        broadcast_activity_sync("tool_result", "System", {
            "tool": "verify_document",
            "result": "not_found"
        })
        return f"No {document_type} found for customer {customer_id}"

    # Check expiry
    expiry = datetime.strptime(doc["expiry_date"], "%Y-%m-%d")
    is_expired = expiry < datetime.now()

    if is_expired:
        broadcast_activity_sync("tool_result", "System", {
            "tool": "verify_document",
            "result": "expired",
            "expiry_date": doc["expiry_date"]
        })
        return (
            f"Document Verification Failed:\n"
            f"- Document: {document_type}\n"
            f"- Status: EXPIRED\n"
            f"- Expired on: {doc['expiry_date']}\n"
            f"- Action Required: Request updated document from customer"
        )

    if doc["status"] == "verified":
        broadcast_activity_sync("tool_result", "System", {
            "tool": "verify_document",
            "result": "verified",
            "valid_until": doc["expiry_date"]
        })
        return (
            f"Document Verification Passed:\n"
            f"- Document: {document_type}\n"
            f"- Status: VERIFIED\n"
            f"- Valid until: {doc['expiry_date']}"
        )

    broadcast_activity_sync("tool_result", "System", {
        "tool": "verify_document",
        "result": "pending",
        "status": doc["status"]
    })
    return (
        f"Document Pending Review:\n"
        f"- Document: {document_type}\n"
        f"- Status: {doc['status'].upper()}\n"
        f"- Valid until: {doc['expiry_date']}"
    )


@ai_function
def approve_kyc(customer_id: str, notes: str = "") -> str:
    """Approve a customer's KYC application.
    
    Use after all documents have been verified.
    
    Args:
        customer_id: Customer's ID
        notes: Optional approval notes
        
    Returns:
        Approval confirmation
    """
    broadcast_activity_sync("tool_call", "System", {
        "tool": "approve_kyc",
        "args": {"customer_id": customer_id, "notes": notes[:50] if notes else ""}
    })
    
    # Handle NEW-xxxx customers (from document uploads, not yet in CSV)
    if customer_id.startswith("NEW-"):
        # Debug: Log what's in pending submissions
        print(f"[DEBUG] approve_kyc called for {customer_id}")
        print(f"[DEBUG] _pending_submissions has {len(_pending_submissions)} entries:")
        for sub in _pending_submissions:
            print(f"[DEBUG]   - {sub.get('customer_id')}: {sub.get('customer_name')}")
        
        # Find and update the pending submission
        for submission in _pending_submissions:
            if submission.get("customer_id") == customer_id:
                submission["status"] = "approved"
                _save_pending_submissions(_pending_submissions)
                broadcast_activity_sync("tool_result", "System", {
                    "tool": "approve_kyc",
                    "result": "approved",
                    "customer_id": customer_id
                })
                customer_name = submission.get("customer_name", "Unknown")
                return (
                    f"KYC Approved:\n"
                    f"- Customer: {customer_name} ({customer_id})\n"
                    f"- Status: APPROVED\n"
                    f"- Approved at: {datetime.now().isoformat()}\n"
                    f"- Notes: {notes or 'None'}\n"
                    f"Customer can now proceed with account services."
                )
        broadcast_activity_sync("tool_result", "System", {
            "tool": "approve_kyc",
            "result": "failed"
        })
        return f"Customer {customer_id} not found in pending submissions"
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    result = _customer_repo.update_kyc_status(
        customer_id,
        status="approved",
        reviewer="bank-employee-agent",
        notes=notes,
    )

    if not result:
        broadcast_activity_sync("tool_result", "System", {
            "tool": "approve_kyc",
            "result": "failed"
        })
        return f"Failed to approve KYC for customer {customer_id}"

    broadcast_activity_sync("tool_result", "System", {
        "tool": "approve_kyc",
        "result": "approved",
        "customer_id": customer_id
    })
    
    return (
        f"KYC Approved:\n"
        f"- Customer: {customer_id}\n"
        f"- Status: APPROVED\n"
        f"- Approved at: {datetime.now().isoformat()}\n"
        f"- Notes: {notes or 'None'}\n"
        f"Customer can now proceed with account services."
    )


@ai_function
def reject_kyc(customer_id: str, reason: str) -> str:
    """Reject a customer's KYC application with a reason.
    
    Args:
        customer_id: Customer's ID
        reason: Rejection reason
        
    Returns:
        Rejection confirmation
    """
    # Handle NEW-xxxx customers (from document uploads, not yet in CSV)
    if customer_id.startswith("NEW-"):
        for submission in _pending_submissions:
            if submission.get("customer_id") == customer_id:
                submission["status"] = "rejected"
                _save_pending_submissions(_pending_submissions)
                customer_name = submission.get("customer_name", "Unknown")
                return (
                    f"KYC Rejected:\n"
                    f"- Customer: {customer_name} ({customer_id})\n"
                    f"- Status: REJECTED\n"
                    f"- Reason: {reason}\n"
                    f"- Rejected at: {datetime.now().isoformat()}\n"
                    f"Customer must be notified of the rejection and reason."
                )
        return f"Customer {customer_id} not found in pending submissions"
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    result = _customer_repo.update_kyc_status(
        customer_id,
        status="rejected",
        reviewer="bank-employee-agent",
        notes=reason,
    )

    if not result:
        return f"Failed to update KYC status for customer {customer_id}"

    return (
        f"KYC Rejected:\n"
        f"- Customer: {customer_id}\n"
        f"- Status: REJECTED\n"
        f"- Reason: {reason}\n"
        f"- Rejected at: {datetime.now().isoformat()}\n"
        f"Customer must be notified of the rejection and reason."
    )


@ai_function
def request_additional_documents(customer_id: str, documents_needed: str, reason: str) -> str:
    """Request additional documents from a customer for KYC verification.
    
    Args:
        customer_id: Customer's ID
        documents_needed: List of documents needed
        reason: Reason for the request
        
    Returns:
        Request confirmation
    """
    # Handle NEW-xxxx customers (from document uploads, not yet in CSV)
    if customer_id.startswith("NEW-"):
        for submission in _pending_submissions:
            if submission.get("customer_id") == customer_id:
                submission["status"] = "pending_documents"
                _save_pending_submissions(_pending_submissions)
                customer_name = submission.get("customer_name", "Unknown")
                return (
                    f"Document Request Created:\n"
                    f"- Customer: {customer_name} ({customer_id})\n"
                    f"- Documents Needed: {documents_needed}\n"
                    f"- Reason: {reason}\n"
                    f"- Status: PENDING_DOCUMENTS\n"
                    f"Customer must be notified to submit the requested documents."
                )
        return f"Customer {customer_id} not found in pending submissions"
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    _customer_repo.update_kyc_status(
        customer_id,
        status="pending_documents",
        reviewer="bank-employee-agent",
        notes=f"Documents requested: {documents_needed}. Reason: {reason}",
    )

    return (
        f"Document Request Created:\n"
        f"- Customer: {customer_id}\n"
        f"- Documents Needed: {documents_needed}\n"
        f"- Reason: {reason}\n"
        f"- Status: PENDING_DOCUMENTS\n"
        f"Customer must be notified to submit the requested documents."
    )


@ai_function
def get_pending_reviews() -> str:
    """Get list of customers with pending KYC reviews.
    
    Returns:
        List of pending reviews
    """
    print(f"[DEBUG] get_pending_reviews called, _pending_submissions has {len(_pending_submissions)} entries")
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    # Get pending reviews from CSV
    pending = _customer_repo.get_pending_reviews()
    
    # Add pending submissions from document uploads
    for submission in _pending_submissions:
        # Check if already in pending list
        existing_ids = [p["customer_id"] for p in pending]
        if submission.get("customer_id") not in existing_ids:
            pending.append(submission)

    if not pending:
        return "No pending KYC reviews at this time."

    lines = []
    for review in pending:
        risk_tier = review.get("risk_tier", "")
        risk_info = f" [RISK: {risk_tier.upper()}]" if risk_tier else ""
        lines.append(
            f"- {review['customer_id']}: {review['customer_name']} - "
            f"Status: {review['status']} (since {review['submitted_date']}){risk_info}"
        )

    return f"Pending KYC Reviews ({len(pending)}):\n" + "\n".join(lines)


@ai_function
def check_pep_status(customer_id: str) -> str:
    """Check if a customer matches any PEP (Politically Exposed Person) watchlist entries.
    
    IMPORTANT: This check is MANDATORY before approving any KYC application.
    PEP matches require enhanced due diligence and may need senior approval.
    
    Args:
        customer_id: Customer's ID to check against PEP watchlist
        
    Returns:
        PEP screening result with any matches and recommendations
    """
    broadcast_activity_sync("tool_call", "System", {
        "tool": "check_pep_status",
        "args": {"customer_id": customer_id}
    })
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    customer = _customer_repo.get_by_id(customer_id)
    if not customer:
        broadcast_activity_sync("tool_result", "System", {
            "tool": "check_pep_status",
            "result": "customer_not_found"
        })
        return f"Customer {customer_id} not found"
    
    full_name = f"{customer['first_name']} {customer['last_name']}"
    matches = _customer_repo.check_pep(full_name)
    
    if matches:
        # Determine highest risk level from matches
        risk_levels = {"critical": 4, "high": 3, "medium": 2, "low": 1}
        highest_risk = max(matches, key=lambda m: risk_levels.get(m.get("risk_level", "low"), 0))
        
        broadcast_activity_sync("tool_result", "System", {
            "tool": "check_pep_status",
            "result": "pep_match",
            "matches_count": len(matches),
            "highest_risk": highest_risk.get("risk_level", "unknown")
        })
        
        match_details = []
        for m in matches:
            match_details.append(
                f"  - Name: {m.get('name', 'N/A')}\n"
                f"    Country: {m.get('country', 'N/A')}\n"
                f"    Category: {m.get('category', 'N/A')}\n"
                f"    Risk Level: {m.get('risk_level', 'N/A').upper()}\n"
                f"    Source: {m.get('source', 'N/A')}"
            )
        
        match_details_str = "\n".join(match_details)
        
        return (
            f"⚠️ PEP SCREENING ALERT\n"
            f"========================\n"
            f"Customer: {full_name} ({customer_id})\n"
            f"Nationality: {customer.get('nationality', 'N/A')}\n\n"
            f"PEP MATCHES FOUND: {len(matches)}\n"
            f"{match_details_str}\n\n"
            f"RECOMMENDATION:\n"
            f"- Enhanced Due Diligence (EDD) REQUIRED\n"
            f"- Senior compliance officer approval REQUIRED\n"
            f"- Document source of funds\n"
            f"- Consider escalating to Compliance department\n\n"
            f"DO NOT approve KYC without completing enhanced due diligence."
        )
    
    broadcast_activity_sync("tool_result", "System", {
        "tool": "check_pep_status",
        "result": "clear",
        "customer_id": customer_id
    })
    
    return (
        f"✓ PEP SCREENING CLEAR\n"
        f"=====================\n"
        f"Customer: {full_name} ({customer_id})\n"
        f"Nationality: {customer.get('nationality', 'N/A')}\n\n"
        f"No matches found in PEP watchlist.\n"
        f"Standard KYC approval process may proceed."
    )


@ai_function
def check_country_risk(customer_id: str) -> str:
    """Check customer's nationality against country risk database.
    
    Returns risk assessment with required action:
    - LOW risk (score 0-30): Auto-approve eligible
    - MEDIUM risk (score 31-70): Bank employee review + income source documents required
    - HIGH risk (score 71-90): Compliance case escalation required
    - CRITICAL risk (score 91-100): Senior compliance review, may be prohibited
    
    This check is MANDATORY for compliance before approving KYC.
    
    Args:
        customer_id: Customer's ID to check
        
    Returns:
        Country risk assessment with risk score and required actions
    """
    broadcast_activity_sync("tool_call", "System", {
        "tool": "check_country_risk",
        "args": {"customer_id": customer_id}
    })
    
    if _customer_repo is None:
        return "Error: Customer repository not initialized"
    
    customer = _customer_repo.get_by_id(customer_id)
    if not customer:
        broadcast_activity_sync("tool_result", "System", {
            "tool": "check_country_risk",
            "result": "customer_not_found"
        })
        return f"Customer {customer_id} not found"
    
    nationality = customer.get('nationality', '')
    full_name = f"{customer['first_name']} {customer['last_name']}"
    
    risk_info = _customer_repo.get_country_risk(nationality)
    
    if not risk_info:
        risk_info = {
            "risk_level": "low",
            "risk_score": 20,
            "reason": "Country not in risk database",
            "action": "auto_approve",
            "requires_edd": False
        }
    
    risk_level = risk_info['risk_level'].upper()
    risk_score = risk_info.get('risk_score', 0)
    action = risk_info.get('action', 'employee_review')
    
    broadcast_activity_sync("tool_result", "System", {
        "tool": "check_country_risk",
        "result": action,
        "risk_level": risk_level,
        "risk_score": risk_score,
        "country": nationality
    })
    
    # Format response based on action type
    if action == "auto_approve":
        return (
            f"✓ COUNTRY RISK: LOW\n"
            f"====================\n"
            f"Customer: {full_name} ({customer_id})\n"
            f"Nationality: {nationality}\n"
            f"Risk Score: {risk_score}/100\n"
            f"Risk Level: {risk_level}\n\n"
            f"ASSESSMENT: {risk_info['reason']}\n\n"
            f"ACTION: AUTO-APPROVE ELIGIBLE\n"
            f"- Standard KYC verification sufficient\n"
            f"- No additional documentation required\n"
            f"- Proceed with document verification and approval"
        )
    
    elif action == "employee_review":
        return (
            f"⚠️ COUNTRY RISK: MEDIUM\n"
            f"========================\n"
            f"Customer: {full_name} ({customer_id})\n"
            f"Nationality: {nationality}\n"
            f"Risk Score: {risk_score}/100\n"
            f"Risk Level: {risk_level}\n\n"
            f"ASSESSMENT: {risk_info['reason']}\n\n"
            f"REQUIRED ACTIONS:\n"
            f"1. Bank employee manual review REQUIRED\n"
            f"2. Request INCOME SOURCE DOCUMENTS from customer:\n"
            f"   - Employment contract or business registration\n"
            f"   - Recent payslips (last 3 months) or tax returns\n"
            f"   - Bank statements showing regular income\n"
            f"3. Document source of initial deposit\n"
            f"4. Enhanced Due Diligence (EDD) checklist\n\n"
            f"DO NOT auto-approve. Manual review required."
        )
    
    else:  # compliance_escalation (high/critical)
        if risk_level == "CRITICAL":
            return (
                f"🚫 COUNTRY RISK: CRITICAL\n"
                f"==========================\n"
                f"Customer: {full_name} ({customer_id})\n"
                f"Nationality: {nationality}\n"
                f"Risk Score: {risk_score}/100\n"
                f"Risk Level: {risk_level}\n\n"
                f"ASSESSMENT: {risk_info['reason']}\n\n"
                f"⛔ COMPLIANCE ESCALATION MANDATORY\n"
                f"This jurisdiction is on FATF Black List or subject to comprehensive sanctions.\n\n"
                f"REQUIRED ACTIONS:\n"
                f"1. STOP - Do not proceed with KYC approval\n"
                f"2. Escalate to Compliance Department IMMEDIATELY\n"
                f"3. Senior Compliance Officer review required\n"
                f"4. Legal department consultation may be needed\n"
                f"5. Document all interactions\n\n"
                f"ACCOUNT OPENING MAY BE PROHIBITED."
            )
        else:  # HIGH
            return (
                f"🔴 COUNTRY RISK: HIGH\n"
                f"======================\n"
                f"Customer: {full_name} ({customer_id})\n"
                f"Nationality: {nationality}\n"
                f"Risk Score: {risk_score}/100\n"
                f"Risk Level: {risk_level}\n\n"
                f"ASSESSMENT: {risk_info['reason']}\n\n"
                f"⚠️ COMPLIANCE ESCALATION REQUIRED\n\n"
                f"REQUIRED ACTIONS:\n"
                f"1. Escalate to Compliance Department\n"
                f"2. Senior management approval REQUIRED\n"
                f"3. Full Enhanced Due Diligence (EDD):\n"
                f"   - Verified source of wealth\n"
                f"   - Purpose of account and expected activity\n"
                f"   - Income source documentation\n"
                f"   - Reference checks\n"
                f"4. Enhanced ongoing monitoring flagged\n"
                f"5. Annual KYC review scheduled\n\n"
                f"DO NOT approve without compliance sign-off."
            )


# Export all tools as a list for easy agent configuration
KYC_VERIFICATION_TOOLS = [
    verify_document,
    approve_kyc,
    reject_kyc,
    request_additional_documents,
    get_pending_reviews,
    check_pep_status,
    check_country_risk,
]
