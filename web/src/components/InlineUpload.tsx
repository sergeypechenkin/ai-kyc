import { useState, useRef, useMemo, useCallback } from 'react';
import { Upload, Loader2, AlertCircle, RotateCcw, Check, AlertTriangle, ShieldAlert, FileWarning, CheckCircle2, X } from 'lucide-react';

interface RiskAssessment {
  risk_score: number;
  risk_tier: 'low' | 'medium' | 'high';
  is_pep: boolean;
  required_documents: string[];
  proof_of_funds_months: number;
  approval_workflow: 'auto_approve' | 'employee_review' | 'compliance_escalation';
  alerts: string[];
}

interface ExtractedData {
  full_name?: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  nationality: string;
  address: string;
  document_number: string;
  expiry_date: string;
  document_type: string;
  document_date?: string;
  is_valid_timeframe?: boolean;
  validity_message?: string;
  validation_errors?: string[];
  validation_warnings?: string[];
  validation_messages?: string[];
  mismatch_with_primary?: boolean;
  risk_assessment?: RiskAssessment;
  error?: string;
}

interface DocumentSlot {
  file?: File;
  extractedData?: ExtractedData;
  isUploading: boolean;
  isDragging: boolean;
  error?: string;
}

interface InlineUploadProps {
  onUploadComplete: (data: ExtractedData, docType: string, confirmed: boolean) => void;
  docType?: 'passport' | 'driving_license' | 'id_card' | 'proof_of_address' | 'auto';
  label?: string;
  sessionId?: string;
}

