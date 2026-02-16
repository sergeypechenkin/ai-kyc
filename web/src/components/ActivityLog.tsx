import { useState, useRef, useEffect } from 'react';
import { 
  ChevronDown, 
  ChevronRight, 
  Wifi, 
  WifiOff,
  Zap,
  MessageSquare,
  Search,
  CheckCircle,
  XCircle,
  Clock,
  ArrowRightLeft,
  FileText,
  Trash2
} from 'lucide-react';
import { ActivityEvent } from '../types';

interface ActivityLogProps {
  activities: ActivityEvent[];
  isConnected: boolean;
}

// Map event types to icons and colors
const eventConfig: Record<string, { icon: React.ElementType; color: string; bgColor: string }> = {
  agent_start: { icon: Zap, color: 'text-yellow-600', bgColor: 'bg-yellow-100' },
  agent_response: { icon: MessageSquare, color: 'text-blue-600', bgColor: 'bg-blue-100' },
  tool_call_start: { icon: Zap, color: 'text-purple-600', bgColor: 'bg-purple-100' },
  tool_call_end: { icon: CheckCircle, color: 'text-green-600', bgColor: 'bg-green-100' },
  tool_call_error: { icon: XCircle, color: 'text-red-600', bgColor: 'bg-red-100' },
  document_search: { icon: Search, color: 'text-indigo-600', bgColor: 'bg-indigo-100' },
  document_retrieved: { icon: FileText, color: 'text-indigo-600', bgColor: 'bg-indigo-100' },
  inter_agent_message: { icon: ArrowRightLeft, color: 'text-orange-600', bgColor: 'bg-orange-100' },
  user_message: { icon: MessageSquare, color: 'text-gray-600', bgColor: 'bg-gray-100' },
  prompt_rendered: { icon: FileText, color: 'text-cyan-600', bgColor: 'bg-cyan-100' },
  default: { icon: Clock, color: 'text-gray-500', bgColor: 'bg-gray-100' },
};

// Format event title with context
function getEventTitle(activity: ActivityEvent): { title: string; subtitle?: string } {
  const data = activity.data || {};
  
  switch (activity.type) {
    case 'tool_call_start':
      return {
        title: `🔧 Tool: ${(data.function as string) || 'unknown'}`,
        subtitle: data.plugin ? `Plugin: ${data.plugin}` : undefined,
      };
    case 'tool_call_end':
      return {
        title: `✅ ${(data.function as string) || 'Tool'} completed`,
        subtitle: data.result_preview ? String(data.result_preview).slice(0, 50) + '...' : undefined,
      };
    case 'tool_call_error':
      return {
        title: `❌ ${(data.function as string) || 'Tool'} failed`,
        subtitle: data.error as string | undefined,
      };
    case 'document_search':
      return {
        title: `🔍 Document Search`,
        subtitle: data.query as string | undefined,
      };
    case 'document_retrieved':
      return {
        title: `📄 ${data.count || 0} documents found`,
        subtitle: data.source as string | undefined,
      };
    case 'inter_agent_message':
      return {
        title: `💬 ${data.from || 'Agent'} → ${data.to || 'Agent'}`,
        subtitle: data.message ? String(data.message).slice(0, 60) : undefined,
      };
    case 'agent_start':
      return {
        title: `▶️ Agent started`,
        subtitle: data.message ? String(data.message).slice(0, 60) : undefined,
      };
    case 'agent_response':
      return {
        title: `💬 Agent response`,
        subtitle: data.response ? String(data.response).slice(0, 60) : undefined,
      };
    case 'prompt_rendered':
      return {
        title: `📝 Prompt (${data.prompt_length || 0} chars)`,
        subtitle: data.function as string | undefined,
      };
    default:
      return {
        title: activity.type.replace(/_/g, ' '),
      };
  }
}

