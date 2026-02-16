"""Document validation service for KYC compliance checks.

Primary document (passport, driving license, ID card) is the reference.
All secondary documents (bills, etc.) must match the primary document's name.

Risk Assessment Tiers:
- LOW (0-30): Auto-approve eligible
- MEDIUM (31-70): Proof of funds 6 months required, pending employee review
- HIGH (71-100): Proof of funds 1 year required, compliance escalation
"""

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, TYPE_CHECKING
from dateutil.relativedelta import relativedelta
from dateutil import parser
import re

if TYPE_CHECKING:
    from src.infrastructure.mock_data import CustomerRepository


# Document types that are considered primary (identity documents)
PRIMARY_DOC_TYPES = {"passport", "driving_license", "id_card"}

# Risk score thresholds
RISK_LOW_THRESHOLD = 30
RISK_MEDIUM_THRESHOLD = 70


@dataclass
class RiskAssessment:
    """Risk assessment result for a customer."""
    risk_score: int = 0
    risk_tier: str = "low"  # low, medium, high
    country_risk: dict | None = None
    pep_matches: list[dict] = field(default_factory=list)
    is_pep: bool = False
    required_documents: list[str] = field(default_factory=list)
    proof_of_funds_months: int = 0  # 0 = not required, 6 or 12
    max_document_age_months: int = 3  # Max age for supporting documents
    approval_workflow: str = "auto_approve"  # auto_approve, employee_review, compliance_escalation
    alerts: list[str] = field(default_factory=list)


@dataclass
class ExtractedDocData:
    """Extracted data from a document."""
    doc_type: str
    full_name: str = ""  # Combined full name
    first_name: str = ""  # Deprecated - use full_name
    last_name: str = ""  # Deprecated - use full_name
    date_of_birth: str = ""
    expiry_date: str = ""
    document_date: str = ""
    address: str = ""
    nationality: str = ""
    
    @property
    def is_primary(self) -> bool:
        """Check if this is a primary identity document."""
        return self.doc_type in PRIMARY_DOC_TYPES


@dataclass
class ValidationResult:
    """Result of document validation."""
    is_valid: bool = True
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    # Success validation messages (e.g., "Name matches primary document")
    validation_messages: list[str] = field(default_factory=list)
    # Indicates what type of document caused the mismatch (for UI)
    mismatch_with_primary: bool = False
    # Risk assessment (populated for primary documents)
    risk_assessment: RiskAssessment | None = None


