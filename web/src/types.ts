// Chat message types
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  agent?: string;
  timestamp: Date;
  metadata?: Record<string, unknown>;
}

// Activity event types
export interface ActivityEvent {
  id: string;
  type: string;
  agentName?: string;
  timestamp: Date;
  durationMs?: number;
  data: Record<string, unknown>;
}

// WebSocket message types
export interface WsMessage {
  type: 'chat' | 'message' | 'typing' | 'error' | 'activity' | 'handoff';
  content?: string;
  role?: string;
  agent?: string;
  data?: Record<string, unknown>;
  metadata?: Record<string, unknown>;
}

// Agent info
export interface AgentInfo {
  name: string;
  displayName: string;
  description: string;
  capabilities: string[];
  initialized: boolean;
}

// Configuration
export interface AppConfig {
  groundingEnabled: boolean;
  azureOpenaiConfigured: boolean;
  azureSearchConfigured: boolean;
  environment: string;
}