function ActivityItem({ activity }: { activity: ActivityEvent }) {
  const [expanded, setExpanded] = useState(false);
  const config = eventConfig[activity.type] || eventConfig.default;
  const Icon = config.icon;
  const { title, subtitle } = getEventTitle(activity);

  return (
    <div className="border-b border-gray-100 last:border-0 animate-slide-in">
      <button
        onClick={() => setExpanded(!expanded)}
        className="w-full px-3 py-2.5 flex items-start gap-2 hover:bg-gray-50 transition-colors text-left"
      >
        <div className={`p-1.5 rounded ${config.bgColor} ${config.color} mt-0.5`}>
          <Icon className="w-4 h-4" />
        </div>
        
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="font-medium text-base text-gray-900 truncate">
              {title}
            </span>
            {activity.durationMs && (
              <span className="text-sm text-gray-400">
                {activity.durationMs.toFixed(0)}ms
              </span>
            )}
          </div>
          {subtitle && (
            <span className="text-sm text-gray-500 truncate block">{subtitle}</span>
          )}
          {activity.agentName && !subtitle && (
            <span className="text-sm text-gray-500">{activity.agentName}</span>
          )}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-sm text-gray-400">
            {activity.timestamp.toLocaleTimeString()}
          </span>
          {expanded ? (
            <ChevronDown className="w-5 h-5 text-gray-400" />
          ) : (
            <ChevronRight className="w-5 h-5 text-gray-400" />
          )}
        </div>
      </button>

      {expanded && (
        <div className="px-3 pb-3 pl-10">
          <pre className="text-sm bg-gray-900 text-gray-100 p-3 rounded-lg overflow-x-auto">
            {JSON.stringify(activity.data, null, 2)}
          </pre>
        </div>
      )}
    </div>
  );
}

export default function ActivityLog({ activities, isConnected }: ActivityLogProps) {
  const scrollRef = useRef<HTMLDivElement>(null);
  const [autoScroll, setAutoScroll] = useState(true);

  // Auto-scroll to bottom on new activities
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [activities, autoScroll]);

  // Detect manual scroll
  const handleScroll = () => {
    if (scrollRef.current) {
      const { scrollTop, scrollHeight, clientHeight } = scrollRef.current;
      const isAtBottom = scrollHeight - scrollTop - clientHeight < 50;
      setAutoScroll(isAtBottom);
    }
  };

  return (
    <div className="flex flex-col flex-1 overflow-hidden">
      {/* Connection status */}
      <div className={`px-3 py-1.5 text-sm flex items-center justify-between ${
        isConnected ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700'
      }`}>
        <div className="flex items-center gap-1">
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
        <span className="text-gray-500">{activities.length} events</span>
      </div>

      {/* Activities */}
      <div
        ref={scrollRef}
        onScroll={handleScroll}
        className="flex-1 overflow-y-auto"
      >
        {activities.length === 0 && (
          <div className="text-center text-gray-400 mt-8 px-4">
            <Clock className="w-16 h-16 mx-auto mb-3 opacity-50" />
            <p className="text-lg">No activity yet</p>
            <p className="text-base mt-2">Agent events will appear here in real-time</p>
          </div>
        )}

        {activities.map((activity) => (
          <ActivityItem key={activity.id} activity={activity} />
        ))}
      </div>

      {/* Footer with auto-scroll indicator */}
      <div className="px-3 py-2 border-t bg-gray-50 flex items-center justify-between text-sm">
        <button
          onClick={() => setAutoScroll(!autoScroll)}
          className={`flex items-center gap-1 ${
            autoScroll ? 'text-green-600' : 'text-gray-500'
          }`}
        >
          {autoScroll ? (
            <>
              <CheckCircle className="w-4 h-4" />
              Auto-scroll on
            </>
          ) : (
            <>
              <XCircle className="w-4 h-4" />
              Auto-scroll off
            </>
          )}
        </button>

        <button
          onClick={() => window.location.reload()}
          className="text-gray-500 hover:text-gray-700 flex items-center gap-1"
        >
          <Trash2 className="w-4 h-4" />
          Clear
        </button>
      </div>
    </div>
  );
}
