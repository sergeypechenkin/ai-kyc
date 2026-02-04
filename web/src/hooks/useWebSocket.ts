import { useState, useEffect, useCallback, useRef } from 'react';
import { WsMessage } from '../types';

interface UseWebSocketReturn {
  isConnected: boolean;
  lastMessage: WsMessage | null;
  send: (message: object) => void;
  error: string | null;
}

export function useWebSocket(channel: string): UseWebSocketReturn {
  const [isConnected, setIsConnected] = useState(false);
  const [lastMessage, setLastMessage] = useState<WsMessage | null>(null);
  const [error, setError] = useState<string | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<number | null>(null);

  const connect = useCallback(() => {
    try {
      const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
      const host = window.location.host;
      const wsUrl = `${protocol}//${host}/ws/${channel}`;
      
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        setIsConnected(true);
        setError(null);
        console.log(`WebSocket connected to ${channel}`);
      };

      ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data);
          setLastMessage(data);
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      };

      ws.onerror = (event) => {
        console.error(`WebSocket error on ${channel}:`, event);
        setError('Connection error');
      };

      ws.onclose = () => {
        setIsConnected(false);
        console.log(`WebSocket disconnected from ${channel}`);
        
        // Attempt to reconnect after 3 seconds
        reconnectTimeoutRef.current = window.setTimeout(() => {
          console.log(`Attempting to reconnect to ${channel}...`);
          connect();
        }, 3000);
      };
    } catch (e) {
      console.error('Failed to create WebSocket:', e);
      setError('Failed to connect');
    }
  }, [channel]);

  useEffect(() => {
    connect();

    return () => {
      if (wsRef.current) {
        wsRef.current.close();
      }
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
      }
    };
  }, [connect]);

  const send = useCallback((message: object) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(message));
    } else {
      console.error('WebSocket is not connected');
    }
  }, []);

  return {
    isConnected,
    lastMessage,
    send,
    error,
  };
}
