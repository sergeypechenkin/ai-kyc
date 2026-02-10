import { useState, useRef, useCallback } from 'react';
import { Upload, X, FileText, Loader2, Check, AlertCircle, User, Calendar, MapPin, CreditCard } from 'lucide-react';

interface ExtractedData {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  nationality: string;
  address: string;
  document_number: string;
  expiry_date: string;
  document_type: string;
  error?: string;
}

interface DocumentUploadProps {
  onCustomerCreated?: (customerId: string, accountNumber: string) => void;
  variant?: 'employee' | 'customer';
}

type UploadStatus = 'idle' | 'uploading' | 'extracted' | 'creating' | 'success' | 'error';

export default function DocumentUpload({ onCustomerCreated, variant = 'employee' }: DocumentUploadProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [status, setStatus] = useState<UploadStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const [extractedData, setExtractedData] = useState<ExtractedData | null>(null);
  const [formData, setFormData] = useState({
    first_name: '',
    last_name: '',
    email: '',
    phone: '',
    address: '',
    date_of_birth: '',
    nationality: '',
    document_type: 'passport',
    document_number: '',
  });
  const [createdAccount, setCreatedAccount] = useState<{ customerId: string; accountNumber: string } | null>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);

  const resetState = () => {
    setStatus('idle');
    setError(null);
    setExtractedData(null);
    setCreatedAccount(null);
    setFormData({
      first_name: '',
      last_name: '',
      email: '',
      phone: '',
      address: '',
      date_of_birth: '',
      nationality: '',
      document_type: 'passport',
      document_number: '',
    });
  };

  const handleDragOver = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(true);
  }, []);

  const handleDragLeave = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
  }, []);

  const handleDrop = useCallback((e: React.DragEvent) => {
    e.preventDefault();
    setIsDragging(false);
    const files = e.dataTransfer.files;
    if (files.length > 0) {
      handleFileUpload(files[0]);
    }
  }, []);

  const handleFileSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFileUpload(files[0]);
    }
  };

  const handleFileUpload = async (file: File) => {
    // Validate file type
    const allowedTypes = ['application/pdf', 'image/jpeg', 'image/png', 'image/tiff'];
    if (!allowedTypes.includes(file.type)) {
      setError('Please upload a PDF or image file (JPEG, PNG, TIFF)');
      setStatus('error');
      return;
    }

    setStatus('uploading');
    setError(null);

    const formDataUpload = new FormData();
    formDataUpload.append('file', file);
    formDataUpload.append('doc_type', formData.document_type);

    try {
      const response = await fetch('/api/documents/upload', {
        method: 'POST',
        body: formDataUpload,
      });

      if (!response.ok) {
        throw new Error('Upload failed');
      }

      const result = await response.json();
      
      if (result.extracted_data) {
        setExtractedData(result.extracted_data);
        
        // Pre-fill form with extracted data
        setFormData(prev => ({
          ...prev,
          first_name: result.extracted_data.first_name || prev.first_name,
          last_name: result.extracted_data.last_name || prev.last_name,
          date_of_birth: result.extracted_data.date_of_birth || prev.date_of_birth,
          nationality: result.extracted_data.nationality || prev.nationality,
          address: result.extracted_data.address || prev.address,
          document_number: result.extracted_data.document_number || prev.document_number,
        }));
        
        setStatus('extracted');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Upload failed');
      setStatus('error');
    }
  };

  const handleCreateAccount = async () => {
    // Validate required fields
    if (!formData.first_name || !formData.last_name || !formData.email) {
      setError('Please fill in all required fields (First Name, Last Name, Email)');
      return;
    }

    setStatus('creating');
    setError(null);

    try {
      const response = await fetch('/api/documents/create-customer', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });

      const result = await response.json();

      if (!response.ok) {
        throw new Error(result.detail || 'Failed to create customer');
      }

      setCreatedAccount({
        customerId: result.customer_id,
        accountNumber: result.account_number,
      });
      setStatus('success');
      
      if (onCustomerCreated) {
        onCustomerCreated(result.customer_id, result.account_number);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create customer');
      setStatus('error');
    }
  };

  const handleInputChange = (field: string, value: string) => {
    setFormData(prev => ({ ...prev, [field]: value }));
  };

  // Dynamic styling based on variant
  const colors = variant === 'customer' ? {
    primary: 'bg-blue-600',
    primaryHover: 'hover:bg-blue-700',
    primaryLight: 'bg-blue-100',
    primaryText: 'text-blue-600',
    ring: 'focus:ring-blue-500',
    border: 'border-blue-500',
    bgLight: 'bg-blue-50',
  } : {
    primary: 'bg-green-600',
    primaryHover: 'hover:bg-green-700',
    primaryLight: 'bg-green-100',
    primaryText: 'text-green-600',
    ring: 'focus:ring-green-500',
    border: 'border-green-500',
    bgLight: 'bg-green-50',
  };

  const buttonLabel = variant === 'customer' ? 'Open Account' : 'New Customer';
  const headerTitle = variant === 'customer' ? 'Open a New Bank Account' : 'Create New Customer Account';

  if (!isOpen) {
    return (
      <button
        onClick={() => { setIsOpen(true); resetState(); }}
        className={`flex items-center gap-2 px-4 py-2 ${colors.primary} text-white rounded-lg ${colors.primaryHover} transition-colors`}
      >
        <Upload className="w-4 h-4" />
        {buttonLabel}
      </button>
    );
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col">
        {/* Header */}
        <div className={`flex items-center justify-between p-4 border-b ${colors.primary} text-white`}>
          <h2 className="text-lg font-semibold flex items-center gap-2">
            <User className="w-5 h-5" />
            {headerTitle}
          </h2>
          <button
            onClick={() => setIsOpen(false)}
            className={`p-1 ${colors.primaryHover.replace('hover:', '')} rounded-full transition-colors`}
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Content */}
        <div className="flex-1 overflow-y-auto p-6">
          {/* Success State */}
          {status === 'success' && createdAccount && (
            <div className="text-center py-8">
              <div className={`w-16 h-16 ${colors.primaryLight} rounded-full flex items-center justify-center mx-auto mb-4`}>
                <Check className={`w-8 h-8 ${colors.primaryText}`} />
              </div>
              <h3 className="text-xl font-semibold text-gray-800 mb-2">Account Created Successfully!</h3>
              <p className="text-gray-600 mb-4">
                {variant === 'customer' 
                  ? `Welcome ${formData.first_name}! Your account has been created.`
                  : `Customer ${formData.first_name} ${formData.last_name} has been registered.`
                }
              </p>
              <div className="bg-gray-50 rounded-lg p-4 inline-block text-left">
                <p className="text-sm text-gray-500">Customer ID</p>
                <p className="font-mono font-semibold text-gray-800">{createdAccount.customerId}</p>
                <p className="text-sm text-gray-500 mt-2">Account Number (IBAN)</p>
                <p className="font-mono font-semibold text-gray-800 text-sm">{createdAccount.accountNumber}</p>
              </div>
              <div className="mt-6">
                <button
                  onClick={() => { setIsOpen(false); resetState(); }}
                  className={`px-6 py-2 ${colors.primary} text-white rounded-lg ${colors.primaryHover} transition-colors`}
                >
                  Done
                </button>
              </div>
            </div>
          )}

          {/* Upload/Form State */}
          {status !== 'success' && (
            <>
              {/* Document Type Selection */}
              <div className="mb-4">
                <label className="block text-sm font-medium text-gray-700 mb-2">Document Type</label>
                <select
                  value={formData.document_type}
                  onChange={(e) => handleInputChange('document_type', e.target.value)}
                  className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                >
                  <option value="passport">Passport</option>
                  <option value="driving_license">Driver's License</option>
                  <option value="id_card">National ID Card</option>
                </select>
              </div>

              {/* Drop Zone */}
              <div
                onDragOver={handleDragOver}
                onDragLeave={handleDragLeave}
                onDrop={handleDrop}
                onClick={() => fileInputRef.current?.click()}
                className={`border-2 border-dashed rounded-xl p-8 text-center cursor-pointer transition-colors ${
                  isDragging
                    ? `${colors.border} ${colors.bgLight}`
                    : status === 'extracted'
                    ? `${colors.border} ${colors.bgLight}`
                    : `border-gray-300 hover:${colors.border} hover:bg-gray-50`
                }`}
              >
                <input
                  ref={fileInputRef}
                  type="file"
                  accept=".pdf,.jpg,.jpeg,.png,.tiff"
                  onChange={handleFileSelect}
                  className="hidden"
                />
                
                {status === 'uploading' ? (
                  <div className="flex flex-col items-center">
                    <Loader2 className={`w-12 h-12 ${colors.primaryText} animate-spin mb-3`} />
                    <p className="text-gray-600">Analyzing document...</p>
                    <p className="text-sm text-gray-400">Extracting information with AI</p>
                  </div>
                ) : status === 'extracted' ? (
                  <div className="flex flex-col items-center">
                    <div className={`w-12 h-12 ${colors.primaryLight} rounded-full flex items-center justify-center mb-3`}>
                      <Check className={`w-6 h-6 ${colors.primaryText}`} />
                    </div>
                    <p className={`${colors.primaryText} font-medium`}>Document processed!</p>
                    <p className="text-sm text-gray-500">Click to upload a different document</p>
                  </div>
                ) : (
                  <div className="flex flex-col items-center">
                    <Upload className="w-12 h-12 text-gray-400 mb-3" />
                    <p className="text-gray-600 font-medium">Drop ID document here</p>
                    <p className="text-sm text-gray-400">or click to browse</p>
                    <p className="text-xs text-gray-400 mt-2">Supports PDF, JPEG, PNG, TIFF</p>
                  </div>
                )}
              </div>

              {/* Error Message */}
              {error && (
                <div className="mt-4 p-3 bg-red-50 border border-red-200 rounded-lg flex items-center gap-2 text-red-700">
                  <AlertCircle className="w-5 h-5 flex-shrink-0" />
                  <p className="text-sm">{error}</p>
                </div>
              )}

              {/* Extraction Notice */}
              {extractedData?.error && (
                <div className="mt-4 p-3 bg-yellow-50 border border-yellow-200 rounded-lg flex items-start gap-2 text-yellow-700">
                  <AlertCircle className="w-5 h-5 flex-shrink-0 mt-0.5" />
                  <p className="text-sm">{extractedData.error}</p>
                </div>
              )}

              {/* Customer Information Form */}
              {(status === 'extracted' || status === 'creating' || status === 'error') && (
                <div className="mt-6 space-y-4">
                  <h3 className="font-medium text-gray-800 flex items-center gap-2">
                    <FileText className="w-4 h-4" />
                    Customer Information
                  </h3>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        First Name <span className="text-red-500">*</span>
                      </label>
                      <div className="relative">
                        <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
                        <input
                          type="text"
                          value={formData.first_name}
                          onChange={(e) => handleInputChange('first_name', e.target.value)}
                          className="w-full pl-10 pr-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                          placeholder="John"
                        />
                      </div>
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Last Name <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="text"
                        value={formData.last_name}
                        onChange={(e) => handleInputChange('last_name', e.target.value)}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                        placeholder="Smith"
                      />
                    </div>
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        Email <span className="text-red-500">*</span>
                      </label>
                      <input
                        type="email"
                        value={formData.email}
                        onChange={(e) => handleInputChange('email', e.target.value)}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                        placeholder="john.smith@email.com"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Phone</label>
                      <input
                        type="tel"
                        value={formData.phone}
                        onChange={(e) => handleInputChange('phone', e.target.value)}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                        placeholder="+353 87 123 4567"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      <MapPin className="inline w-4 h-4 mr-1" />
                      Address
                    </label>
                    <input
                      type="text"
                      value={formData.address}
                      onChange={(e) => handleInputChange('address', e.target.value)}
                      className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                      placeholder="123 Main Street, Dublin 2"
                    />
                  </div>

                  <div className="grid grid-cols-2 gap-4">
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">
                        <Calendar className="inline w-4 h-4 mr-1" />
                        Date of Birth
                      </label>
                      <input
                        type="date"
                        value={formData.date_of_birth}
                        onChange={(e) => handleInputChange('date_of_birth', e.target.value)}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                      />
                    </div>
                    <div>
                      <label className="block text-sm font-medium text-gray-700 mb-1">Nationality</label>
                      <input
                        type="text"
                        value={formData.nationality}
                        onChange={(e) => handleInputChange('nationality', e.target.value)}
                        className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                        placeholder="Irish"
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      <CreditCard className="inline w-4 h-4 mr-1" />
                      Document Number
                    </label>
                    <input
                      type="text"
                      value={formData.document_number}
                      onChange={(e) => handleInputChange('document_number', e.target.value)}
                      className="w-full px-3 py-2 border rounded-lg focus:ring-2 focus:ring-green-500 focus:border-green-500"
                      placeholder="P12345678"
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer */}
        {status !== 'success' && (
          <div className="p-4 border-t bg-gray-50 flex justify-end gap-3">
            <button
              onClick={() => setIsOpen(false)}
              className="px-4 py-2 text-gray-600 hover:text-gray-800 transition-colors"
            >
              Cancel
            </button>
            {(status === 'extracted' || status === 'error' || status === 'creating') && (
              <button
                onClick={handleCreateAccount}
                disabled={status === 'creating'}
                className={`px-6 py-2 ${colors.primary} text-white rounded-lg ${colors.primaryHover} disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors flex items-center gap-2`}
              >
                {status === 'creating' ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    Creating...
                  </>
                ) : (
                  <>
                    <Check className="w-4 h-4" />
                    {variant === 'customer' ? 'Submit Application' : 'Create Account'}
                  </>
                )}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