class DocumentValidationService:
    """Service for validating documents during KYC process.
    
    Primary document (passport, ID, license) is the reference.
    All secondary documents must match the primary's name/DOB.
    """

    def __init__(self, customer_repo: "CustomerRepository | None" = None):
        """Initialize the validation service.
        
        Args:
            customer_repo: Optional customer repository for country risk and PEP checks
        """
        # Store primary document by session_id
        self._primary_documents: dict[str, ExtractedDocData] = {}
        # Store secondary documents by session_id -> list
        self._secondary_documents: dict[str, list[ExtractedDocData]] = {}
        # Store risk assessment by session_id
        self._risk_assessments: dict[str, RiskAssessment] = {}
        # Customer repository for risk checks
        self._customer_repo = customer_repo

    def get_primary_document(self, session_id: str) -> ExtractedDocData | None:
        """Get the primary document for a session."""
        return self._primary_documents.get(session_id)

    def get_secondary_documents(self, session_id: str) -> list[ExtractedDocData]:
        """Get all secondary documents for a session."""
        return self._secondary_documents.get(session_id, [])

    def get_session_documents(self, session_id: str) -> list[ExtractedDocData]:
        """Get all documents for a session (for backward compatibility)."""
        docs = []
        primary = self.get_primary_document(session_id)
        if primary:
            docs.append(primary)
        docs.extend(self.get_secondary_documents(session_id))
        return docs

    def clear_session(self, session_id: str) -> None:
        """Clear all documents for a session."""
        self._primary_documents.pop(session_id, None)
        self._secondary_documents.pop(session_id, None)
        self._risk_assessments.pop(session_id, None)

    def replace_primary_document(self, session_id: str) -> None:
        """Clear primary document and all secondary documents.
        
        Called when user wants to upload a new primary document.
        """
        self._primary_documents.pop(session_id, None)
        self._secondary_documents.pop(session_id, None)
        self._risk_assessments.pop(session_id, None)
        print(f"[INFO] Cleared all documents for session {session_id}")

    def get_risk_assessment(self, session_id: str) -> RiskAssessment | None:
        """Get the risk assessment for a session."""
        return self._risk_assessments.get(session_id)

    def _perform_risk_assessment(
        self, 
        session_id: str, 
        doc_data: ExtractedDocData
    ) -> RiskAssessment:
        """Perform risk assessment for a primary document.
        
        Checks:
        1. Country risk based on nationality
        2. PEP watchlist based on name
        
        Returns RiskAssessment with calculated tier and required actions.
        """
        assessment = RiskAssessment()
        
        full_name = doc_data.full_name.strip() or f"{doc_data.first_name} {doc_data.last_name}".strip()
        nationality = doc_data.nationality
        
        # Check country risk
        if self._customer_repo and nationality:
            country_risk = self._customer_repo.get_country_risk(nationality)
            if country_risk:
                assessment.country_risk = country_risk
                country_score = country_risk.get("risk_score", 0)
                assessment.risk_score = max(assessment.risk_score, country_score)
                
                if country_risk.get("risk_level", "").lower() in ("high", "critical"):
                    assessment.alerts.append(
                        f"⚠️ HIGH RISK COUNTRY: {nationality} - {country_risk.get('reason', '')}"
                    )
                elif country_risk.get("risk_level", "").lower() == "medium":
                    assessment.alerts.append(
                        f"⚡ MEDIUM RISK COUNTRY: {nationality} - {country_risk.get('reason', '')}"
                    )
        
        # Check PEP watchlist
        if self._customer_repo and full_name:
            pep_matches = self._customer_repo.check_pep(full_name)
            if pep_matches:
                assessment.pep_matches = pep_matches
                assessment.is_pep = True
                # PEP status adds 40 points to risk score
                assessment.risk_score = min(100, assessment.risk_score + 40)
                for match in pep_matches:
                    assessment.alerts.append(
                        f"🔴 PEP MATCH: {match.get('name', 'Unknown')} - {match.get('position', '')} ({match.get('country', '')})"
                    )
        
        # Determine risk tier and requirements
        if assessment.risk_score <= RISK_LOW_THRESHOLD:
            assessment.risk_tier = "low"
            assessment.approval_workflow = "auto_approve"
            assessment.proof_of_funds_months = 0
        elif assessment.risk_score <= RISK_MEDIUM_THRESHOLD:
            assessment.risk_tier = "medium"
            assessment.approval_workflow = "employee_review"
            assessment.proof_of_funds_months = 6
            assessment.max_document_age_months = 3
            assessment.required_documents = [
                "Bank statements for last 6 months",
                "Proof of income/employment"
            ]
        else:
            assessment.risk_tier = "high"
            assessment.approval_workflow = "compliance_escalation"
            assessment.proof_of_funds_months = 12
            assessment.max_document_age_months = 3
            assessment.required_documents = [
                "Bank statements for last 12 months",
                "Proof of income/employment",
                "Source of wealth declaration"
            ]
            assessment.alerts.append(
                "⛔ COMPLIANCE ESCALATION REQUIRED - High risk score"
            )
        
        # Store assessment for the session
        self._risk_assessments[session_id] = assessment
        
        print(f"[INFO] Risk assessment for session {session_id}: "
              f"score={assessment.risk_score}, tier={assessment.risk_tier}, "
              f"workflow={assessment.approval_workflow}")
        
        return assessment

    def validate_document(
        self, 
        session_id: str, 
        extracted_data: dict[str, Any]
    ) -> ValidationResult:
        """Validate a newly uploaded document.
        
        Primary documents (passport, ID, license):
        - Validated for expiry date
        - Becomes the reference for name matching
        
        Secondary documents (bills, etc.):
        - Validated against primary document's name
        - Validated for document date (not older than 3 months for bills)
        
        Args:
            session_id: Session identifier
            extracted_data: Data extracted from the document
            
        Returns:
            ValidationResult with errors and warnings
        """
        result = ValidationResult()
        
        doc_type = extracted_data.get("document_type", "unknown")
        first_name = extracted_data.get("first_name", "").strip()
        last_name = extracted_data.get("last_name", "").strip()
        full_name = extracted_data.get("full_name", "").strip()
        dob = extracted_data.get("date_of_birth", "").strip()
        expiry_date = extracted_data.get("expiry_date", "").strip()
        document_date = extracted_data.get("document_date", "").strip()
        
        # Use full_name if available, otherwise construct from first/last
        if not full_name:
            full_name = f"{first_name} {last_name}".strip()
        
        # Create doc data record
        doc_data = ExtractedDocData(
            doc_type=doc_type,
            full_name=full_name,
            first_name=first_name,
            last_name=last_name,
            date_of_birth=dob,
            expiry_date=expiry_date,
            document_date=document_date,
            address=extracted_data.get("address", ""),
            nationality=extracted_data.get("nationality", ""),
        )
        
        is_primary = doc_data.is_primary
        
        if is_primary:
            # Validating a primary document
            
            # 1. Check expiry
            if expiry_date:
                expiry_valid, expiry_msg = self._validate_expiry(expiry_date)
                if not expiry_valid:
                    result.errors.append(expiry_msg)
                    result.is_valid = False
            
            # 2. If there's already a primary, check if names match
            existing_primary = self.get_primary_document(session_id)
            if existing_primary:
                # Replacing primary - clear everything and use new primary
                self.replace_primary_document(session_id)
            
            # Store as primary
            self._primary_documents[session_id] = doc_data
            print(f"[INFO] Primary document set for session {session_id}: {doc_type}")
            
            # 3. Perform risk assessment (country + PEP check)
            result.risk_assessment = self._perform_risk_assessment(session_id, doc_data)
            
        else:
            # Validating a secondary document (supporting docs like bank statements, etc.)
            
            # 1. Check document date - ALL secondary documents must be within 3 months
            if document_date:
                date_valid, date_msg = self._validate_document_date(document_date)
                if date_valid:
                    result.validation_messages.append(date_msg)
                else:
                    result.errors.append(date_msg)
                    result.is_valid = False
            
            # 2. Validate against primary document
            primary = self.get_primary_document(session_id)
            if primary:
                # Validate name consistency
                name_valid, name_msg = self._validate_name_match(doc_data, primary)
                if name_valid:
                    result.validation_messages.append(f"✓ Name matches primary document ({primary.full_name})")
                else:
                    result.errors.append(name_msg)
                    result.is_valid = False
                    result.mismatch_with_primary = True
                
                # Validate DOB consistency if available
                if dob and primary.date_of_birth:
                    dob_valid, dob_msg = self._validate_dob_match(doc_data, primary)
                    if dob_valid:
                        result.validation_messages.append(f"✓ Date of birth matches primary document")
                    else:
                        result.errors.append(dob_msg)
                        result.is_valid = False
                        result.mismatch_with_primary = True
            
            # Store secondary document (replace if same type exists)
            if session_id not in self._secondary_documents:
                self._secondary_documents[session_id] = []
            self._secondary_documents[session_id] = [
                d for d in self._secondary_documents[session_id]
                if d.doc_type != doc_type
            ]
            self._secondary_documents[session_id].append(doc_data)
        
        return result

    def _extract_latin_only(self, text: str) -> str:
        """Extract only Latin characters from text."""
        latin_only = re.sub(r"[^a-zA-Z\s\-']", "", text)
        latin_only = re.sub(r"\s+", " ", latin_only).strip()
        return latin_only

    def _normalize_name(self, name: str) -> str:
        """Normalize a name for comparison.
        
        Returns a sorted set of name words to enable order-independent matching.
        E.g., "ASHLEY CHRISTY ERIKA FERNANDEZ" and "ERIKA ASHLEY CHRISTY FERNANDEZ"
        will both normalize to the same sorted string.
        """
        name = self._extract_latin_only(name)
        name = name.upper().strip()
        name = name.replace("-", " ").replace("'", "")
        # Split into words and sort them to make order-independent
        parts = sorted([p.strip() for p in name.split() if p.strip()])
        # Return sorted words joined by space
        return " ".join(parts)

    def _validate_expiry(self, expiry_date: str) -> tuple[bool, str]:
        """Validate that document has not expired."""
        try:
            if "-" in expiry_date and len(expiry_date) == 10:
                exp_date = datetime.strptime(expiry_date, "%Y-%m-%d").date()
            else:
                exp_date = parser.parse(expiry_date, dayfirst=True).date()
            
            today = date.today()
            if exp_date < today:
                return False, f"Document has EXPIRED on {exp_date.strftime('%d %B %Y')}. Please provide a valid, non-expired document."
            
            if exp_date < today + relativedelta(months=3):
                return True, f"Document expires soon ({exp_date.strftime('%d %B %Y')})"
            
            return True, ""
        except Exception:
            return True, ""

    def _validate_bill_date(self, document_date: str) -> tuple[bool, str]:
        """Validate that utility bill is not older than 3 months."""
        try:
            if "-" in document_date and len(document_date) == 10:
                doc_date = datetime.strptime(document_date, "%Y-%m-%d").date()
            else:
                doc_date = parser.parse(document_date, dayfirst=True).date()
            
            three_months_ago = date.today() - relativedelta(months=3)
            if doc_date < three_months_ago:
                return False, f"Proof of address dated {doc_date.strftime('%d %B %Y')} is older than 3 months. Please provide a more recent document."
            
            return True, f"✓ Document dated {doc_date.strftime('%d %B %Y')} is valid (within 3 months)"
        except Exception:
            return True, ""

    def _validate_document_date(self, document_date: str) -> tuple[bool, str]:
        """Validate that document is not older than 3 months."""
        try:
            if "-" in document_date and len(document_date) == 10:
                doc_date = datetime.strptime(document_date, "%Y-%m-%d").date()
            else:
                doc_date = parser.parse(document_date, dayfirst=True).date()
            
            three_months_ago = date.today() - relativedelta(months=3)
            if doc_date < three_months_ago:
                return False, f"Document dated {doc_date.strftime('%d %B %Y')} is older than 3 months. Please provide a more recent document."
            
            return True, f"✓ Document dated {doc_date.strftime('%d %B %Y')} is valid (within 3 months)"
        except Exception:
            return True, ""

    def _validate_name_match(
        self, 
        doc: ExtractedDocData, 
        primary: ExtractedDocData
    ) -> tuple[bool, str]:
        """Validate that full names match between document and primary.
        
        Compares complete names as strings rather than splitting into first/last,
        to avoid issues with compound names and different name orderings.
        """
        doc_name = doc.full_name.strip()
        primary_name = primary.full_name.strip()
        
        if not doc_name or not primary_name:
            return True, ""  # Skip validation if either name is missing
        
        # Normalize both names for comparison (remove accents, convert to uppercase, etc.)
        norm_doc = self._normalize_name(doc_name)
        norm_primary = self._normalize_name(primary_name)
        
        if norm_doc and norm_primary and norm_doc != norm_primary:
            return False, f"Name mismatch with ID document: '{doc_name}' vs '{primary_name}' on {primary.doc_type}. Please upload a document with matching name, or upload a different ID document."
        
        return True, ""

    def _validate_dob_match(
        self,
        doc: ExtractedDocData,
        primary: ExtractedDocData
    ) -> tuple[bool, str]:
        """Validate that dates of birth match between documents."""
        try:
            dob_doc = self._parse_date(doc.date_of_birth)
            dob_primary = self._parse_date(primary.date_of_birth)
            
            if dob_doc and dob_primary and dob_doc != dob_primary:
                return False, f"Date of birth mismatch: {dob_doc.strftime('%d/%m/%Y')} vs {dob_primary.strftime('%d/%m/%Y')} on {primary.doc_type}"
            
            return True, ""
        except Exception:
            return True, ""

    def _parse_date(self, date_str: str) -> date | None:
        """Parse a date string to date object."""
        if not date_str:
            return None
        try:
            if "-" in date_str and len(date_str) == 10:
                return datetime.strptime(date_str, "%Y-%m-%d").date()
            return parser.parse(date_str, dayfirst=True).date()
        except Exception:
            return None
