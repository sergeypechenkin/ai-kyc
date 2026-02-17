import { useState, useEffect, useCallback } from 'react';
import { Settings } from 'lucide-react';
import CustomerChat from './components/CustomerChat';
import EmployeeChat from './components/EmployeeChat';
import ActivityLog from './components/ActivityLog';
import GroundingToggle from './components/GroundingToggle';
import { useWebSocket } from './hooks/useWebSocket';
import { ActivityEvent, ChatMessage } from './types';

function App() {
  const [groundingEnabled, setGroundingEnabled] = useState(false);
  const [customerMessages, setCustomerMessages] = useState<ChatMessage[]>([]);
  const [employeeMessages, setEmployeeMessages] = useState<ChatMessage[]>([]);
  const [activities, setActivities] = useState<ActivityEvent[]>([]);
  const [showSettings, setShowSettings] = useState(false);

  // WebSocket connections
  const customerWs = useWebSocket('customer');
  const employeeWs = useWebSocket('employee');
  const activityWs = useWebSocket('activity');

  // Handle incoming customer messages
  useEffect(() => {
    if (customerWs.lastMessage) {
      const msg = customerWs.lastMessage;
      if (msg.type === 'message' && msg.role && msg.content) {
        const newMessage: ChatMessage = {
          id: Date.now().toString(),
          role: msg.role as 'user' | 'assistant' | 'system',
          content: msg.content,
          agent: msg.agent,
          timestamp: new Date(),
        };
        setCustomerMessages(prev => [...prev, newMessage]);
      }
    }
  }, [customerWs.lastMessage]);

  // Handle incoming employee messages
  useEffect(() => {
    if (employeeWs.lastMessage) {
      const msg = employeeWs.lastMessage;
      if (msg.type === 'message' && msg.role && msg.content) {
        const newMessage: ChatMessage = {
          id: Date.now().toString(),
          role: msg.role as 'user' | 'assistant' | 'system',
          content: msg.content,
          agent: msg.agent,
          timestamp: new Date(),
        };
        setEmployeeMessages(prev => [...prev, newMessage]);
      }
    }
  }, [employeeWs.lastMessage]);

  // Handle activity events
  useEffect(() => {
    if (activityWs.lastMessage) {
      const msg = activityWs.lastMessage;
      if (msg.type === 'activity' && msg.data) {
        const data = msg.data as Record<string, unknown>;
        setActivities(prev => [...prev, {
          id: (data.id as string) || Date.now().toString(),
          type: data.type as string,
          agentName: data.agent_name as string | undefined,
          timestamp: new Date(data.timestamp as string),
          data: (data.data as Record<string, unknown>) || data,
          durationMs: data.duration_ms as number | undefined,
        }]);
      }
    }
  }, [activityWs.lastMessage]);

  // Send customer message
  const sendCustomerMessage = useCallback((content: string) => {
    // Add user message to chat
    setCustomerMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    }]);
    
    // Send via WebSocket
    customerWs.send({ type: 'chat', content });
  }, [customerWs]);

  // Add a local-only customer message (no backend send)
  const addCustomerLocalMessage = useCallback((content: string) => {
    setCustomerMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    }]);
  }, []);

  // Send verified document event (not a user chat message)
  const sendCustomerDocumentEvent = useCallback((payload: { docType: string; extractedData: Record<string, unknown>; confirmed: boolean; sessionId?: string }) => {
    customerWs.send({ type: 'document_event', payload });
  }, [customerWs]);

  // Send employee message
  const sendEmployeeMessage = useCallback((content: string) => {
    // Add user message to chat
    setEmployeeMessages(prev => [...prev, {
      id: Date.now().toString(),
      role: 'user',
      content,
      timestamp: new Date(),
    }]);
    
    // Send via WebSocket
    employeeWs.send({ type: 'chat', content });
  }, [employeeWs]);

  // Toggle grounding
  const handleGroundingToggle = async (enabled: boolean) => {
    try {
      const response = await fetch('/api/config/grounding', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled }),
      });
      
      if (response.ok) {
        setGroundingEnabled(enabled);
      }
    } catch (error) {
      console.error('Failed to toggle grounding:', error);
    }
  };

  // Load initial config
  useEffect(() => {
    fetch('/api/config/grounding')
      .then(res => res.json())
      .then(data => setGroundingEnabled(data.enabled))
      .catch(console.error);
  }, []);

  return (
    <div className="min-h-screen bg-gray-100">
      {/* Header */}
      <header className="bg-zava-purple text-white shadow-lg">
        <div className="max-w-full mx-auto px-4 py-3 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-12 h-12 bg-white rounded-lg flex items-center justify-center">
              <span className="text-zava-purple font-bold text-xl">ZB</span>
            </div>
            <div>
              <h1 className="text-2xl font-semibold">Zava Bank AI-KYC</h1>
              <p className="text-purple-200 text-base">Multi-Agent KYC System</p>
            </div>
          </div>
          
          <div className="flex items-center gap-4">
            <GroundingToggle 
              enabled={groundingEnabled} 
              onToggle={handleGroundingToggle} 
            />
            <button 
              onClick={() => setShowSettings(!showSettings)}
              className="p-2 hover:bg-zava-purple-dark rounded-lg transition-colors"
            >
              <Settings className="w-5 h-5" />
            </button>
          </div>
        </div>
      </header>

      {/* Main Content */}
      <main className="max-w-full mx-auto p-4">
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4 h-[calc(100vh-120px)]">
          {/* Customer Chat */}
          <div className="bg-white rounded-xl shadow-md overflow-hidden flex flex-col">
            <div className="bg-blue-600 text-white px-4 py-4">
              <h2 className="font-semibold text-lg">Customer Chat</h2>
              <p className="text-blue-200 text-base">Talk to the Customer Service Agent</p>
            </div>
            <CustomerChat
              messages={customerMessages}
              onSendMessage={sendCustomerMessage}
              onAddLocalMessage={addCustomerLocalMessage}
              onSendDocumentEvent={sendCustomerDocumentEvent}
              isConnected={customerWs.isConnected}
            />
          </div>

          {/* Employee Chat */}
          <div className="bg-white rounded-xl shadow-md overflow-hidden flex flex-col">
            <div className="bg-green-600 text-white px-4 py-4">
              <h2 className="font-semibold text-lg">Bank Employee Chat</h2>
              <p className="text-green-200 text-base">Bank Employee Agent Interface</p>
            </div>
            <EmployeeChat
              messages={employeeMessages}
              onSendMessage={sendEmployeeMessage}
              isConnected={employeeWs.isConnected}
            />
          </div>

          {/* Activity Log */}
          <div className="bg-white rounded-xl shadow-md overflow-hidden flex flex-col">
            <div className="bg-gray-800 text-white px-4 py-4">
              <h2 className="font-semibold text-lg">Activity Log</h2>
              <p className="text-gray-400 text-base">Agent internals & events</p>
            </div>
            <ActivityLog 
              activities={activities}
              isConnected={activityWs.isConnected}
            />
          </div>
        </div>
      </main>
    </div>
  );
}

export default App;
