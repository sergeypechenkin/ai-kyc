import { useState, useRef, useEffect } from 'react';
import { Send, Briefcase, Bot, Wifi, WifiOff, ClipboardCheck, X, Loader2, ChevronDown } from 'lucide-react';
import { ChatMessage } from '../types';
import DocumentUpload from './DocumentUpload';
import ComplianceReviewForm from './ComplianceReviewForm';

interface PendingReview {
  customer_id: string;
  customer_name: string;
  status: string;
  submitted_date: string;
  risk_tier: string;
  risk_score: number;
}

interface EmployeeChatProps {
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  isConnected: boolean;
}

export default function EmployeeChat({ messages, onSendMessage, isConnected }: EmployeeChatProps) {
  const [input, setInput] = useState('');
  const [showComplianceForm, setShowComplianceForm] = useState(false);
  const [reviewCustomerId, setReviewCustomerId] = useState<string>('');
  const [showPendingList, setShowPendingList] = useState(false);
  const [pendingReviews, setPendingReviews] = useState<PendingReview[]>([]);
  const [loadingPending, setLoadingPending] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const pendingListRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  // Close pending list on outside click
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (pendingListRef.current && !pendingListRef.current.contains(e.target as Node)) {
        setShowPendingList(false);
      }
    };
    if (showPendingList) document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, [showPendingList]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && isConnected) {
      onSendMessage(input.trim());
      setInput('');
    }
  };

  const loadPendingReviews = async () => {
    setLoadingPending(true);
    try {
      const res = await fetch('/api/compliance/pending');
      if (res.ok) {
        const data = await res.json();
        setPendingReviews(data.reviews || []);
      }
    } catch (err) {
      console.error('Failed to load pending reviews:', err);
    } finally {
      setLoadingPending(false);
    }
  };

  const handleOpenComplianceList = async () => {
    if (showPendingList) {
      setShowPendingList(false);
      return;
    }
    await loadPendingReviews();
    setShowPendingList(true);
  };

  const handleSelectReview = (customerId: string) => {
    setReviewCustomerId(customerId);
    setShowComplianceForm(true);
    setShowPendingList(false);
  };

  const handleComplianceDecision = async (
    decision: 'approved' | 'approved_with_conditions' | 'rejected', 
    notes: string, 
    reviewedDocs: string[]
  ) => {
    const decisionText = decision === 'approved' 
      ? `APPROVED` 
      : decision === 'approved_with_conditions'
      ? `APPROVED WITH CONDITIONS`
      : `REJECTED`;
    
    const message = `Compliance Review Decision for ${reviewCustomerId}:\n` +
      `Decision: ${decisionText}\n` +
      `Documents Reviewed: ${reviewedDocs.length}\n` +
      (notes ? `Notes: ${notes}` : '');
    
    onSendMessage(message);
    setShowComplianceForm(false);
    setReviewCustomerId('');
  };

  const riskColor = (tier: string) => {
    switch (tier.toLowerCase()) {
      case 'high': return 'text-red-700 bg-red-100 border-red-300';
      case 'medium': return 'text-amber-700 bg-amber-100 border-amber-300';
      case 'low': return 'text-green-700 bg-green-100 border-green-300';
      default: return 'text-gray-700 bg-gray-100 border-gray-300';
    }
  };

  // Show compliance form modal if active
  if (showComplianceForm && reviewCustomerId) {
    return (
      <div className="flex flex-col flex-1 overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 bg-gray-100">
          <ComplianceReviewForm
            customerId={reviewCustomerId}
            onDecision={handleComplianceDecision}
            onClose={() => {
              setShowComplianceForm(false);
              setReviewCustomerId('');
            }}
          />
        </div>
      </div>
    );
  }

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Connection status */}
      <div className={`px-3 py-1.5 text-sm flex items-center gap-1 ${
        isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}>
        {isConnected ? (
          <>
            <Wifi className="w-4 h-4" />
            Connected
          </>
        ) : (
          <>
            <WifiOff className="w-4 h-4" />
            Disconnected
          </>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-8">
            <Briefcase className="w-16 h-16 mx-auto mb-3 opacity-50" />
            <p className="text-lg">Bank Employee Interface</p>
            <p className="text-base mt-2">Review KYC applications, verify documents, manage approvals</p>
          </div>
        )}
        
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 animate-fade-in ${
              msg.role === 'user' ? 'flex-row-reverse' : ''
            }`}
          >
            <div className={`w-10 h-10 rounded-full flex items-center justify-center flex-shrink-0 ${
              msg.role === 'user' 
                ? 'bg-green-600 text-white' 
                : 'bg-gray-200 text-gray-600'
            }`}>
              {msg.role === 'user' ? (
                <Briefcase className="w-5 h-5" />
              ) : (
                <Bot className="w-5 h-5" />
              )}
            </div>
            
            <div className={`max-w-[80%] ${msg.role === 'user' ? 'text-right' : ''}`}>
              {msg.role === 'assistant' && msg.agent && (
                <span className="text-sm text-gray-500 mb-1 block">
                  {msg.agent}
                </span>
              )}
              <div className={`rounded-2xl px-4 py-3 ${
                msg.role === 'user'
                  ? 'bg-green-600 text-white rounded-tr-md'
                  : 'bg-gray-100 text-gray-800 rounded-tl-md'
              }`}>
                <p className="whitespace-pre-wrap text-base leading-relaxed">{msg.content}</p>
              </div>
              <span className="text-sm text-gray-400 mt-1 block">
                {msg.timestamp.toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t bg-gray-50">
        <div className="flex gap-2 mb-2">
          <DocumentUpload 
            onCustomerCreated={(customerId, accountNumber) => {
              console.log(`Customer ${customerId} created with account ${accountNumber}`);
            }}
          />
          <div className="relative" ref={pendingListRef}>
            <button
              type="button"
              onClick={handleOpenComplianceList}
              className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
            >
              <ClipboardCheck className="w-4 h-4" />
              Compliance Review
              <ChevronDown className={`w-3 h-3 transition-transform ${showPendingList ? 'rotate-180' : ''}`} />
            </button>

            {/* Pending reviews dropdown */}
            {showPendingList && (
              <div className="absolute bottom-full left-0 mb-1 w-80 bg-white border border-gray-200 rounded-lg shadow-xl z-50 max-h-80 overflow-y-auto">
                <div className="flex items-center justify-between px-3 py-2 border-b bg-gray-50 rounded-t-lg">
                  <span className="text-sm font-semibold text-gray-700">Pending Reviews</span>
                  <button type="button" onClick={() => setShowPendingList(false)} className="text-gray-400 hover:text-gray-600">
                    <X className="w-4 h-4" />
                  </button>
                </div>
                {loadingPending ? (
                  <div className="flex items-center justify-center py-6">
                    <Loader2 className="w-5 h-5 animate-spin text-blue-600" />
                    <span className="ml-2 text-sm text-gray-500">Loading...</span>
                  </div>
                ) : pendingReviews.length === 0 ? (
                  <div className="py-6 text-center text-sm text-gray-500">No pending reviews</div>
                ) : (
                  <div className="py-1">
                    {pendingReviews.map((review) => (
                      <button
                        key={review.customer_id}
                        type="button"
                        onClick={() => handleSelectReview(review.customer_id)}
                        className="w-full text-left px-3 py-2.5 hover:bg-blue-50 transition-colors border-b border-gray-100 last:border-b-0"
                      >
                        <div className="flex items-center justify-between">
                          <div className="flex-1 min-w-0">
                            <div className="flex items-center gap-2">
                              <span className="font-medium text-sm text-gray-900 truncate">
                                {review.customer_name || review.customer_id}
                              </span>
                              {review.risk_tier && (
                                <span className={`text-xs px-1.5 py-0.5 rounded border font-medium uppercase ${riskColor(review.risk_tier)}`}>
                                  {review.risk_tier}
                                </span>
                              )}
                            </div>
                            <div className="flex items-center gap-2 mt-0.5">
                              <span className="text-xs text-gray-500">{review.customer_id}</span>
                              <span className="text-xs text-gray-400">·</span>
                              <span className="text-xs text-gray-500">{review.submitted_date?.split('T')[0]}</span>
                            </div>
                          </div>
                          <span className="text-xs text-gray-400 ml-2">→</span>
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Enter command or query..."
            disabled={!isConnected}
            className="flex-1 px-4 py-3 text-base border rounded-full focus:outline-none focus:ring-2 focus:ring-green-500 disabled:bg-gray-200 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!isConnected || !input.trim()}
            className="p-2.5 bg-green-600 text-white rounded-full hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-6 h-6" />
          </button>
        </div>
      </form>
    </div>
  );
}
