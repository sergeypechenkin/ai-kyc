"""Azure Document Intelligence service for document extraction."""

import io
import os
from pathlib import Path
from typing import Any

from src.infrastructure.config import get_settings

# Maximum file size for Azure Document Intelligence (4MB for images)
MAX_IMAGE_SIZE_BYTES = 4 * 1024 * 1024


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

    def _compress_image(self, file_path: Path) -> bytes:
        """Compress an image if it exceeds the maximum size.
        
        Args:
            file_path: Path to the image file
            
        Returns:
            Compressed image bytes, or original bytes if no compression needed
        """
        with open(file_path, "rb") as f:
            original_bytes = f.read()
        
        # Check if it's a PDF (no compression needed for PDFs)
        if file_path.suffix.lower() == ".pdf":
            return original_bytes
        
        # If file is small enough, return as-is
        if len(original_bytes) <= MAX_IMAGE_SIZE_BYTES:
            return original_bytes
        
        try:
            from PIL import Image
            
            # Open the image
            img = Image.open(io.BytesIO(original_bytes))
            
            # Convert to RGB if necessary (for JPEG)
            if img.mode in ('RGBA', 'P'):
                img = img.convert('RGB')
            
            # Calculate resize factor to fit within 4MB
            # Start with quality reduction, then resize if needed
            output = io.BytesIO()
            quality = 85
            
            while quality >= 30:
                output.seek(0)
                output.truncate()
                img.save(output, format='JPEG', quality=quality, optimize=True)
                
                if output.tell() <= MAX_IMAGE_SIZE_BYTES:
                    print(f"Image compressed: {len(original_bytes)/1024/1024:.2f}MB -> {output.tell()/1024/1024:.2f}MB (quality={quality})")
                    return output.getvalue()
                
                quality -= 10
            
            # If quality reduction isn't enough, resize the image
            scale = 0.8
            while scale >= 0.3:
                new_size = (int(img.width * scale), int(img.height * scale))
                resized = img.resize(new_size, Image.Resampling.LANCZOS)
                
                output.seek(0)
                output.truncate()
                resized.save(output, format='JPEG', quality=70, optimize=True)
                
                if output.tell() <= MAX_IMAGE_SIZE_BYTES:
                    print(f"Image resized: {len(original_bytes)/1024/1024:.2f}MB -> {output.tell()/1024/1024:.2f}MB (scale={scale})")
                    return output.getvalue()
                
                scale -= 0.1
            
            # Last resort: aggressive resize
            new_size = (int(img.width * 0.25), int(img.height * 0.25))
            resized = img.resize(new_size, Image.Resampling.LANCZOS)
            output.seek(0)
            output.truncate()
            resized.save(output, format='JPEG', quality=60, optimize=True)
            print(f"Image aggressively resized: {len(original_bytes)/1024/1024:.2f}MB -> {output.tell()/1024/1024:.2f}MB")
            return output.getvalue()
            
        except ImportError:
            print("Pillow not installed. Cannot compress image.")
            return original_bytes
        except Exception as e:
            print(f"Image compression failed: {e}")
            return original_bytes

    def _deduplicate_name_parts(self, first_name: str, last_name: str) -> tuple[str, str]:
        """Remove duplicate words from first_name and last_name.
        
        E.g., if last_name contains words already in first_name, remove them.
        "FIGUEROA MICHAEL NICHOLAS FIGUEROA" becomes:
        first_name: "MICHAEL NICHOLAS"
        last_name: "FIGUEROA"
        
        Args:
            first_name: First name string
            last_name: Last name string
            
        Returns:
            Tuple of (cleaned_first_name, cleaned_last_name)
        """
        if not first_name or not last_name:
            return first_name, last_name
        
        first_words = set(w.upper().strip() for w in first_name.split() if w.strip())
        last_words = [w for w in last_name.split() if w.strip()]
        
        # Remove words from last_name that are already in first_name
        unique_last_words = [w for w in last_words if w.upper() not in first_words]
        
        # If all words were duplicates, keep the original
        if not unique_last_words:
            unique_last_words = last_words
        
        cleaned_last_name = " ".join(unique_last_words)
        return first_name, cleaned_last_name

    def _generate_full_name(self, first_name: str, last_name: str) -> str:
        """Generate full name by combining first and last name.
        
        Args:
            first_name: First name string
            last_name: Last name string
            
        Returns:
            Combined full name with duplicates removed
        """
        parts = []
        if first_name.strip():
            parts.append(first_name.strip())
        if last_name.strip():
            parts.append(last_name.strip())
        
        full_name = " ".join(parts)
        return full_name

    def _extract_name_from_raw_text(self, raw_text: str) -> str | None:
        """Extract the full name from raw document text.
        
        Looks for text that follows name field indicators.
        Handles multi-line cases where label and name are on separate lines.
        
        Args:
            raw_text: Raw text from document
            
        Returns:
            Extracted full name or None if not found
        """
        if not raw_text:
            return None
        
        lines = raw_text.split('\n')
        
        # Look for "Name:" or "Nom:" patterns and get the content
        for i, line in enumerate(lines):
            # Check if this line contains a name label
            label_found = None
            for label in ['Name /', 'Nom /', 'Name :', 'Nom :']:
                if label in line:
                    label_found = label
                    break
            
            if label_found:
                # Try to extract name from this line first
                parts = line.split(label_found, 1)
                if len(parts) > 1:
                    name_part = parts[1].strip()
                    # If we got something substantial on this line, use it
                    if name_part and len(name_part) > 3:
                        # Clean up - remove extra whitespace, control chars
                        name = ' '.join(name_part.split())
                        return name
                
                # If nothing on this line, check the next non-empty line
                for j in range(i + 1, min(i + 3, len(lines))):
                    next_line = lines[j].strip()
                    # Skip empty lines and lines that are just labels/metadata
                    if next_line and not any(
                        x in next_line.lower() for x in ['date', 'nationality', 'doc #', 'expir', 'lieu']
                    ):
                        # This looks like a name line
                        # Names are typically all-caps or title case with multiple words
                        if len(next_line) > 3:
                            name = ' '.join(next_line.split())
                            # Verify it looks like a name (should have space or be long)
                            if ' ' in name or len(name) > 15:
                                return name
        
        return None

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
            # Compress image if needed (Azure limit is 4MB for images)
            document_bytes = self._compress_image(file_path)
            
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
                "is_id_document": True,  # This is an ID document
            }

            if result.documents:
                doc = result.documents[0]
                fields = doc.fields

                # Extract structured fields from Azure
                # Try both value_string and content - they may differ!
                first_name = ""
                last_name = ""
                
                if "FirstName" in fields:
                    # Try content first (raw OCR), then value_string (interpreted)
                    first_name = fields["FirstName"].content or fields["FirstName"].value_string or ""
                if "LastName" in fields:
                    # Try content first (raw OCR), then value_string (interpreted)
                    last_name = fields["LastName"].content or fields["LastName"].value_string or ""
                
                # Generate full_name by concatenating both parts
                # For 4-word names like "ASHLEY CHRISTY ERIKA FERNANDEZ":
                # Using .content (raw OCR) should preserve original order
                extracted["first_name"] = first_name
                extracted["last_name"] = last_name
                extracted["full_name"] = self._generate_full_name(first_name, last_name)

                # Extract other fields from ID document
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
                    raw_doc_type = (fields["DocumentType"].value_string or fields["DocumentType"].content or "").lower()
                    # Normalize to our standard types
                    if "passport" in raw_doc_type:
                        extracted["document_type"] = "passport"
                    elif "driver" in raw_doc_type or "license" in raw_doc_type:
                        extracted["document_type"] = "driving_license"
                    elif "id" in raw_doc_type or "card" in raw_doc_type:
                        extracted["document_type"] = "id_card"
                    else:
                        extracted["document_type"] = "passport"  # Default to passport for ID documents
                
                # If DocumentType field was missing, default to passport
                # since this method is specifically for ID documents
                if not extracted["document_type"]:
                    extracted["document_type"] = "passport"

            # If no documents were returned at all, still default to passport
            if not extracted["document_type"]:
                extracted["document_type"] = "passport"

            # Return extracted data with full_name already populated
            # No need for deduplication since we're using structured fields

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
            # Compress image if needed (Azure limit is 4MB for images)
            document_bytes = self._compress_image(file_path)
            
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
                "is_id_document": False,  # This is an address document, not an ID
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
                        # Remove duplicate words from name parts
                        extracted["first_name"], extracted["last_name"] = self._deduplicate_name_parts(
                            extracted["first_name"], 
                            extracted["last_name"]
                        )
                        # Generate full name
                        extracted["full_name"] = self._generate_full_name(
                            extracted["first_name"], 
                            extracted["last_name"]
                        )
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
                    # Remove duplicate words from name parts
                    extracted["first_name"], extracted["last_name"] = self._deduplicate_name_parts(
                        extracted["first_name"], 
                        extracted["last_name"]
                    )
                    return extracted
                return {"error": "Could not extract address information from this document"}

            # Remove duplicate words from name parts before returning
            extracted["first_name"], extracted["last_name"] = self._deduplicate_name_parts(
                extracted["first_name"], 
                extracted["last_name"]
            )
            # Generate full name
            extracted["full_name"] = self._generate_full_name(
                extracted["first_name"], 
                extracted["last_name"]
            )
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
            # Compress image if needed (Azure limit is 4MB for images)
            document_bytes = self._compress_image(file_path)
            
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
                    
                    # Remove duplicate words from name parts before returning
                    extracted["first_name"], extracted["last_name"] = self._deduplicate_name_parts(
                        extracted["first_name"], 
                        extracted["last_name"]
                    )
                    # Generate full name
                    extracted["full_name"] = self._generate_full_name(
                        extracted["first_name"], 
                        extracted["last_name"]
                    )
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

            # Use structured fields - prefer .content (raw OCR) over .value_string (interpreted)
            # For 4-word names like "ASHLEY CHRISTY ERIKA FERNANDEZ":
            # Azure may reorder if using value_string, so prefer content
            first_name = ""
            last_name = ""
            
            if "FirstName" in fields:
                # Try content first (raw OCR), then value_string (interpreted)
                first_name = fields["FirstName"].content or fields["FirstName"].value_string or ""
            if "LastName" in fields:
                # Try content first (raw OCR), then value_string (interpreted)
                last_name = fields["LastName"].content or fields["LastName"].value_string or ""
            
            extracted["first_name"] = first_name
            extracted["last_name"] = last_name
            
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

        # Generate full name by concatenating first and last
        extracted["full_name"] = self._generate_full_name(
            extracted["first_name"], 
            extracted["last_name"]
        )

        return extracted
