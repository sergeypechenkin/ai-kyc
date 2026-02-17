"""WebSocket endpoint for real-time communication."""

import asyncio
import json
import logging
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect

from src.agents.core import ChatRole
from src.api.state import get_app_state

logger = logging.getLogger(__name__)


class ConnectionManager:
    """Manages WebSocket connections."""

    def __init__(self):
        """Initialize the connection manager."""
        self.active_connections: dict[str, list[WebSocket]] = {
            "customer": [],
            "employee": [],
            "activity": [],
        }

    async def connect(self, websocket: WebSocket, channel: str) -> None:
        """Accept a new WebSocket connection.

        Args:
            websocket: The WebSocket connection
            channel: Channel name (customer, employee, activity)
        """
        await websocket.accept()
        if channel not in self.active_connections:
            self.active_connections[channel] = []
        self.active_connections[channel].append(websocket)
        logger.info(f"WebSocket connected to channel: {channel}")

    def disconnect(self, websocket: WebSocket, channel: str) -> None:
        """Remove a WebSocket connection.

        Args:
            websocket: The WebSocket connection
            channel: Channel name
        """
        if channel in self.active_connections:
            if websocket in self.active_connections[channel]:
                self.active_connections[channel].remove(websocket)
        logger.info(f"WebSocket disconnected from channel: {channel}")

    async def send_to_channel(self, message: dict[str, Any], channel: str) -> None:
        """Send a message to all connections on a channel.

        Args:
            message: Message to send
            channel: Target channel
        """
        if channel not in self.active_connections:
            return

        dead_connections = []
        for connection in self.active_connections[channel]:
            try:
                await connection.send_json(message)
            except Exception:
                dead_connections.append(connection)

        # Clean up dead connections
        for conn in dead_connections:
            self.active_connections[channel].remove(conn)

    async def broadcast(self, message: dict[str, Any]) -> None:
        """Broadcast a message to all channels.

        Args:
            message: Message to broadcast
        """
        for channel in self.active_connections:
            await self.send_to_channel(message, channel)


# Global connection manager
manager = ConnectionManager()


def setup_websocket(app: FastAPI) -> None:
    """Set up WebSocket endpoints on the FastAPI app.

    Args:
        app: The FastAPI application
    """

    @app.websocket("/ws/{channel}")
    async def websocket_endpoint(websocket: WebSocket, channel: str):
        """WebSocket endpoint for real-time communication.

        Channels:
        - customer: Customer chat messages
        - employee: Bank employee chat messages
        - activity: Activity log events
        """
        if channel not in ["customer", "employee", "activity"]:
            await websocket.close(code=4000)
            return

        await manager.connect(websocket, channel)
        state = get_app_state()

        # If this is an activity channel, subscribe to activity events
        activity_queue = None
        activity_task = None
        if channel == "activity":
            activity_queue = state.subscribe_to_activities()

            # Start task to forward activity events
            async def forward_activities():
                try:
                    while True:
                        event = await activity_queue.get()
                        await websocket.send_json({
                            "type": "activity",
                            "data": event,
                        })
                except asyncio.CancelledError:
                    pass

            activity_task = asyncio.create_task(forward_activities())

        try:
            while True:
                # Receive message from client
                data = await websocket.receive_text()
                message = json.loads(data)

                if channel in ["customer", "employee"]:
                    # Process chat or document event
                    await handle_chat_message(websocket, channel, message, state)
                    await handle_document_event(websocket, channel, message, state)

        except WebSocketDisconnect:
            manager.disconnect(websocket, channel)
            if activity_task:
                activity_task.cancel()
            if activity_queue:
                state.unsubscribe_from_activities(activity_queue)

        except Exception as e:
            logger.error(f"WebSocket error: {e}")
            manager.disconnect(websocket, channel)
            if activity_task:
                activity_task.cancel()
            if activity_queue:
                state.unsubscribe_from_activities(activity_queue)


async def handle_chat_message(
    websocket: WebSocket,
    channel: str,
    message: dict[str, Any],
    state,
) -> None:
    """Handle an incoming chat message.

    Args:
        websocket: The WebSocket connection
        channel: Channel name (customer/employee)
        message: The message data
        state: Application state
    """
    msg_type = message.get("type")
    content = message.get("content", "")

    if msg_type != "chat" or not content:
        return

    # Map channel to role
    role = ChatRole.CUSTOMER if channel == "customer" else ChatRole.EMPLOYEE

    # Send typing indicator
    await websocket.send_json({
        "type": "typing",
        "agent": f"{channel}-agent",
    })

    try:
        # Process through orchestrator
        response = await state.orchestrator.process_user_message(
            message=content,
            role=role,
        )

        # Send response back to the same channel
        await websocket.send_json({
            "type": "message",
            "role": "assistant",
            "agent": response.source_agent,
            "content": response.message,
            "metadata": {
                "requires_handoff": response.requires_handoff,
                "handoff_target": response.handoff_target,
            },
        })
    except Exception as e:
        logger.error(f"Chat message handling failed: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e),
        })


async def handle_document_event(
    websocket: WebSocket,
    channel: str,
    message: dict[str, Any],
    state,
) -> None:
    """Handle a verified document event from the client.

    Args:
        websocket: The WebSocket connection
        channel: Channel name (customer/employee)
        message: The message data
        state: Application state
    """
    msg_type = message.get("type")
    payload = message.get("payload", {})

    logger.info(f"[DOCUMENT_EVENT] Received: type={msg_type}, has_payload={bool(payload)}, confirmed={payload.get('confirmed') if payload else None}")

    if msg_type != "document_event" or not payload:
        logger.info(f"[DOCUMENT_EVENT] Skipping: wrong type or no payload")
        return

    if not payload.get("confirmed", False):
        logger.info(f"[DOCUMENT_EVENT] Skipping: not confirmed")
        return

    # Map channel to role
    role = ChatRole.CUSTOMER if channel == "customer" else ChatRole.EMPLOYEE

    logger.info(f"[DOCUMENT_EVENT] Processing: docType={payload.get('docType')}, role={role}")

    try:
        response = await state.orchestrator.process_user_message(
            message="Verified document upload event received.",
            role=role,
            context={
                "document_event": payload,
                "source": "upload",
            },
        )

        await websocket.send_json({
            "type": "message",
            "role": "assistant",
            "agent": response.source_agent,
            "content": response.message,
            "metadata": {
                "requires_handoff": response.requires_handoff,
                "handoff_target": response.handoff_target,
            },
        })
        
        # If there's a handoff, send notification to the other channel
        if response.requires_handoff and response.handoff_target:
            target_channel = (
                "employee" if response.handoff_target == "bank-employee-agent" else "customer"
            )
            await manager.send_to_channel(
                {
                    "type": "handoff",
                    "from_agent": response.source_agent,
                    "to_agent": response.handoff_target,
                    "context": response.handoff_context,
                },
                target_channel,
            )
    except Exception as e:
        logger.error(f"Document event handling failed: {e}")
        await websocket.send_json({
            "type": "error",
            "message": str(e),
        })
