import { useState, useRef, useCallback, useEffect } from 'react';
import { Upload, Loader2, AlertCircle, RotateCcw, ShieldAlert, CheckCircle2 } from 'lucide-react';

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
  sent?: boolean; // whether we already sent the document_event for this slot
}

interface InlineUploadProps {
  onUploadComplete: (data: ExtractedData, docType: string, confirmed: boolean, sessionId?: string) => void;
  docType?: 'passport' | 'driving_license' | 'id_card' | 'proof_of_address' | 'auto';
  label?: string;
  sessionId?: string;
}

// Step-by-step flow:
// 1. identity  – show identity upload zone only
// 2. address   – identity done, show address upload zone
// 3. additional – both primary docs done AND risk requires extra docs, show them one-by-one
// 4. complete  – all documents collected
type FlowStep = 'identity' | 'address' | 'additional' | 'complete';

export default function InlineUpload({ 
  onUploadComplete, 
  docType = 'auto',
  sessionId: propsSessionId = 'default'
}: InlineUploadProps) {
  // Session ID
  const [sessionId, setSessionId] = useState(propsSessionId === 'default' ? 
    `upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}` : 
    propsSessionId
  );

  // Primary document slots
  const [identityDoc, setIdentityDoc] = useState<DocumentSlot>({ isUploading: false, isDragging: false });
  const [addressDoc, setAddressDoc] = useState<DocumentSlot>({ isUploading: false, isDragging: false });

  // Additional documents (keyed by doc name)
  const [additionalDocs, setAdditionalDocs] = useState<Record<string, {
    file: File;
    extractedData?: ExtractedData;
    validation_messages?: string[];
    validation_errors?: string[];
    address?: string;
    sent?: boolean;
  } | null>>({});
  const [uploadingAdditional, setUploadingAdditional] = useState<Set<string>>(new Set());

  // Which additional doc the user is currently uploading (index into required_documents)
  const [currentAdditionalIdx, setCurrentAdditionalIdx] = useState(0);

  // Refs
  const identityInputRef = useRef<HTMLInputElement>(null);
  const addressInputRef = useRef<HTMLInputElement>(null);
  const additionalInputRefs = useRef<Record<string, HTMLInputElement | null>>({});

  // Derive risk assessment
  const riskAssessment = identityDoc.extractedData?.risk_assessment;
  const requiredAdditional = riskAssessment?.required_documents ?? [];
  const needsAdditionalDocs = requiredAdditional.length > 0;

  // Derive current flow step
  const flowStep: FlowStep = (() => {
    if (!identityDoc.extractedData || !identityDoc.sent) return 'identity';
    if (!addressDoc.extractedData || !addressDoc.sent) return 'address';
    if (needsAdditionalDocs && currentAdditionalIdx < requiredAdditional.length) return 'additional';
    return 'complete';
  })();

  // ──────────────────────────────────────────
  // Auto-send document_event when a doc finishes uploading
  // ──────────────────────────────────────────

  // Identity: auto-send once extractedData arrives
  useEffect(() => {
    if (identityDoc.extractedData && !identityDoc.sent && !identityDoc.extractedData.error && !identityDoc.extractedData.validation_errors?.length) {
      setIdentityDoc(prev => ({ ...prev, sent: true }));
      onUploadComplete(identityDoc.extractedData, identityDoc.extractedData.document_type || 'passport', true, sessionId);
    }
  }, [identityDoc.extractedData]);

  // Address: auto-send once extractedData arrives
  useEffect(() => {
    if (addressDoc.extractedData && !addressDoc.sent && !addressDoc.extractedData.error && !addressDoc.extractedData.validation_errors?.length) {
      setAddressDoc(prev => ({ ...prev, sent: true }));
      onUploadComplete(addressDoc.extractedData, 'proof_of_address', true, sessionId);
    }
  }, [addressDoc.extractedData]);

  // ──────────────────────────────────────────
  // Upload helpers
  // ──────────────────────────────────────────

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

    setSlot(prev => ({ ...prev, isUploading: true, error: undefined, isDragging: false, file, sent: false }));

    const formData = new FormData();
    formData.append('file', file);
    formData.append('doc_type', slotType === 'identity' ? 'passport' : 'proof_of_address');
    formData.append('session_id', sessionId);

    try {
      const response = await fetch('/api/documents/upload', { method: 'POST', body: formData });
      if (!response.ok) {
        let errorMessage = 'Upload failed';
        try { const ed = await response.json(); errorMessage = ed.detail || errorMessage; } catch { errorMessage = `Upload failed: ${response.status} ${response.statusText}`; }
        throw new Error(errorMessage);
      }
      const result = await response.json();
      if (result.extracted_data) {
        setSlot(prev => ({ ...prev, extractedData: result.extracted_data, isUploading: false }));
      } else {
        setSlot(prev => ({ ...prev, error: 'Could not extract document data', isUploading: false }));
      }
    } catch (err) {
      setSlot(prev => ({ ...prev, error: err instanceof Error ? err.message : 'Upload failed', isUploading: false }));
    }
  };

  // Additional doc upload — auto-sends document_event on success
  const handleAdditionalFileSelect = async (docName: string, file: File) => {
    const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff'];
    if (!allowedTypes.includes(file.type)) return;

    setUploadingAdditional(prev => new Set([...prev, docName]));

    const formData = new FormData();
    formData.append('file', file);
    formData.append('doc_type', docName);
    formData.append('session_id', sessionId);

    try {
      const response = await fetch('/api/documents/upload', { method: 'POST', body: formData });
      if (response.ok) {
        const result = await response.json();
        const resultData = result.extracted_data || {};
        setAdditionalDocs(prev => ({
          ...prev,
          [docName]: {
            file,
            extractedData: resultData,
            validation_messages: resultData.validation_messages || [],
            validation_errors: resultData.validation_errors || [],
            address: resultData.address || '',
            sent: true,
          }
        }));

        // Auto-send document_event for additional doc
        const syntheticData: ExtractedData = {
          first_name: resultData.first_name || '',
          last_name: resultData.last_name || '',
          date_of_birth: resultData.date_of_birth || '',
          nationality: resultData.nationality || '',
          address: resultData.address || '',
          document_number: resultData.document_number || '',
          expiry_date: resultData.expiry_date || '',
          document_type: docName,
          document_date: resultData.document_date || '',
          validation_messages: resultData.validation_messages || [],
          validation_errors: resultData.validation_errors || [],
        };
        onUploadComplete(syntheticData, docName, true, sessionId);

        // Advance to next additional doc
        setCurrentAdditionalIdx(prev => prev + 1);
      }
    } catch (err) {
      console.error('Additional document upload failed:', err);
    } finally {
      setUploadingAdditional(prev => { const n = new Set(prev); n.delete(docName); return n; });
    }
  };

  // ──────────────────────────────────────────
  // Drag / file-select handlers
  // ──────────────────────────────────────────

  const handleIdentityDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIdentityDoc(prev => ({ ...prev, isDragging: true })); }, []);
  const handleIdentityDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setIdentityDoc(prev => ({ ...prev, isDragging: false })); }, []);
  const handleIdentityDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); const f = e.dataTransfer.files; if (f.length > 0) processFile(f[0], 'identity', setIdentityDoc); }, [sessionId]);

  const handleAddressDragOver = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setAddressDoc(prev => ({ ...prev, isDragging: true })); }, []);
  const handleAddressDragLeave = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); setAddressDoc(prev => ({ ...prev, isDragging: false })); }, []);
  const handleAddressDrop = useCallback((e: React.DragEvent) => { e.preventDefault(); e.stopPropagation(); const f = e.dataTransfer.files; if (f.length > 0) processFile(f[0], 'address', setAddressDoc); }, [sessionId]);

  const handleIdentityFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => { const f = e.target.files?.[0]; if (f) processFile(f, 'identity', setIdentityDoc); e.target.value = ''; };
  const handleAddressFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => { const f = e.target.files?.[0]; if (f) processFile(f, 'address', setAddressDoc); e.target.value = ''; };

  // ──────────────────────────────────────────
  // Reset
  // ──────────────────────────────────────────

  const resetAll = async () => {
    try { await fetch(`/api/documents/clear-session?session_id=${encodeURIComponent(sessionId)}`, { method: 'POST' }); } catch {}
    setIdentityDoc({ isUploading: false, isDragging: false });
    setAddressDoc({ isUploading: false, isDragging: false });
    setAdditionalDocs({});
    setCurrentAdditionalIdx(0);
    setSessionId(`upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  };

  const resetIdentity = () => {
    setIdentityDoc({ isUploading: false, isDragging: false });
    setAddressDoc({ isUploading: false, isDragging: false });
    setAdditionalDocs({});
    setCurrentAdditionalIdx(0);
    setSessionId(`upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  };

  const resetAddress = () => {
    setAddressDoc({ isUploading: false, isDragging: false });
    setAdditionalDocs({});
    setCurrentAdditionalIdx(0);
    setSessionId(`upload-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`);
  };

  // ──────────────────────────────────────────
  // Render helpers
  // ──────────────────────────────────────────

  // Active upload drop zone
  const renderUploadZone = (
    slot: DocumentSlot,
    title: string,
    subtitle: string,
    inputRef: React.RefObject<HTMLInputElement>,
    onDragOver: (e: React.DragEvent) => void,
    onDragLeave: (e: React.DragEvent) => void,
    onDrop: (e: React.DragEvent) => void,
    onFileSelect: (e: React.ChangeEvent<HTMLInputElement>) => void,
    onReset: () => void
  ) => {
    // Uploaded with errors → let user retry
    if (slot.error) {
      return (
        <div className="border border-red-300 rounded-lg p-3 bg-red-50">
          <div className="flex items-center gap-2 text-red-600 mb-2">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm">{slot.error}</span>
          </div>
          <button onClick={onReset} className="text-xs px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700 transition-colors">Try Again</button>
          <input ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.tiff" onChange={onFileSelect} className="hidden" />
        </div>
      );
    }

    // Uploaded with validation errors → show summary + retry
    if (slot.extractedData && slot.extractedData.validation_errors?.length) {
      return (
        <div className="border border-red-300 rounded-lg p-3 bg-red-50">
          <div className="flex items-center gap-2 text-red-600 mb-1">
            <AlertCircle className="w-4 h-4" />
            <span className="text-sm font-medium">{title}</span>
          </div>
          {slot.extractedData.validation_errors.map((err, i) => (
            <p key={i} className="text-xs text-red-600 ml-6">{err}</p>
          ))}
          <button onClick={onReset} className="mt-2 text-xs px-2 py-1 bg-red-600 text-white rounded hover:bg-red-700 transition-colors">Re-upload</button>
        </div>
      );
    }

    // Uploading / drop zone
    return (
      <div
        onDragOver={onDragOver}
        onDragLeave={onDragLeave}
        onDrop={onDrop}
        onClick={() => !slot.isUploading && inputRef.current?.click()}
        className={`border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors ${
          slot.isDragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 hover:border-blue-400 hover:bg-gray-50'
        }`}
      >
        <input ref={inputRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.tiff" onChange={onFileSelect} className="hidden" />
        {slot.isUploading ? (
          <div className="flex flex-col items-center py-2">
            <Loader2 className="w-6 h-6 text-blue-600 animate-spin mb-2" />
            <p className="text-xs text-gray-600">Analyzing document...</p>
          </div>
        ) : (
          <div className="flex flex-col items-center py-2">
            <Upload className={`w-6 h-6 mb-2 ${slot.isDragging ? 'text-blue-600' : 'text-gray-400'}`} />
            <p className={`text-sm font-medium ${slot.isDragging ? 'text-blue-600' : 'text-gray-600'}`}>{title}</p>
            <p className="text-xs text-gray-400 mt-1">{subtitle}</p>
            <p className="text-xs text-gray-400 mt-2">Drop file or click</p>
          </div>
        )}
      </div>
    );
  };

  // ──────────────────────────────────────────
  // Progress indicator
  // ──────────────────────────────────────────
  const totalSteps = 2 + requiredAdditional.length; // identity + address + additional docs
  const completedSteps = (identityDoc.sent ? 1 : 0) + (addressDoc.sent ? 1 : 0) +
    requiredAdditional.filter((_, i) => i < currentAdditionalIdx).length;

  // Build a compact list of completed step labels
  const completedLabels: string[] = [];
  if (identityDoc.sent) completedLabels.push('Identity');
  if (addressDoc.sent) completedLabels.push('Address');
  requiredAdditional.forEach((docName, i) => {
    if (i < currentAdditionalIdx && additionalDocs[docName]) completedLabels.push(docName);
  });

  // ──────────────────────────────────────────
  // MAIN RENDER — only current step + compact completed list
  // ──────────────────────────────────────────
  return (
    <div className="space-y-2">
      {/* Progress bar + compact completed steps */}
      <div className="flex items-center gap-2 text-xs text-gray-500">
        <span className="whitespace-nowrap">Step {Math.min(completedSteps + 1, totalSteps)}/{totalSteps}</span>
        <div className="flex-1 h-1.5 bg-gray-200 rounded-full overflow-hidden">
          <div className="h-full bg-blue-500 rounded-full transition-all duration-300" style={{ width: `${(completedSteps / totalSteps) * 100}%` }} />
        </div>
        {completedSteps === totalSteps && <CheckCircle2 className="w-4 h-4 text-green-600" />}
      </div>

      {/* Compact completed-steps summary (one line with checkmarks) */}
      {completedLabels.length > 0 && flowStep !== 'complete' && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-green-700">
          {completedLabels.map((label, i) => (
            <span key={i} className="flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" />
              {label}
            </span>
          ))}
          {riskAssessment && (
            <span className={`flex items-center gap-1 font-medium ${
              riskAssessment.risk_tier === 'high' ? 'text-red-600' : riskAssessment.risk_tier === 'medium' ? 'text-amber-600' : 'text-green-600'
            }`}>
              <ShieldAlert className="w-3 h-3" />
              {riskAssessment.risk_tier.toUpperCase()} ({riskAssessment.risk_score})
            </span>
          )}
        </div>
      )}

      {/* ── STEP 1: Identity ── */}
      {flowStep === 'identity' && (
        <div>
          <p className="text-sm font-medium text-gray-700 mb-2">Upload Proof of Identity</p>
          {renderUploadZone(
            identityDoc, 'Proof of Identity', 'Passport, ID Card, or License',
            identityInputRef,
            handleIdentityDragOver, handleIdentityDragLeave, handleIdentityDrop,
            handleIdentityFileSelect, resetIdentity
          )}
        </div>
      )}

      {/* ── STEP 2: Address ── */}
      {flowStep === 'address' && (
        <div>
          <p className="text-sm font-medium text-gray-700 mb-2">Upload Proof of Address</p>
          {renderUploadZone(
            addressDoc, 'Proof of Address', 'Utility Bill, Bank Statement',
            addressInputRef,
            handleAddressDragOver, handleAddressDragLeave, handleAddressDrop,
            handleAddressFileSelect, resetAddress
          )}
        </div>
      )}

      {/* ── STEP 3+: Additional Documents (current one only) ── */}
      {flowStep === 'additional' && currentAdditionalIdx < requiredAdditional.length && (() => {
        const docName = requiredAdditional[currentAdditionalIdx];
        return (
          <div>
            <p className="text-sm font-medium text-gray-700 mb-2">Upload {docName}</p>
            <input
              ref={(el) => { additionalInputRefs.current[docName] = el; }}
              type="file"
              accept=".pdf,.jpg,.jpeg,.png,.tiff"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) handleAdditionalFileSelect(docName, f); e.target.value = ''; }}
              className="hidden"
            />
            <div
              onDragOver={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.classList.add('border-blue-400', 'bg-blue-50'); }}
              onDragLeave={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.classList.remove('border-blue-400', 'bg-blue-50'); }}
              onDrop={(e) => { e.preventDefault(); e.stopPropagation(); e.currentTarget.classList.remove('border-blue-400', 'bg-blue-50'); const f = e.dataTransfer.files[0]; if (f) handleAdditionalFileSelect(docName, f); }}
              onClick={() => additionalInputRefs.current[docName]?.click()}
              className="border-2 border-dashed rounded-lg p-4 text-center cursor-pointer transition-colors border-gray-300 hover:border-blue-400 hover:bg-gray-50"
            >
              {uploadingAdditional.has(docName) ? (
                <div className="flex flex-col items-center py-2">
                  <Loader2 className="w-6 h-6 text-blue-600 animate-spin mb-2" />
                  <p className="text-xs text-gray-600">Uploading...</p>
                </div>
              ) : (
                <div className="flex flex-col items-center py-2">
                  <Upload className="w-6 h-6 mb-2 text-gray-400" />
                  <p className="text-sm font-medium text-gray-600">{docName}</p>
                  <p className="text-xs text-gray-400 mt-1">PDF, JPEG, PNG, or TIFF</p>
                  <p className="text-xs text-gray-400 mt-2">Drop file or click</p>
                </div>
              )}
            </div>
          </div>
        );
      })()}

      {/* ── Complete ── */}
      {flowStep === 'complete' && (
        <div className="p-3 rounded-lg bg-green-50 border border-green-300">
          <div className="flex items-center gap-2 text-green-700 font-medium text-sm">
            <CheckCircle2 className="w-4 h-4" />
            All {totalSteps} documents uploaded
          </div>
          <p className="text-xs text-green-600 mt-1">Check the chat for next steps.</p>
          <button onClick={resetAll} className="mt-2 flex items-center gap-1 px-2 py-1 text-xs bg-gray-100 text-gray-600 rounded hover:bg-gray-200 transition-colors">
            <RotateCcw className="w-3 h-3" /> Start Over
          </button>
        </div>
      )}
    </div>
  );
}