export default function InlineUpload({ 
  onUploadComplete, 
  docType = 'auto',
  sessionId: propsSessionId = 'default'
}: InlineUploadProps) {
  // Generate unique session ID to isolate document validation across resets
  const [sessionId, setSessionId] = useState(propsSessionId === 'default' ? 
    `upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}` : 
    propsSessionId
  );
  // Primary document slots - Proof of Identity and Proof of Address
  const [identityDoc, setIdentityDoc] = useState<DocumentSlot>({ isUploading: false, isDragging: false });
  const [addressDoc, setAddressDoc] = useState<DocumentSlot>({ isUploading: false, isDragging: false });
  
  // Additional documents required after risk assessment
  const [additionalDocs, setAdditionalDocs] = useState<Record<string, {
    file: File;
    validation_messages?: string[];
    validation_errors?: string[];
    address?: string;
  } | null>>({});
  const [uploadingAdditional, setUploadingAdditional] = useState<Set<string>>(new Set());
  
  // Refs for file inputs
  const identityInputRef = useRef<HTMLInputElement>(null);
  const addressInputRef = useRef<HTMLInputElement>(null);
  const additionalInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  // Combined data state - track if user confirmed the submission
  const [, setIsConfirmed] = useState(false);

  // Process file upload for a specific slot
  const processFile = async (
    file: File, 
    slotType: 'identity' | 'address',
    setSlot: React.Dispatch<React.SetStateAction<DocumentSlot>>
  ) => {
    const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff'];
    if (!allowedTypes.includes(file.type)) {
      setSlot(prev => ({ ...prev, error: 'Please upload a PDF or image file', isDragging: false }));
      return;
    }

    setSlot(prev => ({ ...prev, isUploading: true, error: undefined, isDragging: false, file }));

    const formData = new FormData();
    formData.append('file', file);
    formData.append('doc_type', slotType === 'identity' ? 'passport' : 'proof_of_address');
    formData.append('session_id', sessionId);

    try {
      const response = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
      });

      if (!response.ok) {
        throw new Error('Upload failed');
      }

      const result = await response.json();
      
      if (result.extracted_data) {
        setSlot(prev => ({ 
          ...prev, 
          extractedData: result.extracted_data,
          isUploading: false 
        }));
      } else {
        setSlot(prev => ({ 
          ...prev, 
          error: 'Could not extract document data',
          isUploading: false 
        }));
      }
    } catch (err) {
      setSlot(prev => ({ 
        ...prev, 
        error: err instanceof Error ? err.message : 'Upload failed',
        isUploading: false 
      }));
    }
  };

  // Drag handlers for identity slot
  const handleIdentityDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIdentityDoc(prev => ({ ...prev, isDragging: true }));
  }, []);

  const handleIdentityDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setIdentityDoc(prev => ({ ...prev, isDragging: false }));
  }, []);

  const handleIdentityDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      processFile(files[0], 'identity', setIdentityDoc);
    }
  }, [sessionId]);

  // Drag handlers for address slot
  const handleAddressDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setAddressDoc(prev => ({ ...prev, isDragging: true }));
  }, []);

  const handleAddressDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    setAddressDoc(prev => ({ ...prev, isDragging: false }));
  }, []);

  const handleAddressDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    e.stopPropagation();
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      processFile(files[0], 'address', setAddressDoc);
    }
  }, [sessionId]);

  // File select handlers
  const handleIdentityFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file, 'identity', setIdentityDoc);
    }
    e.target.value = '';
  };

  const handleAddressFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (file) {
      processFile(file, 'address', setAddressDoc);
    }
    e.target.value = '';
  };

  // Reset handlers
  const resetIdentity = () => {
    setIdentityDoc({ isUploading: false, isDragging: false });
    setAdditionalDocs({});
    // Generate new session ID so next passport upload is validated independently
    setSessionId(`upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  };

  const resetAddress = () => {
    setAddressDoc({ isUploading: false, isDragging: false });
    // Generate new session ID so next address document upload is validated independently
    setSessionId(`upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  };

  const resetAll = async () => {
    try {
      await fetch(`/api/documents/clear-session?session_id=${encodeURIComponent(sessionId)}`, {
        method: 'POST',
      });
    } catch (err) {
      console.error('Failed to clear session:', err);
    }
    setIdentityDoc({ isUploading: false, isDragging: false });
    setAddressDoc({ isUploading: false, isDragging: false });
    setAdditionalDocs({});
    setIsConfirmed(false);
    // Generate new session ID for fresh document validation
    setSessionId(`upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  };

  // Handle additional document upload
  const handleAdditionalFileSelect = async (docName: string, file: File) => {
    const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff'];
    if (!allowedTypes.includes(file.type)) return;

    setUploadingAdditional(prev => new Set([...prev, docName]));
    
    const formData = new FormData();
    formData.append('file', file);
    formData.append('doc_type', docName);
    formData.append('session_id', sessionId);

    try {
      const response = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formData,
      });

      if (response.ok) {
        const result = await response.json();
        const resultData = result.extracted_data || {};
        setAdditionalDocs(prev => ({ 
          ...prev, 
          [docName]: {
            file,
            validation_messages: resultData.validation_messages || [],
            validation_errors: resultData.validation_errors || [],
            address: resultData.address || '',
          }
        }));
      }
    } catch (err) {
      console.error('Additional document upload failed:', err);
    } finally {
      setUploadingAdditional(prev => {
        const next = new Set(prev);
        next.delete(docName);
        return next;
      });
    }
  };

  // Computed values
  const bothDocumentsUploaded = identityDoc.extractedData && addressDoc.extractedData;
  const hasIdentityErrors = identityDoc.extractedData?.validation_errors?.length;
  const hasAddressErrors = addressDoc.extractedData?.validation_errors?.length;
  const hasAnyErrors = hasIdentityErrors || hasAddressErrors;
  
  // Get risk assessment from identity document (primary)
  const riskAssessment = identityDoc.extractedData?.risk_assessment;
  
  // Check if all required additional documents are uploaded
  const allAdditionalDocsUploaded = useMemo(() => {
    if (!riskAssessment?.required_documents?.length) return true;
    return riskAssessment.required_documents.every(doc => additionalDocs[doc] !== undefined);
  }, [riskAssessment, additionalDocs]);

  // Handle confirmation - submit for compliance review if high risk
  const handleConfirm = async () => {
    if (!identityDoc.extractedData) return;

    // Merge address from proof of address document if identity doc doesn't have one
    const data = {
      ...identityDoc.extractedData,
      address: identityDoc.extractedData.address || addressDoc.extractedData?.address || '',
    };
    
    if (data.risk_assessment?.risk_tier === 'high' || 
        data.risk_assessment?.approval_workflow === 'compliance_escalation') {
      try {
        const customerName = `${data.first_name} ${data.last_name}`.trim();
        
        await fetch('/api/compliance/submit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            session_id: sessionId,
            customer_name: customerName,
            first_name: data.first_name || '',
            last_name: data.last_name || '',
            date_of_birth: data.date_of_birth || '',
            nationality: data.nationality || '',
            address: data.address,
            document_number: data.document_number || '',
            risk_tier: data.risk_assessment?.risk_tier || 'high',
            risk_score: data.risk_assessment?.risk_score || 0,
            alerts: data.risk_assessment?.alerts || [],
          }),
        });
        console.log('[INFO] Submitted for compliance review');
      } catch (err) {
        console.error('Failed to submit for compliance review:', err);
      }
    }
    
    setIsConfirmed(true);
    onUploadComplete(data, docType, true);
  };

  // Render a document drop zone
  const renderDropZone = (
    slot: DocumentSlot,
    _slotType: 'identity' | 'address',
    title: string,
    subtitle: string,
    inputRef: React.RefObject<HTMLInputElement>,
    onDragOver: (e: React.DragEvent) => void,
    onDragLeave: (e: React.DragEvent) => void,
    onDrop: (e: React.DragEvent) => void,
    onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void,
    onReset: () => void
  ) => {
    // Show uploaded state
    if (slot.extractedData && !slot.extractedData.error) {
      const data = slot.extractedData;
      const hasErrors = data.validation_errors?.length;
      
      return (
        <div className={`flex-1 border rounded-lg p-3 ${
          hasErrors ? 'border-red-300 bg-red-50' : 'border-green-300 bg-green-50'
        }`}>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              {hasErrors ? (
                <AlertCircle className="w-4 h-4 text-red-600" />
              ) : (
                <CheckCircle2 className="w-4 h-4 text-green-600" />
              )}
              <span className={`text-sm font-medium ${hasErrors ? 'text-red-700' : 'text-green-700'}`}>
                {title}
              </span>
            </div>
            <button
              onClick={onReset}
              className="p-1 hover:bg-gray-200 rounded transition-colors"
              title="Upload different document"
            >
              <X className="w-4 h-4 text-gray-500" />
            </button>
          </div>
          
          <div className="text-xs space-y-0.5 text-gray-600">
            <p><span className="text-gray-400">Name:</span> {(data.full_name || (data.first_name || data.last_name)) ? (data.full_name || `${data.first_name} ${data.last_name}`.trim()) : '(not extracted)'}</p>
            {data.date_of_birth && (
              <p><span className="text-gray-400">DOB:</span> {data.date_of_birth}</p>
            )}
            {data.nationality && (
              <p><span className="text-gray-400">Nationality:</span> {data.nationality}</p>
            )}
            {data.address && (
              <p><span className="text-gray-400">Address:</span> {data.address}</p>
            )}
            {data.document_number && (
              <p><span className="text-gray-400">Doc #:</span> {data.document_number}</p>
            )}
            {data.document_date && (
              <p><span className="text-gray-400">Date:</span> {data.document_date}</p>
            )}
          </div>
          
          {/* Validation messages */}
          {data.validation_messages && data.validation_messages.length > 0 && (
            <div className="mt-2 space-y-0.5">
              {data.validation_messages.map((msg, idx) => (
                <div key={idx} className="text-xs text-green-600 flex items-start gap-1">
                  <CheckCircle2 className="w-3 h-3 mt-0.5 flex-shrink-0" />
                  <span>{msg}</span>
                </div>
              ))}
            </div>
          )}
          
          {/* Validation errors */}
          {data.validation_errors && data.validation_errors.length > 0 && (
            <div className="mt-2 space-y-0.5">
              {data.validation_errors.map((err, idx) => (
                <div key={idx} className="text-xs text-red-600 flex items-start gap-1">
                  <AlertCircle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                  <span>{err}</span>
                </div>
              ))}
            </div>
          )}
          
          {/* Validation warnings */}
          {data.validation_warnings && data.validation_warnings.length > 0 && (
            <div className="mt-2 space-y-0.5">
              {data.validation_warnings.map((warn, idx) => (
                <div key={idx} className="text-xs text-amber-600 flex items-start gap-1">
                  <AlertTriangle className="w-3 h-3 mt-0.5 flex-shrink-0" />
                  <span>{warn}</span>
                </div>
              ))}
            </div>
          )}
          
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.tiff"
            onChange={onFileSelect}
            className="hidden"
          />
        </div>
      );
    }

    // Show error state
    if (slot.error) {
      return (
        <div className="flex-1 border border-red-300 rounded-lg p-3 bg-red-50">
          <div className="flex items-center gap-2 text-red-600 mb-2">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm">{slot.error}</span>
          </div>
          <button
            onClick={onReset}
            className="text-xs px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700 transition-colors"
          >
            Try Again
          </button>
          <input
            ref={inputRef}
            type="file"
            accept=".pdf,.jpg,.jpeg,.png,.tiff"
            onChange={onFileSelect}
            className="hidden"
          />
        </div>
      );
    }

    // Show upload zone
    return (
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => !slot.isUploading && inputRef.current?.click()}
        className={`flex-1 border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
          slot.isDragging
            ? 'border-blue-500 bg-blue-50'
            : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'
        }`}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.tiff"
          onChange={onFileSelect}
          className="hidden"
        />
        
        {slot.isUploading ? (
          <div className="flex flex-col items-center py-2">
            <Loader2 className="w-6 h-6 text-blue-600 animate-spin mb-2" />
            <p className="text-xs text-gray-600">Analyzing...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center py-2">
            <Upload className={`w-6 h-6 mb-2 ${slot.isDragging ? 'text-blue-600' : 'text-gray-400'}`} />
            <p className={`text-sm font-medium ${slot.isDragging ? 'text-blue-600' : 'text-gray-600'}`}>
              {title}
            </p>
            <p className="text-xs text-gray-400 mt-1">{subtitle}</p>
            <p className="text-xs text-gray-400 mt-2">Drop file or click</p>
          </div>
        )}
      </div>
    );
  };

  // Render additional document slot
  const renderAdditionalDocSlot = (docName: string) => {
    if (additionalDocs[docName]) {
      const docData = additionalDocs[docName]!;
      const hasErrors = docData.validation_errors?.length;
      
      return (
        <div className={`p-2 rounded text-sm ${
          hasErrors ? 'bg-red-100 border border-red-200' : 'bg-green-100 border border-green-200'
        }`}>
          <div className="flex items-center gap-2">
            <CheckCircle2 className={`w-4 h-4 flex-shrink-0 ${hasErrors ? 'text-red-600' : 'text-green-600'}`} />
            <span className={`truncate font-medium ${hasErrors ? 'text-red-700' : 'text-green-700'}`}>
              {docData.file.name}
            </span>
          </div>
          {docData.validation_messages?.map((msg, i) => (
            <div key={i} className="ml-6 text-green-600 text-xs mt-1">{msg}</div>
          ))}
          {docData.validation_errors?.map((err, i) => (
            <div key={i} className="ml-6 text-red-600 text-xs mt-1 flex items-center gap-1">
              <AlertCircle className="w-3 h-3" /> {err}
            </div>
          ))}
        </div>
      );
    }

    return (
      <>
        <input
          ref={(el) => { additionalInputRefs.current[docName] = el; }}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.tiff"
          onChange={(e) => {
            const file = e.target.files?.[0];
            if (file) handleAdditionalFileSelect(docName, file);
            e.target.value = '';
          }}
          className="hidden"
        />
        <div
          onDragOver={(e) => {
            e.preventDefault();
            e.stopPropagation();
            e.currentTarget.classList.add('border-blue-400', 'bg-blue-50');
          }}
          onDragLeave={(e) => {
            e.preventDefault();
            e.stopPropagation();
            e.currentTarget.classList.remove('border-blue-400', 'bg-blue-50');
          }}
          onDrop={(e) => {
            e.preventDefault();
            e.stopPropagation();
            e.currentTarget.classList.remove('border-blue-400', 'bg-blue-50');
            const file = e.dataTransfer.files[0];
            if (file) handleAdditionalFileSelect(docName, file);
          }}
          onClick={() => additionalInputRefs.current[docName]?.click()}
          className="flex items-center justify-center gap-2 p-3 border-2 border-dashed border-gray-300 rounded hover:border-blue-400 hover:bg-blue-50 transition-colors text-sm text-gray-600 cursor-pointer"
        >
          {uploadingAdditional.has(docName) ? (
            <>
              <Loader2 className="w-4 h-4 animate-spin" />
              Uploading...
            </>
          ) : (
            <>
              <Upload className="w-4 h-4" />
              <span className="text-center">{docName}<br/><span className="text-xs text-gray-400">Click or drop file</span></span>
            </>
          )}
        </div>
      </>
    );
  };

  // Main render
  return (
    <div className="space-y-4">
      {/* Two primary document drop zones side by side */}
      <div className="flex gap-3">
        {renderDropZone(
          identityDoc,
          'identity',
          'Proof of Identity',
          'Passport, ID Card, or License',
          identityInputRef,
          handleIdentityDragOver,
          handleIdentityDragLeave,
          handleIdentityDrop,
          handleIdentityFileSelect,
          resetIdentity
        )}
        {renderDropZone(
          addressDoc,
          'address',
          'Proof of Address',
          'Utility Bill, Bank Statement',
          addressInputRef,
          handleAddressDragOver,
          handleAddressDragLeave,
          handleAddressDrop,
          handleAddressFileSelect,
          resetAddress
        )}
      </div>
      
      {/* Risk Assessment section - shown when identity doc is uploaded */}
      {identityDoc.extractedData?.risk_assessment && (
        <div className={`text-sm p-3 rounded border space-y-2 ${
          riskAssessment?.risk_tier === 'high'
            ? 'bg-red-50 border-red-300'
            : riskAssessment?.risk_tier === 'medium'
            ? 'bg-amber-50 border-amber-300'
            : 'bg-green-50 border-green-300'
        }`}>
          <div className="flex items-center gap-2 font-medium">
            <ShieldAlert className={`w-4 h-4 ${
              riskAssessment?.risk_tier === 'high' ? 'text-red-600' 
              : riskAssessment?.risk_tier === 'medium' ? 'text-amber-600' 
              : 'text-green-600'
            }`} />
            <span className={
              riskAssessment?.risk_tier === 'high' ? 'text-red-700' 
              : riskAssessment?.risk_tier === 'medium' ? 'text-amber-700' 
              : 'text-green-700'
            }>
              Risk Assessment: {riskAssessment?.risk_tier?.toUpperCase()} 
              ({riskAssessment?.risk_score}/100)
            </span>
          </div>
          
          {/* Alerts */}
          {riskAssessment?.alerts && riskAssessment.alerts.length > 0 && (
            <div className="space-y-1">
              {riskAssessment.alerts.map((alert, idx) => (
                <div key={idx} className={`text-sm ${
                  riskAssessment.risk_tier === 'high' ? 'text-red-700' : 'text-amber-700'
                }`}>
                  {alert}
                </div>
              ))}
            </div>
          )}
          
          {/* Workflow requirement */}
          <div className={`text-sm font-medium ${
            riskAssessment?.approval_workflow === 'compliance_escalation' 
              ? 'text-red-700' 
              : riskAssessment?.approval_workflow === 'employee_review'
              ? 'text-amber-700'
              : 'text-green-700'
          }`}>
            {riskAssessment?.approval_workflow === 'compliance_escalation' 
              ? '⛔ Requires Compliance Review'
              : riskAssessment?.approval_workflow === 'employee_review'
              ? '⏳ Requires Employee Approval'
              : '✅ Auto-Approve Eligible'}
          </div>
          
          {/* Required additional documents */}
          {riskAssessment?.required_documents && riskAssessment.required_documents.length > 0 && (
            <div className="mt-2 pt-2 border-t border-current/20">
              <div className="flex items-center gap-1 text-sm font-medium mb-2">
                <FileWarning className="w-4 h-4" />
                Additional Documents Required:
              </div>
              <div className="space-y-2">
                {riskAssessment.required_documents.map((doc, idx) => (
                  <div key={idx}>
                    {renderAdditionalDocSlot(doc)}
                  </div>
                ))}
              </div>
              {allAdditionalDocsUploaded && (
                <div className="mt-3 p-2 bg-green-100 text-green-700 rounded text-sm flex items-center gap-2">
                  <CheckCircle2 className="w-4 h-4" />
                  All required documents uploaded
                </div>
              )}
            </div>
          )}
        </div>
      )}
      
      {/* Submission section - shown when both docs uploaded and no critical errors */}
      {bothDocumentsUploaded && !hasAnyErrors && (
        <div className="border-t pt-3 mt-3">
          {riskAssessment?.required_documents?.length ? (
            allAdditionalDocsUploaded ? (
              <div className="space-y-2">
                <p className="text-sm text-gray-600">All documents verified. Ready to submit?</p>
                <div className="flex gap-2">
                  <button
                    onClick={handleConfirm}
                    className="flex-1 flex items-center justify-center gap-2 px-4 py-2.5 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors font-medium"
                  >
                    <Check className="w-4 h-4" />
                    {riskAssessment.approval_workflow === 'compliance_escalation' 
                      ? 'Submit for Compliance Review' 
                      : 'Confirm & Proceed'}
                  </button>
                  <button
                    onClick={resetAll}
                    className="flex items-center gap-2 px-4 py-2.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors"
                  >
                    <RotateCcw className="w-4 h-4" />
                    Start Over
                  </button>
                </div>
              </div>
            ) : (
              <p className="text-xs text-gray-500">Please upload all required additional documents above</p>
            )
          ) : (
            <div className="space-y-2">
              <p className="text-sm text-gray-600">Documents verified. Is this information correct?</p>
              <div className="flex gap-2">
                <button
                  onClick={handleConfirm}
                  className="flex items-center gap-2 px-4 py-2 bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors text-sm"
                >
                  <Check className="w-4 h-4" />
                  Yes, confirm
                </button>
                <button
                  onClick={resetAll}
                  className="flex items-center gap-2 px-4 py-2 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm"
                >
                  <RotateCcw className="w-4 h-4" />
                  Start over
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Missing documents state */}
      {(!identityDoc.extractedData || !addressDoc.extractedData) && (
        <div className="border-t pt-3 mt-3 bg-blue-50 border-blue-200 rounded-lg p-3 text-sm text-blue-700">
          <div className="space-y-2">
            <p className="font-medium flex items-center gap-2">
              <AlertCircle className="w-4 h-4" />
              Required Documents
            </p>
            <ul className="space-y-1 ml-6">
              <li className="flex items-center gap-2">
                {identityDoc.extractedData ? (
                  <> <Check className="w-4 h-4 text-green-600" /> Proof of Identity <span className="text-gray-500">(uploaded)</span> </>
                ) : (
                  <> <AlertCircle className="w-4 h-4 text-blue-600" /> Proof of Identity <span className="text-gray-500">(required)</span> </>
                )}
              </li>
              <li className="flex items-center gap-2">
                {addressDoc.extractedData ? (
                  <> <Check className="w-4 h-4 text-green-600" /> Proof of Address <span className="text-gray-500">(uploaded)</span> </>
                ) : (
                  <> <AlertCircle className="w-4 h-4 text-blue-600" /> Proof of Address <span className="text-gray-500">(required)</span> </>
                )}
              </li>
            </ul>
            <p className="text-xs text-blue-600 mt-2">Both documents are required to proceed with account opening.</p>
          </div>
        </div>
      )}
      
      {/* Error state - show when there are validation errors */}
      {bothDocumentsUploaded && hasAnyErrors && (
        <div className="border-t pt-3 mt-3">
          <div className="text-sm p-3 rounded bg-red-50 text-red-700 border border-red-200 space-y-2">
            <div className="font-medium flex items-center gap-1">
              <AlertCircle className="w-4 h-4" />
              Document Validation Issues
            </div>
            <p className="text-sm">Please fix the errors above by uploading corrected documents.</p>
            <button
              onClick={resetAll}
              className="w-full flex items-center justify-center gap-2 px-3 py-2 bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors text-sm font-medium"
            >
              <RotateCcw className="w-4 h-4" />
              Start Over with New Documents
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
