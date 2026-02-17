import { useState, useRef, useEffect, useMemo } from 'react';
import { Send, User, Bot, Wifi, WifiOff, Upload, Paperclip, X } from 'lucide-react';
import { ChatMessage } from '../types';
import InlineUpload from './InlineUpload';

interface CustomerChatProps {
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  onAddLocalMessage: (message: string) => void;
  onSendDocumentEvent: (payload: { docType: string; extractedData: ExtractedData; confirmed: boolean; sessionId?: string }) => void;
  isConnected: boolean;
}

interface ExtractedData {
  first_name: string;
  last_name: string;
  date_of_birth: string;
  nationality: string;
  address: string;
  document_number: string;
  expiry_date: string;
  document_type: string;
  document_date?: string;
  validation_errors?: string[];
  validation_warnings?: string[];
  error?: string;
}

export default function CustomerChat({ messages, onSendMessage, onAddLocalMessage, onSendDocumentEvent, isConnected }: CustomerChatProps) {
  const [input, setInput] = useState('');
  const [showUploadPanel, setShowUploadPanel] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  
  // Generate unique session ID for document validation
  const sessionId = useMemo(() => `customer-${Date.now()}-${Math.random().toString(36).substr(2, 9)}`, []);

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

  const handleUploadComplete = (data: ExtractedData, docType: string, confirmed: boolean, uploadSessionId?: string) => {
    // Don't close upload panel - step-by-step flow manages its own visibility
    
    // Format the extracted data as a message - use detected document type
    const docTypeLabel: Record<string, string> = {
      passport: 'passport',
      driving_license: "driver's license",
      id_card: 'ID card',
      proof_of_address: 'proof of address',
      auto: 'document',
    };
    
    // Use detected type from data if available
    const actualDocType = docType !== 'auto' ? docType : (data.document_type || docType);
    const label = docTypeLabel[actualDocType] || actualDocType;

    if (data.error) {
      onAddLocalMessage(`I tried to upload a document but there was an issue: ${data.error}`);
      return;
    }

    if (!confirmed) {
      onAddLocalMessage(`The document didn't scan correctly. I'll try uploading a different photo.`);
      return;
    }

    // Build confirmation message with extracted data
    const parts = [`I've uploaded my ${label} and confirmed the information:`];

    if (actualDocType === 'proof_of_address') {
      parts.push('• I have already uploaded my identity document.');
      if (data.address) parts.push(`• Address: ${data.address}`);
      if (data.document_date) parts.push(`• Document Date: ${data.document_date}`);
    } else if (['passport', 'driving_license', 'id_card'].includes(actualDocType)) {
      if (data.first_name) parts.push(`• Name: ${data.first_name} ${data.last_name || ''}`);
      if (data.date_of_birth) parts.push(`• Date of Birth: ${data.date_of_birth}`);
      if (data.nationality) parts.push(`• Nationality: ${data.nationality}`);
      if (data.address) parts.push(`• Address: ${data.address}`);
      if (data.document_number) parts.push(`• Document Number: ${data.document_number}`);
      if (data.expiry_date) parts.push(`• Expiry Date: ${data.expiry_date}`);
    } else {
      // Additional document (bank statement, proof of income, etc.)
      parts.push(`• Document type: ${actualDocType}`);
      if (data.address) parts.push(`• Address: ${data.address}`);
      if (data.document_date) parts.push(`• Document Date: ${data.document_date}`);
    }
    
    // Add validation warnings if any
    if (data.validation_warnings && data.validation_warnings.length > 0) {
      parts.push('');
      parts.push('⚠️ Validation Notes:');
      data.validation_warnings.forEach(warn => parts.push(`• ${warn}`));
    }
    
    if (parts.length === 1) {
      parts.push('(No information could be automatically extracted.)');
    }
    
    onAddLocalMessage(parts.join('\n'));
    onSendDocumentEvent({ docType: actualDocType, extractedData: data, confirmed, sessionId: uploadSessionId });
  };

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
            <User className="w-16 h-16 mx-auto mb-3 opacity-50" />
            <p className="text-lg">Start a conversation as a customer</p>
            <p className="text-base mt-2">Say "I want to open a bank account" to get started</p>
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
                ? 'bg-blue-600 text-white' 
                : 'bg-gray-200 text-gray-600'
            }`}>
              {msg.role === 'user' ? (
                <User className="w-5 h-5" />
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
                  ? 'bg-blue-600 text-white rounded-tr-md'
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

      {/* Upload Panel - shows when user clicks upload button */}
      {showUploadPanel && (
        <div className="px-4 py-3 border-t bg-blue-50">
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <Upload className="w-4 h-4 text-blue-600" />
              <span className="text-sm font-medium text-blue-700">Upload Document</span>
            </div>
            <button 
              onClick={() => setShowUploadPanel(false)}
              className="p-1 hover:bg-blue-100 rounded"
            >
              <X className="w-4 h-4 text-gray-500" />
            </button>
          </div>
          
          <p className="text-xs text-gray-500 mb-2">
            Upload passport, driver's license, ID card, or utility bill - type is detected automatically
          </p>
          
          <InlineUpload 
            docType="auto"
            onUploadComplete={handleUploadComplete}
            sessionId={sessionId}
          />
        </div>
      )}

      {/* Quick Start Buttons */}
      {messages.length === 0 && (
        <div className="px-4 py-3 border-t bg-blue-50">
          <p className="text-sm text-blue-600 mb-2 font-medium">Quick Start</p>
          <div className="flex flex-wrap gap-2">
            <button
              onClick={() => onSendMessage("I want to open a bank account")}
              className="px-4 py-2 bg-white border border-blue-200 text-blue-700 rounded-full text-base hover:bg-blue-100 transition-colors"
            >
              Open an Account
            </button>
            <button
              onClick={() => onSendMessage("What are your account fees?")}
              className="px-4 py-2 bg-white border border-blue-200 text-blue-700 rounded-full text-base hover:bg-blue-100 transition-colors"
            >
              Account Fees
            </button>
            <button
              onClick={() => onSendMessage("What documents do I need for KYC?")}
              className="px-4 py-2 bg-white border border-blue-200 text-blue-700 rounded-full text-base hover:bg-blue-100 transition-colors"
            >
              KYC Requirements
            </button>
          </div>
        </div>
      )}

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t bg-gray-50">
        <div className="flex gap-2 items-center">
          {/* Upload/Attach button */}
          <button
            type="button"
            onClick={() => setShowUploadPanel(!showUploadPanel)}
            disabled={!isConnected}
            className={`p-2.5 rounded-full transition-colors ${
              showUploadPanel 
                ? 'bg-blue-100 text-blue-600' 
                : 'text-gray-500 hover:bg-gray-200'
            } disabled:opacity-50 disabled:cursor-not-allowed`}
            title="Upload document"
          >
            <Paperclip className="w-6 h-6" />
          </button>
          
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Type your message..."
            disabled={!isConnected}
            className="flex-1 px-4 py-3 text-base border rounded-full focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-gray-200 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!isConnected || !input.trim()}
            className="p-2.5 bg-blue-600 text-white rounded-full hover:bg-blue-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-6 h-6" />
          </button>
        </div>
      </form>
    </div>
  );
}
