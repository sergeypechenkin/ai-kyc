"""Activity broadcasting for MAF workflow.

Provides a way for tools and agents to broadcast activity events
to connected WebSocket clients.
"""

import asyncio
import datetime
from typing import Callable, Awaitable, Any

# Global activity callback (set by server)
_activity_callback: Callable[[str, str, dict | None], Awaitable[None]] | None = None


def set_activity_callback(callback: Callable[[str, str, dict | None], Awaitable[None]]) -> None:
    """Set the activity broadcast callback.
    
    Args:
        callback: Async function(event_type, agent_name, data) to broadcast
    """
    global _activity_callback
    _activity_callback = callback


async def broadcast_activity(event_type: str, agent_name: str = "", data: dict | None = None) -> None:
    """Broadcast an activity event.
    
    Args:
        event_type: Type of activity (tool_call, tool_result, inter_agent, grounding, etc.)
        agent_name: Name of the agent
        data: Additional data for the event
    """
    if _activity_callback is not None:
        try:
            await _activity_callback(event_type, agent_name, data)
        except Exception as e:
            print(f"[WARN] Failed to broadcast activity: {e}")


def broadcast_activity_sync(event_type: str, agent_name: str = "", data: dict | None = None) -> None:
    """Synchronous wrapper for broadcast_activity.
    
    Creates a new event loop task if needed.
    """
    if _activity_callback is not None:
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                asyncio.create_task(broadcast_activity(event_type, agent_name, data))
            else:
                loop.run_until_complete(broadcast_activity(event_type, agent_name, data))
        except RuntimeError:
            # No event loop, skip
            pass
