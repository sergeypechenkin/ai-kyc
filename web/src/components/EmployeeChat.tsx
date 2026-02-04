import { useState, useRef, useEffect } from 'react';
import { Send, Briefcase, Bot, Wifi, WifiOff } from 'lucide-react';
import { ChatMessage } from '../types';

interface EmployeeChatProps {
  messages: ChatMessage[];
  onSendMessage: (message: string) => void;
  isConnected: boolean;
}

export default function EmployeeChat({ messages, onSendMessage, isConnected }: EmployeeChatProps) {
  const [input, setInput] = useState('');
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

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Connection status */}
      <div className={`px-3 py-1 text-xs flex items-center gap-1 ${
        isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}>
        {isConnected ? (
          <>
            <Wifi className="w-3 h-3" />
            Connected
          </>
        ) : (
          <>
            <WifiOff className="w-3 h-3" />
            Disconnected
          </>
        )}
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-400 mt-8">
            <Briefcase className="w-12 h-12 mx-auto mb-2 opacity-50" />
            <p>Bank Employee Interface</p>
            <p className="text-sm mt-1">Review KYC applications, verify documents, manage approvals</p>
          </div>
        )}
        
        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex gap-3 animate-fade-in ${
              msg.role === 'user' ? 'flex-row-reverse' : ''
            }`}
          >
            <div className={`w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0 ${
              msg.role === 'user' 
                ? 'bg-green-600 text-white' 
                : 'bg-gray-200 text-gray-600'
            }`}>
              {msg.role === 'user' ? (
                <Briefcase className="w-4 h-4" />
              ) : (
                <Bot className="w-4 h-4" />
              )}
            </div>
            
            <div className={`max-w-[80%] ${msg.role === 'user' ? 'text-right' : ''}`}>
              {msg.role === 'assistant' && msg.agent && (
                <span className="text-xs text-gray-500 mb-1 block">
                  {msg.agent}
                </span>
              )}
              <div className={`rounded-2xl px-4 py-2 ${
                msg.role === 'user'
                  ? 'bg-green-600 text-white rounded-tr-md'
                  : 'bg-gray-100 text-gray-800 rounded-tl-md'
              }`}>
                <p className="whitespace-pre-wrap">{msg.content}</p>
              </div>
              <span className="text-xs text-gray-400 mt-1 block">
                {msg.timestamp.toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <form onSubmit={handleSubmit} className="p-4 border-t bg-gray-50">
        <div className="flex gap-2">
          <input
            type="text"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Enter command or query..."
            disabled={!isConnected}
            className="flex-1 px-4 py-2 border rounded-full focus:outline-none focus:ring-2 focus:ring-green-500 disabled:bg-gray-200 disabled:cursor-not-allowed"
          />
          <button
            type="submit"
            disabled={!isConnected || !input.trim()}
            className="p-2 bg-green-600 text-white rounded-full hover:bg-green-700 disabled:bg-gray-300 disabled:cursor-not-allowed transition-colors"
          >
            <Send className="w-5 h-5" />
          </button>
        </div>
      </form>
    </div>
  );
}
