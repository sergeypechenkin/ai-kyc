import { useState, useRef } from 'react';
import { Upload, Loader2, FileCheck, AlertCircle, RotateCcw, Check } from 'lucide-react';

interface ExtractedData {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  nationality: string;
  address: string;
  document_number: string;
  expiry_date: string;
  document_type: string;
  document_date?: string;  // Date of the document (for proof of address)
  is_valid_timeframe?: boolean;  // Whether document is within required timeframe
  validity_message?: string;  // Message about document validity
  error?: string;
}

interface InlineUploadProps {
  onUploadComplete: (data: ExtractedData, docType: string, confirmed: boolean) => void;
  docType?: 'passport' | 'driving_license' | 'id_card' | 'proof_of_address' | 'auto';
  label?: string;
}

export default function InlineUpload({ 
  onUploadComplete, 
  docType = 'auto',
  label
}: InlineUploadProps) {
  const [isUploading, setIsUploading] = useState(false);
  const [extractedData, setExtractedData] = useState<ExtractedData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Get contextual label based on document type
  const getLabel = () => {
    if (label) return label;
    switch (docType) {
      case 'passport': return 'Upload Passport';
      case 'driving_license': return "Upload Driver's License";
      case 'id_card': return 'Upload ID Card';
      case 'proof_of_address': return 'Upload Proof of Address';
      case 'auto': return 'Select File';
      default: return 'Upload Document';
    }
  };

  const handleFileSelect = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;

    const file = files[0];
    
    // Validate file type
    const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff'];
    if (!allowedTypes.includes(file.type)) {
      setError('Please upload a PDF or image file');
      return;
    }

    setIsUploading(true);
    setError(null);
    setExtractedData(null);

    const formData = new FormData();
    formData.append('file', file);
    formData.append('doc_type', docType);

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
        setExtractedData(result.extracted_data);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setIsUploading(false);
    }
  };

  const handleConfirm = () => {
    if (extractedData) {
      onUploadComplete(extractedData, docType, true);
    }
  };

  const handleRetry = () => {
    setExtractedData(null);
    setError(null);
    fileInputRef.current?.click();
  };

  // Show extracted data for confirmation
  if (extractedData && !extractedData.error) {
    const hasData = extractedData.first_name || extractedData.last_name || 
                    extractedData.date_of_birth || extractedData.address;
    
    return (
      <div className="bg-white border border-blue-200 rounded-lg p-3 space-y-3">
        <div className="flex items-center gap-2 text-blue-600">
          <FileCheck className="w-4 h-4" />
          <span className="text-sm font-medium">Document Analyzed</span>
        </div>
        
        {hasData ? (
          <>
            <div className="text-sm space-y-1 text-gray-700">
              {extractedData.first_name && (
                <p><span className="text-gray-500">Name:</span> {extractedData.first_name} {extractedData.last_name}</p>
              )}
              {extractedData.date_of_birth && (
                <p><span className="text-gray-500">DOB:</span> {extractedData.date_of_birth}</p>
              )}
              {extractedData.nationality && (
                <p><span className="text-gray-500">Nationality:</span> {extractedData.nationality}</p>
              )}
              {extractedData.address && (
                <p><span className="text-gray-500">Address:</span> {extractedData.address}</p>
              )}
              {extractedData.document_number && (
                <p><span className="text-gray-500">Doc #:</span> {extractedData.document_number}</p>
              )}
              {extractedData.document_date && (
                <p><span className="text-gray-500">Document Date:</span> {extractedData.document_date}</p>
              )}
            </div>
            
            {/* Show validity warning for proof of address */}
            {extractedData.validity_message && (
              <div className={`text-sm p-2 rounded ${
                extractedData.is_valid_timeframe 
                  ? 'bg-green-50 text-green-700 border border-green-200' 
                  : 'bg-amber-50 text-amber-700 border border-amber-200'
              }`}>
                {extractedData.is_valid_timeframe ? '✓' : '⚠️'} {extractedData.validity_message}
              </div>
            )}
            
            <p className="text-xs text-gray-500">Is this information correct?</p>
            
            <div className="flex gap-2">
              <button
                onClick={handleConfirm}
                disabled={!extractedData.is_valid_timeframe}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg transition-colors text-sm ${
                  extractedData.is_valid_timeframe 
                    ? 'bg-green-600 text-white hover:bg-green-700' 
                    : 'bg-gray-300 text-gray-500 cursor-not-allowed'
                }`}
              >
                <Check className="w-3 h-3" />
                Yes, correct
              </button>
              <button
                onClick={handleRetry}
                className="flex items-center gap-1 px-3 py-1.5 bg-gray-100 text-gray-700 rounded-lg hover:bg-gray-200 transition-colors text-sm"
              >
                <RotateCcw className="w-3 h-3" />
                Upload different
              </button>
            </div>
          </>
        ) : (
          <>
            <p className="text-sm text-amber-600">
              Could not extract information from this document. The image may be unclear or the document type may not match.
            </p>
            <div className="flex gap-2">
              <button
                onClick={handleRetry}
                className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
              >
                <RotateCcw className="w-3 h-3" />
                Try another photo
              </button>
            </div>
          </>
        )}
        
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.tiff"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>
    );
  }

  // Show error with extraction issue
  if (extractedData?.error) {
    return (
      <div className="bg-amber-50 border border-amber-200 rounded-lg p-3 space-y-2">
        <div className="flex items-center gap-2 text-amber-600">
          <AlertCircle className="w-4 h-4" />
          <span className="text-sm">{extractedData.error}</span>
        </div>
        <button
          onClick={handleRetry}
          className="flex items-center gap-1 px-3 py-1.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm"
        >
          <RotateCcw className="w-3 h-3" />
          Try again
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.tiff"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>
    );
  }

  if (error) {
    return (
      <div className="flex flex-col gap-2">
        <div className="inline-flex items-center gap-2 px-3 py-2 bg-red-100 text-red-700 rounded-lg text-sm">
          <AlertCircle className="w-4 h-4" />
          {error}
        </div>
        <button
          onClick={() => { setError(null); fileInputRef.current?.click(); }}
          className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm w-fit"
        >
          <RotateCcw className="w-4 h-4" />
          Try Again
        </button>
        <input
          ref={fileInputRef}
          type="file"
          accept=".pdf,.jpg,.jpeg,.png,.tiff"
          onChange={handleFileSelect}
          className="hidden"
        />
      </div>
    );
  }

  return (
    <div>
      <input
        ref={fileInputRef}
        type="file"
        accept=".pdf,.jpg,.jpeg,.png,.tiff"
        onChange={handleFileSelect}
        className="hidden"
      />
      <button
        onClick={() => fileInputRef.current?.click()}
        disabled={isUploading}
        className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:bg-blue-400 transition-colors text-sm"
      >
        {isUploading ? (
          <>
            <Loader2 className="w-4 h-4 animate-spin" />
            Analyzing...
          </>
        ) : (
          <>
            <Upload className="w-4 h-4" />
            {getLabel()}
          </>
        )}
      </button>
    </div>
  );
}
