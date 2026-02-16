import { useState, useRef, useEffect } from 'react';
import { Send, Briefcase, Bot, Wifi, WifiOff, ClipboardCheck } from 'lucide-react';
import { ChatMessage } from '../types';
import DocumentUpload from './DocumentUpload';
import ComplianceReviewForm from './ComplianceReviewForm';

interface EmployeeChatProps {
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  isConnected: boolean;
}

export default function EmployeeChat({ messages, onSendMessage, isConnected }: EmployeeChatProps) {
  const [input, setInput] = useState('');
  const [showComplianceForm, setShowComplianceForm] = useState(false);
  const [reviewCustomerId, setReviewCustomerId] = useState<string>('');
  const messagesEndRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom on new messages
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (input.trim() && isConnected) {
      onSendMessage(input.trim());
      setInput('');
    }
  };

  const handleOpenComplianceForm = () => {
    const customerId = prompt('Enter Customer ID to review (e.g., C015):');
    if (customerId) {
      setReviewCustomerId(customerId.trim());
      setShowComplianceForm(true);
    }
  };

  const handleComplianceDecision = async (
    decision: 'approved' | 'approved_with_conditions' | 'rejected', 
    notes: string, 
    reviewedDocs: string[]
  ) => {
    // Send the decision as a message to the chat
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
              // Optionally notify the chat about the new customer
              console.log(`Customer ${customerId} created with account ${accountNumber}`);
            }}
          />
          <button
            type="button"
            onClick={handleOpenComplianceForm}
            className="flex items-center gap-2 px-3 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 transition-colors text-sm font-medium"
          >
            <ClipboardCheck className="w-4 h-4" />
            Compliance Review
          </button>
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
