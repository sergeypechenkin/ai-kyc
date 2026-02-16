import { useState, useEffect } from 'react';
import { 
  FileCheck, 
  AlertTriangle, 
  ShieldAlert, 
  CheckCircle2, 
  XCircle, 
  ExternalLink,
  Loader2,
  FileText,
  User,
  MapPin,
  Calendar,
  Flag,
  Printer
} from 'lucide-react';

interface CustomerDocument {
  id: string;
  type: string;
  name: string;
  path: string;
  uploaded_at: string;
  verified: boolean;
}

interface RiskAssessment {
  risk_score: number;
  risk_tier: 'low' | 'medium' | 'high';
  is_pep: boolean;
  pep_details?: string;
  country_risk_reason?: string;
  required_documents: string[];
  approval_workflow: string;
  alerts: string[];
}

interface CustomerInfo {
  customer_id: string;
  first_name: string;
  last_name: string;
  date_of_birth: string;
  nationality: string;
  address: string;
  email: string;
  document_number?: string;
}

interface ComplianceReviewFormProps {
  customerId: string;
  onDecision: (decision: 'approved' | 'approved_with_conditions' | 'rejected', notes: string, reviewedDocs: string[]) => void;
  onClose: () => void;
}

export default function ComplianceReviewForm({ 
  customerId, 
  onDecision,
  onClose 
}: ComplianceReviewFormProps) {
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [customer, setCustomer] = useState<CustomerInfo | null>(null);
  const [documents, setDocuments] = useState<CustomerDocument[]>([]);
  const [riskAssessment, setRiskAssessment] = useState<RiskAssessment | null>(null);
  const [reviewedDocs, setReviewedDocs] = useState<Record<string, boolean>>({});
  const [decision, setDecision] = useState<'approved' | 'approved_with_conditions' | 'rejected' | null>(null);
  const [conditions, setConditions] = useState('');
  const [error, setError] = useState<string | null>(null);

  // Generate report ID
  const reportId = `CDR-${new Date().getFullYear()}-${String(new Date().getMonth() + 1).padStart(2, '0')}${String(new Date().getDate()).padStart(2, '0')}-${customerId}`;

  useEffect(() => {
    loadCustomerData();
  }, [customerId]);

  const loadCustomerData = async () => {
    setLoading(true);
    setError(null);
    try {
      // Load customer info
      const customerRes = await fetch(`/api/customers/${customerId}`);
      if (customerRes.ok) {
        const customerData = await customerRes.json();
        setCustomer(customerData);
      }

      // Load customer documents
      const docsRes = await fetch(`/api/customers/${customerId}/documents`);
      if (docsRes.ok) {
        const docsData = await docsRes.json();
        setDocuments(docsData.documents || []);
        // Initialize reviewed state
        const reviewed: Record<string, boolean> = {};
        (docsData.documents || []).forEach((doc: CustomerDocument) => {
          reviewed[doc.id] = false;
        });
        setReviewedDocs(reviewed);
      }

      // Load risk assessment
      const riskRes = await fetch(`/api/customers/${customerId}/risk-assessment`);
      if (riskRes.ok) {
        const riskData = await riskRes.json();
        setRiskAssessment(riskData);
      }
    } catch (err) {
      setError('Failed to load customer data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  const handleDocumentReview = (docId: string, checked: boolean) => {
    setReviewedDocs(prev => ({ ...prev, [docId]: checked }));
  };

  const allDocumentsReviewed = Object.values(reviewedDocs).every(v => v);
  const canSubmit = allDocumentsReviewed && decision !== null;

  const handleSubmit = async () => {
    if (!canSubmit) return;
    
    setSubmitting(true);
    const notes = decision === 'approved_with_conditions' 
      ? `Approved with conditions: ${conditions}`
      : decision === 'rejected'
      ? `Rejected: ${conditions}`
      : '';
    
    onDecision(decision!, notes, Object.keys(reviewedDocs));
    setSubmitting(false);
  };

  const handlePrint = () => {
    window.print();
  };

  const openDocument = (path: string) => {
    // Open document in new tab
    window.open(`/api/documents/view/${encodeURIComponent(path)}`, '_blank');
  };

  if (loading) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6 max-w-2xl mx-auto">
        <div className="flex items-center justify-center py-12">
          <Loader2 className="w-8 h-8 animate-spin text-blue-600" />
          <span className="ml-3 text-gray-600">Loading customer data...</span>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-white rounded-lg shadow-lg p-6 max-w-2xl mx-auto">
        <div className="text-center py-8">
          <XCircle className="w-12 h-12 text-red-500 mx-auto mb-4" />
          <p className="text-red-600">{error}</p>
          <button
            onClick={onClose}
            className="mt-4 px-4 py-2 bg-gray-200 rounded-lg hover:bg-gray-300"
          >
            Close
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="bg-white rounded-lg shadow-lg max-w-2xl mx-auto print:shadow-none print:max-w-none">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-800 to-blue-600 text-white p-4 rounded-t-lg print:rounded-none">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-xl font-bold">COMPLIANCE DECISION REPORT</h2>
            <p className="text-blue-200 text-sm">Zava Bank KYC Review</p>
          </div>
          <button
            onClick={handlePrint}
            className="p-2 bg-white/20 rounded-lg hover:bg-white/30 transition-colors print:hidden"
            title="Print Report"
          >
            <Printer className="w-5 h-5" />
          </button>
        </div>
      </div>

      <div className="p-4 space-y-4">
        {/* Report Info */}
        <div className="flex justify-between text-sm text-gray-600 border-b pb-3">
          <span><strong>Report ID:</strong> {reportId}</span>
          <span><strong>Date:</strong> {new Date().toLocaleString()}</span>
        </div>

        {/* Customer Information */}
        <div className="border rounded-lg p-3">
          <h3 className="font-semibold text-gray-800 flex items-center gap-2 mb-3">
            <User className="w-4 h-4" />
            Customer Information
          </h3>
          {customer ? (
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div><span className="text-gray-500">Name:</span> {customer.first_name} {customer.last_name}</div>
              <div><span className="text-gray-500">Customer ID:</span> {customer.customer_id}</div>
              <div className="flex items-center gap-1">
                <Calendar className="w-3 h-3 text-gray-400" />
                <span className="text-gray-500">DOB:</span> {customer.date_of_birth}
              </div>
              <div className="flex items-center gap-1">
                <Flag className="w-3 h-3 text-gray-400" />
                <span className="text-gray-500">Nationality:</span> {customer.nationality}
              </div>
              {customer.document_number && (
                <div><span className="text-gray-500">Doc #:</span> {customer.document_number}</div>
              )}
              {customer.email && (
                <div><span className="text-gray-500">Email:</span> {customer.email}</div>
              )}
              <div className="col-span-2 flex items-start gap-1">
                <MapPin className="w-3 h-3 text-gray-400 mt-0.5" />
                <span className="text-gray-500">Address:</span> {customer.address}
              </div>
            </div>
          ) : (
            <p className="text-gray-500 text-sm">Customer information not available</p>
          )}
        </div>

        {/* Risk Assessment */}
        {riskAssessment && (
          <div className={`border rounded-lg p-3 ${
            riskAssessment.risk_tier === 'high' ? 'border-red-300 bg-red-50' :
            riskAssessment.risk_tier === 'medium' ? 'border-amber-300 bg-amber-50' :
            'border-green-300 bg-green-50'
          }`}>
            <h3 className="font-semibold flex items-center gap-2 mb-3">
              <ShieldAlert className={`w-4 h-4 ${
                riskAssessment.risk_tier === 'high' ? 'text-red-600' :
                riskAssessment.risk_tier === 'medium' ? 'text-amber-600' :
                'text-green-600'
              }`} />
              Risk Assessment
            </h3>
            <div className="grid grid-cols-2 gap-2 text-sm">
              <div>
                <span className="text-gray-600">Risk Score:</span>{' '}
                <span className="font-bold">{riskAssessment.risk_score}/100</span>
              </div>
              <div>
                <span className="text-gray-600">Risk Tier:</span>{' '}
                <span className={`font-bold uppercase ${
                  riskAssessment.risk_tier === 'high' ? 'text-red-600' :
                  riskAssessment.risk_tier === 'medium' ? 'text-amber-600' :
                  'text-green-600'
                }`}>{riskAssessment.risk_tier}</span>
              </div>
              <div className="col-span-2">
                <span className="text-gray-600">PEP Status:</span>{' '}
                {riskAssessment.is_pep ? (
                  <span className="text-red-600 font-bold">YES - {riskAssessment.pep_details}</span>
                ) : (
                  <span className="text-green-600">NO</span>
                )}
              </div>
              {riskAssessment.country_risk_reason && (
                <div className="col-span-2">
                  <span className="text-gray-600">Country Risk:</span>{' '}
                  <span className="text-gray-800">{riskAssessment.country_risk_reason}</span>
                </div>
              )}
            </div>
            {riskAssessment.alerts.length > 0 && (
              <div className="mt-2 pt-2 border-t border-current/20 space-y-1">
                {riskAssessment.alerts.map((alert, idx) => (
                  <div key={idx} className="text-sm flex items-start gap-1">
                    <AlertTriangle className="w-4 h-4 flex-shrink-0 mt-0.5" />
                    {alert}
                  </div>
                ))}
              </div>
            )}
          </div>
        )}

        {/* Documents Review */}
        <div className="border rounded-lg p-3">
          <h3 className="font-semibold text-gray-800 flex items-center gap-2 mb-3">
            <FileText className="w-4 h-4" />
            Documents Review
          </h3>
          {documents.length > 0 ? (
            <div className="space-y-2">
              {documents.map((doc) => (
                <div 
                  key={doc.id} 
                  className={`flex items-center justify-between p-2 rounded border ${
                    reviewedDocs[doc.id] ? 'bg-green-50 border-green-200' : 'bg-gray-50 border-gray-200'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <input
                      type="checkbox"
                      id={`doc-${doc.id}`}
                      checked={reviewedDocs[doc.id] || false}
                      onChange={(e) => handleDocumentReview(doc.id, e.target.checked)}
                      className="w-5 h-5 rounded border-gray-300 text-green-600 focus:ring-green-500"
                    />
                    <label htmlFor={`doc-${doc.id}`} className="text-sm cursor-pointer">
                      <span className="font-medium">{doc.type}</span>
                      <span className="text-gray-500 ml-2">({doc.name})</span>
                    </label>
                  </div>
                  <button
                    onClick={() => openDocument(doc.path)}
                    className="flex items-center gap-1 text-sm text-blue-600 hover:text-blue-800 hover:underline"
                  >
                    <ExternalLink className="w-4 h-4" />
                    View
                  </button>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm">No documents uploaded</p>
          )}
          
          {!allDocumentsReviewed && documents.length > 0 && (
            <p className="mt-2 text-amber-600 text-sm flex items-center gap-1">
              <AlertTriangle className="w-4 h-4" />
              Please review all documents before making a decision
            </p>
          )}
        </div>

        {/* Decision Section */}
        <div className="border rounded-lg p-3">
          <h3 className="font-semibold text-gray-800 mb-3">Decision</h3>
          
          <div className="space-y-2">
            <label className={`flex items-center gap-3 p-3 rounded border cursor-pointer transition-colors ${
              decision === 'approved' ? 'bg-green-100 border-green-400' : 'hover:bg-gray-50'
            }`}>
              <input
                type="radio"
                name="decision"
                value="approved"
                checked={decision === 'approved'}
                onChange={() => setDecision('approved')}
                disabled={!allDocumentsReviewed}
                className="w-5 h-5 text-green-600"
              />
              <div className="flex items-center gap-2">
                <CheckCircle2 className="w-5 h-5 text-green-600" />
                <span className="font-medium">APPROVED</span>
              </div>
            </label>

            <label className={`flex items-center gap-3 p-3 rounded border cursor-pointer transition-colors ${
              decision === 'approved_with_conditions' ? 'bg-amber-100 border-amber-400' : 'hover:bg-gray-50'
            }`}>
              <input
                type="radio"
                name="decision"
                value="approved_with_conditions"
                checked={decision === 'approved_with_conditions'}
                onChange={() => setDecision('approved_with_conditions')}
                disabled={!allDocumentsReviewed}
                className="w-5 h-5 text-amber-600"
              />
              <div className="flex items-center gap-2">
                <AlertTriangle className="w-5 h-5 text-amber-600" />
                <span className="font-medium">APPROVED WITH CONDITIONS</span>
              </div>
            </label>

            <label className={`flex items-center gap-3 p-3 rounded border cursor-pointer transition-colors ${
              decision === 'rejected' ? 'bg-red-100 border-red-400' : 'hover:bg-gray-50'
            }`}>
              <input
                type="radio"
                name="decision"
                value="rejected"
                checked={decision === 'rejected'}
                onChange={() => setDecision('rejected')}
                disabled={!allDocumentsReviewed}
                className="w-5 h-5 text-red-600"
              />
              <div className="flex items-center gap-2">
                <XCircle className="w-5 h-5 text-red-600" />
                <span className="font-medium">REJECTED</span>
              </div>
            </label>
          </div>

          {(decision === 'approved_with_conditions' || decision === 'rejected') && (
            <div className="mt-3">
              <label className="block text-sm font-medium text-gray-700 mb-1">
                {decision === 'approved_with_conditions' ? 'Conditions:' : 'Rejection Reason:'}
              </label>
              <textarea
                value={conditions}
                onChange={(e) => setConditions(e.target.value)}
                placeholder={decision === 'approved_with_conditions' 
                  ? 'e.g., Enhanced monitoring required. Quarterly review scheduled.'
                  : 'Enter rejection reason...'
                }
                className="w-full p-2 border rounded-lg text-sm resize-none"
                rows={3}
              />
            </div>
          )}
        </div>

        {/* Signature Section (for print) */}
        <div className="border rounded-lg p-3 hidden print:block">
          <h3 className="font-semibold text-gray-800 mb-4">Signatures</h3>
          <div className="grid grid-cols-2 gap-8">
            <div>
              <p className="text-sm text-gray-600 mb-8">Reviewer:</p>
              <div className="border-b border-gray-400 mb-1"></div>
              <p className="text-xs text-gray-500">Name & Signature</p>
            </div>
            <div>
              <p className="text-sm text-gray-600 mb-8">Compliance Officer:</p>
              <div className="border-b border-gray-400 mb-1"></div>
              <p className="text-xs text-gray-500">Name & Signature</p>
            </div>
          </div>
          <div className="mt-4">
            <p className="text-sm text-gray-600">Date: _________________</p>
          </div>
        </div>

        {/* Action Buttons */}
        <div className="flex gap-3 pt-2 print:hidden">
          <button
            onClick={onClose}
            className="flex-1 px-4 py-2 border border-gray-300 rounded-lg text-gray-700 hover:bg-gray-50 transition-colors"
          >
            Cancel
          </button>
          <button
            onClick={handleSubmit}
            disabled={!canSubmit || submitting}
            className={`flex-1 px-4 py-2 rounded-lg font-medium transition-colors flex items-center justify-center gap-2 ${
              canSubmit
                ? decision === 'approved'
                  ? 'bg-green-600 text-white hover:bg-green-700'
                  : decision === 'approved_with_conditions'
                  ? 'bg-amber-600 text-white hover:bg-amber-700'
                  : 'bg-red-600 text-white hover:bg-red-700'
                : 'bg-gray-300 text-gray-500 cursor-not-allowed'
            }`}
          >
            {submitting ? (
              <>
                <Loader2 className="w-4 h-4 animate-spin" />
                Submitting...
              </>
            ) : (
              <>
                <FileCheck className="w-4 h-4" />
                Submit Decision
              </>
            )}
          </button>
        </div>
      </div>
    </div>
  );
}
