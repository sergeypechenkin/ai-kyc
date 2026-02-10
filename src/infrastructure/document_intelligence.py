"""Azure Document Intelligence service for document extraction."""

import os
from pathlib import Path
from typing import Any

from src.infrastructure.config import get_settings


class DocumentIntelligenceService:
    """Service for extracting information from ID documents using Azure Document Intelligence."""

    def __init__(self):
        """Initialize the document intelligence service."""
        self._settings = get_settings()
        self._client = None
        self._initialize_client()

    @property
    def is_available(self) -> bool:
        """Check if Document Intelligence is available."""
        return self._client is not None

    def _initialize_client(self) -> None:
        """Initialize Azure Document Intelligence client if configured."""
        if not self._settings.azure_document_intelligence_configured:
            print("Azure Document Intelligence not configured")
            return

        try:
            from azure.ai.documentintelligence import DocumentIntelligenceClient
            from azure.identity import ClientSecretCredential

            client_id = os.environ.get("AZURE_CLIENT_ID")
            client_secret = os.environ.get("AZURE_CLIENT_SECRET")
            tenant_id = os.environ.get("AZURE_TENANT_ID")

            if all([client_id, client_secret, tenant_id]):
                credential = ClientSecretCredential(
                    tenant_id=tenant_id,
                    client_id=client_id,
                    client_secret=client_secret,
                )
                self._client = DocumentIntelligenceClient(
                    endpoint=self._settings.azure_document_intelligence_endpoint,
                    credential=credential,
                )
                print("Azure Document Intelligence client initialized")
            else:
                print("Service Principal credentials missing for Document Intelligence")
        except ImportError as e:
            print(f"Azure Document Intelligence SDK not installed: {e}")

    async def extract_id_document(self, file_path: Path) -> dict[str, Any]:
        """Extract information from an ID document (passport, driving license).

        Args:
            file_path: Path to the document file

        Returns:
            Extracted fields: first_name, last_name, date_of_birth, nationality, 
            document_number, expiry_date, address (if available)
        """
        if not self._client:
            return {"error": "Document Intelligence not configured"}

        try:
            with open(file_path, "rb") as f:
                document_bytes = f.read()
            
            from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
            
            poller = self._client.begin_analyze_document(
                "prebuilt-idDocument",
                AnalyzeDocumentRequest(bytes_source=document_bytes),
            )
            result = poller.result()

            extracted = {
                "first_name": "",
                "last_name": "",
                "date_of_birth": "",
                "nationality": "",
                "address": "",
                "document_number": "",
                "expiry_date": "",
                "document_type": "",
            }

            if result.documents:
                doc = result.documents[0]
                fields = doc.fields

                # Extract fields from ID document
                if "FirstName" in fields:
                    extracted["first_name"] = fields["FirstName"].value_string or fields["FirstName"].content or ""
                if "LastName" in fields:
                    extracted["last_name"] = fields["LastName"].value_string or fields["LastName"].content or ""
                if "DateOfBirth" in fields:
                    dob = fields["DateOfBirth"].value_date
                    if dob:
                        extracted["date_of_birth"] = dob.isoformat()
                    elif fields["DateOfBirth"].content:
                        extracted["date_of_birth"] = fields["DateOfBirth"].content
                if "Nationality" in fields:
                    extracted["nationality"] = fields["Nationality"].value_string or fields["Nationality"].content or ""
                if "CountryRegion" in fields and not extracted["nationality"]:
                    extracted["nationality"] = fields["CountryRegion"].value_string or fields["CountryRegion"].content or ""
                if "PlaceOfBirth" in fields and not extracted["nationality"]:
                    # Some IDs have place of birth instead of nationality
                    extracted["nationality"] = fields["PlaceOfBirth"].value_string or fields["PlaceOfBirth"].content or ""
                if "Address" in fields:
                    addr_field = fields["Address"]
                    extracted["address"] = addr_field.value_string or addr_field.content or ""
                if "DocumentNumber" in fields:
                    extracted["document_number"] = fields["DocumentNumber"].value_string or fields["DocumentNumber"].content or ""
                if "DateOfExpiration" in fields:
                    exp = fields["DateOfExpiration"].value_date
                    if exp:
                        extracted["expiry_date"] = exp.isoformat()
                    elif fields["DateOfExpiration"].content:
                        extracted["expiry_date"] = fields["DateOfExpiration"].content
                if "DocumentType" in fields:
                    extracted["document_type"] = fields["DocumentType"].value_string or fields["DocumentType"].content or ""

            return extracted

        except Exception as e:
            return {"error": str(e)}

    async def extract_address_document(self, file_path: Path) -> dict[str, Any]:
        """Extract address from utility bill or similar document.

        Uses prebuilt-invoice model first (good for bills), falls back to layout+text extraction.

        Args:
            file_path: Path to the document file

        Returns:
            Extracted address information with name if available
        """
        if not self._client:
            return {"error": "Document Intelligence not configured"}

        try:
            with open(file_path, "rb") as f:
                document_bytes = f.read()
            
            from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
            
            extracted = {
                "first_name": "",
                "last_name": "",
                "date_of_birth": "",
                "nationality": "",
                "address": "",
                "document_number": "",
                "expiry_date": "",
                "document_type": "proof_of_address",
                "document_date": "",  # Date of the bill/invoice
                "is_valid_timeframe": True,  # Whether document is within 3 months
                "validity_message": "",
            }
            
            # Try invoice model first - good for utility bills
            try:
                poller = self._client.begin_analyze_document(
                    "prebuilt-invoice",
                    AnalyzeDocumentRequest(bytes_source=document_bytes),
                )
                result = poller.result()
                
                if result.documents:
                    doc = result.documents[0]
                    fields = doc.fields
                    
                    # Customer name and address
                    if "CustomerName" in fields:
                        name = fields["CustomerName"].content or fields["CustomerName"].value_string or ""
                        # Try to split name into first/last
                        name_parts = name.replace("MR ", "").replace("MRS ", "").replace("MS ", "").strip().split()
                        if len(name_parts) >= 2:
                            extracted["first_name"] = name_parts[0]
                            extracted["last_name"] = " ".join(name_parts[1:])
                        elif name_parts:
                            extracted["last_name"] = name_parts[0]
                    
                    if "CustomerAddress" in fields:
                        addr = fields["CustomerAddress"]
                        extracted["address"] = addr.content or addr.value_string or ""
                    
                    if "BillingAddress" in fields and not extracted["address"]:
                        addr = fields["BillingAddress"]
                        extracted["address"] = addr.content or addr.value_string or ""
                    
                    if "InvoiceId" in fields:
                        extracted["document_number"] = fields["InvoiceId"].content or fields["InvoiceId"].value_string or ""
                    
                    # Extract invoice date for validity check
                    invoice_date = None
                    for date_field in ["InvoiceDate", "DueDate", "ServiceEndDate"]:
                        if date_field in fields:
                            field = fields[date_field]
                            if hasattr(field, 'value_date') and field.value_date:
                                invoice_date = field.value_date
                                extracted["document_date"] = invoice_date.isoformat()
                                break
                            elif field.content:
                                extracted["document_date"] = field.content
                                # Try to parse the date string
                                from dateutil import parser
                                try:
                                    invoice_date = parser.parse(field.content, dayfirst=True).date()
                                except Exception:
                                    pass
                                break
                    
                    # Check if document is within 3 months
                    if invoice_date:
                        from datetime import date
                        from dateutil.relativedelta import relativedelta
                        
                        three_months_ago = date.today() - relativedelta(months=3)
                        if invoice_date < three_months_ago:
                            extracted["is_valid_timeframe"] = False
                            extracted["validity_message"] = f"Document dated {invoice_date.strftime('%d %B %Y')} is older than 3 months. Please provide a more recent proof of address."
                        else:
                            extracted["validity_message"] = f"Document dated {invoice_date.strftime('%d %B %Y')} is valid (within 3 months)."
                    
                    # If we got an address, return success
                    if extracted["address"]:
                        return extracted
                        
            except Exception:
                pass  # Fall through to layout extraction
            
            # Fallback: Use layout model to extract all text
            poller = self._client.begin_analyze_document(
                "prebuilt-layout",
                AnalyzeDocumentRequest(bytes_source=document_bytes),
            )
            result = poller.result()

            full_text = result.content or ""
            
            # Try to find address patterns in text
            import re
            
            # Common address patterns (Irish/UK style)
            # Look for multi-line blocks that look like addresses
            lines = full_text.split('\n')
            address_lines = []
            name_line = ""
            
            for i, line in enumerate(lines):
                line = line.strip()
                # Look for name patterns (MR/MRS/MS followed by name)
                if re.match(r'^(MR|MRS|MS|MISS|DR)\s+[A-Z]', line, re.IGNORECASE):
                    name_line = line
                    # Next few lines are likely address
                    for j in range(i+1, min(i+5, len(lines))):
                        addr_line = lines[j].strip()
                        if addr_line and not re.match(r'^(Your account|To ask|For emergencies|call|MPRN|Date)', addr_line, re.IGNORECASE):
                            address_lines.append(addr_line)
                        else:
                            break
                    break
            
            if name_line:
                name_parts = re.sub(r'^(MR|MRS|MS|MISS|DR)\s+', '', name_line, flags=re.IGNORECASE).strip().split()
                if len(name_parts) >= 2:
                    extracted["first_name"] = name_parts[0]
                    extracted["last_name"] = " ".join(name_parts[1:])
                elif name_parts:
                    extracted["last_name"] = name_parts[0]
            
            if address_lines:
                extracted["address"] = ", ".join(address_lines)
            
            # If we couldn't extract structured data, try to find any address-like text
            if not extracted["address"]:
                # Look for Eircode pattern (Irish postal code) or common address keywords
                for line in lines:
                    line = line.strip()
                    # Irish Eircode pattern: A65 F4E2 or D02 X285
                    if re.search(r'[A-Z]\d{2}\s*[A-Z0-9]{4}', line, re.IGNORECASE):
                        # Found an Eircode, gather nearby lines as address
                        idx = lines.index(line)
                        addr_candidate = []
                        for j in range(max(0, idx-3), min(idx+2, len(lines))):
                            l = lines[j].strip()
                            if l and len(l) > 3 and not re.match(r'^(Date|Account|Invoice|Bill|Amount|Total|VAT|€|\d{1,2}/\d{1,2}/\d{2,4})', l, re.IGNORECASE):
                                addr_candidate.append(l)
                        if addr_candidate:
                            extracted["address"] = ", ".join(addr_candidate[:4])
                        break
                    # UK postcode pattern
                    elif re.search(r'[A-Z]{1,2}\d{1,2}[A-Z]?\s*\d[A-Z]{2}', line, re.IGNORECASE):
                        idx = lines.index(line)
                        addr_candidate = []
                        for j in range(max(0, idx-3), min(idx+2, len(lines))):
                            l = lines[j].strip()
                            if l and len(l) > 3:
                                addr_candidate.append(l)
                        if addr_candidate:
                            extracted["address"] = ", ".join(addr_candidate[:4])
                        break
            
            # Even if we only got partial data, return it - let the user review
            # Only error if we truly got nothing useful
            if not extracted["address"] and not extracted["last_name"] and not extracted["first_name"]:
                # Last resort: return first few meaningful lines as address
                meaningful_lines = [l.strip() for l in lines[:10] if l.strip() and len(l.strip()) > 5]
                if meaningful_lines:
                    extracted["address"] = ", ".join(meaningful_lines[:3])
                    extracted["document_type"] = "proof_of_address"
                    return extracted
                return {"error": "Could not extract address information from this document"}

            return extracted

        except Exception as e:
            return {"error": str(e)}

    async def extract_auto_detect(self, file_path: Path) -> dict[str, Any]:
        """Auto-detect document type and extract information.

        Tries ID document model first. If it detects an ID, uses that result.
        Otherwise falls back to address/invoice extraction.

        Args:
            file_path: Path to the document file

        Returns:
            Extracted fields with document_type indicating what was detected
        """
        import logging
        logger = logging.getLogger(__name__)
        
        if not self._client:
            return {"error": "Document Intelligence not configured"}

        try:
            with open(file_path, "rb") as f:
                document_bytes = f.read()
            
            logger.info(f"Auto-detect: analyzing {file_path}, size={len(document_bytes)} bytes")
            
            from azure.ai.documentintelligence.models import AnalyzeDocumentRequest
            
            # Try ID document first
            poller = self._client.begin_analyze_document(
                "prebuilt-idDocument",
                AnalyzeDocumentRequest(bytes_source=document_bytes),
            )
            result = poller.result()

            # Check if we got a valid ID document
            if result.documents and len(result.documents) > 0:
                doc = result.documents[0]
                confidence = doc.confidence if hasattr(doc, 'confidence') else 0
                doc_type = doc.doc_type if hasattr(doc, 'doc_type') else ""
                
                logger.info(f"ID detection: doc_type={doc_type}, confidence={confidence}, fields={list(doc.fields.keys()) if doc.fields else []}")
                
                # Check for essential ID fields - must have at least name OR date of birth
                # to be considered a valid ID document
                has_name = doc.fields and any(
                    f in doc.fields and (doc.fields[f].value_string or doc.fields[f].content)
                    for f in ["FirstName", "LastName"]
                )
                has_dob = doc.fields and "DateOfBirth" in doc.fields and (
                    doc.fields["DateOfBirth"].value_date or doc.fields["DateOfBirth"].content
                )
                
                # Only use ID extraction if we found meaningful personal data
                is_valid_id = has_name or has_dob
                
                logger.info(f"ID validation: has_name={has_name}, has_dob={has_dob}, is_valid_id={is_valid_id}")
                
                if is_valid_id:
                    # Use ID document extraction
                    extracted = await self._extract_from_id_result(result)
                    
                    # Map doc_type to our format
                    if "passport" in doc_type.lower():
                        extracted["document_type"] = "passport"
                    elif "driver" in doc_type.lower() or "license" in doc_type.lower():
                        extracted["document_type"] = "driving_license"
                    else:
                        extracted["document_type"] = "id_card"
                    
                    return extracted
            
            # Fall back to address document extraction
            logger.info("No ID detected, falling back to address extraction")
            # Need to re-read file since we consumed it
            result = await self.extract_address_document(file_path)
            logger.info(f"Address extraction result: {result}")
            if "error" not in result:
                result["document_type"] = "proof_of_address"
            return result

        except Exception as e:
            logger.exception(f"Error in auto-detect: {e}")
            # If ID detection fails, try address extraction
            try:
                result = await self.extract_address_document(file_path)
                if "error" not in result:
                    result["document_type"] = "proof_of_address"
                return result
            except Exception as e2:
                return {"error": f"Could not process document: {str(e2)}"}

    async def _extract_from_id_result(self, result) -> dict[str, Any]:
        """Extract fields from an ID document analysis result.
        
        Args:
            result: The analysis result from Document Intelligence
            
        Returns:
            Extracted fields dictionary
        """
        extracted = {
            "first_name": "",
            "last_name": "",
            "date_of_birth": "",
            "nationality": "",
            "address": "",
            "document_number": "",
            "expiry_date": "",
            "document_type": "",
        }

        if result.documents:
            doc = result.documents[0]
            fields = doc.fields

            if "FirstName" in fields:
                extracted["first_name"] = fields["FirstName"].value_string or fields["FirstName"].content or ""
            if "LastName" in fields:
                extracted["last_name"] = fields["LastName"].value_string or fields["LastName"].content or ""
            if "DateOfBirth" in fields:
                dob = fields["DateOfBirth"].value_date
                if dob:
                    extracted["date_of_birth"] = dob.isoformat()
                elif fields["DateOfBirth"].content:
                    extracted["date_of_birth"] = fields["DateOfBirth"].content
            if "Nationality" in fields:
                extracted["nationality"] = fields["Nationality"].value_string or fields["Nationality"].content or ""
            if "CountryRegion" in fields and not extracted["nationality"]:
                extracted["nationality"] = fields["CountryRegion"].value_string or fields["CountryRegion"].content or ""
            if "PlaceOfBirth" in fields and not extracted["nationality"]:
                extracted["nationality"] = fields["PlaceOfBirth"].value_string or fields["PlaceOfBirth"].content or ""
            if "Address" in fields:
                addr_field = fields["Address"]
                extracted["address"] = addr_field.value_string or addr_field.content or ""
            if "DocumentNumber" in fields:
                extracted["document_number"] = fields["DocumentNumber"].value_string or fields["DocumentNumber"].content or ""
            if "DateOfExpiration" in fields:
                exp = fields["DateOfExpiration"].value_date
                if exp:
                    extracted["expiry_date"] = exp.isoformat()
                elif fields["DateOfExpiration"].content:
                    extracted["expiry_date"] = fields["DateOfExpiration"].content

        return extracted
