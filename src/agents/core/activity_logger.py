"""Activity logger for detailed agent event tracking."""

import asyncio
import uuid
from collections.abc import Awaitable, Callable
from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field
from semantic_kernel.filters import FilterTypes
from semantic_kernel.filters.functions.function_invocation_context import FunctionInvocationContext
from semantic_kernel.filters.prompts.prompt_render_context import PromptRenderContext
from semantic_kernel import Kernel


class ActivityType(str, Enum):
    """Types of activity events."""

    # Agent events
    AGENT_START = "agent_start"
    AGENT_RESPONSE = "agent_response"
    AGENT_ERROR = "agent_error"

    # Inter-agent events
    INTER_AGENT_MESSAGE = "inter_agent_message"
    HANDOFF_INITIATED = "handoff_initiated"
    HANDOFF_COMPLETED = "handoff_completed"

    # Plugin/Tool events
    TOOL_CALL_START = "tool_call_start"
    TOOL_CALL_END = "tool_call_end"
    TOOL_CALL_ERROR = "tool_call_error"

    # Document grounding events
    DOCUMENT_SEARCH = "document_search"
    DOCUMENT_RETRIEVED = "document_retrieved"

    # Prompt events
    PROMPT_RENDERED = "prompt_rendered"

    # Token usage
    TOKEN_USAGE = "token_usage"

    # User events
    USER_MESSAGE = "user_message"


class ActivityEvent(BaseModel):
    """A single activity event."""

    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    type: ActivityType
    agent_name: str | None = None
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    duration_ms: float | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class ActivityLogger:
    """Logger for tracking all agent activities.

    Captures:
    - Tool/plugin invocations
    - Inter-agent messages
    - Document retrievals
    - Prompt rendering
    - Token usage
    - Errors
    """

    def __init__(
        self,
        on_event: Callable[[ActivityEvent], None | Awaitable[None]] | None = None,
        buffer_size: int = 1000,
    ):
        """Initialize the activity logger.

        Args:
            on_event: Callback for each event (for real-time streaming)
            buffer_size: Maximum number of events to buffer
        """
        self.on_event = on_event
        self.buffer_size = buffer_size
        self._events: list[ActivityEvent] = []
        self._lock = asyncio.Lock()

    async def log(
        self,
        event_type: ActivityType | str,
        agent_name: str | None = None,
        data: dict[str, Any] | None = None,
        duration_ms: float | None = None,
    ) -> ActivityEvent:
        """Log an activity event.

        Args:
            event_type: Type of event
            agent_name: Name of the agent (if applicable)
            data: Additional event data
            duration_ms: Duration in milliseconds (if applicable)

        Returns:
            The created event
        """
        if isinstance(event_type, str):
            try:
                event_type = ActivityType(event_type)
            except ValueError:
                # Allow custom event types, use a generic type
                event_type = ActivityType.AGENT_RESPONSE

        event = ActivityEvent(
            type=event_type,
            agent_name=agent_name,
            data=data or {},
            duration_ms=duration_ms,
        )

        async with self._lock:
            self._events.append(event)
            # Trim buffer if needed
            if len(self._events) > self.buffer_size:
                self._events = self._events[-self.buffer_size :]

        # Notify callback
        if self.on_event:
            result = self.on_event(event)
            if asyncio.iscoroutine(result):
                await result

        return event

    def get_events(
        self,
        limit: int | None = None,
        event_types: list[ActivityType] | None = None,
        agent_name: str | None = None,
    ) -> list[ActivityEvent]:
        """Get logged events with optional filtering.

        Args:
            limit: Maximum number of events to return
            event_types: Filter by event types
            agent_name: Filter by agent name

        Returns:
            List of matching events
        """
        events = self._events

        if event_types:
            events = [e for e in events if e.type in event_types]

        if agent_name:
            events = [e for e in events if e.agent_name == agent_name]

        if limit:
            events = events[-limit:]

        return events

    def clear(self) -> None:
        """Clear all logged events."""
        self._events.clear()

    def create_kernel_filters(self, kernel: Kernel, agent_name: str) -> None:
        """Add Semantic Kernel filters for automatic logging.

        Args:
            kernel: The Semantic Kernel instance
            agent_name: Name of the agent for attribution
        """

        @kernel.filter(FilterTypes.FUNCTION_INVOCATION)
        async def function_invocation_filter(
            context: FunctionInvocationContext,
            next: Callable[[FunctionInvocationContext], Awaitable[None]],
        ) -> None:
            """Filter for logging function/plugin invocations."""
            start_time = datetime.utcnow()

            # Log start
            await self.log(
                event_type=ActivityType.TOOL_CALL_START,
                agent_name=agent_name,
                data={
                    "plugin": context.function.plugin_name,
                    "function": context.function.name,
                    "arguments": {k: str(v)[:100] for k, v in (context.arguments or {}).items()},
                },
            )

            try:
                await next(context)

                # Calculate duration
                duration = (datetime.utcnow() - start_time).total_seconds() * 1000

                # Log completion
                result_preview = str(context.result)[:200] if context.result else None
                await self.log(
                    event_type=ActivityType.TOOL_CALL_END,
                    agent_name=agent_name,
                    duration_ms=duration,
                    data={
                        "plugin": context.function.plugin_name,
                        "function": context.function.name,
                        "result_preview": result_preview,
                    },
                )
            except Exception as e:
                duration = (datetime.utcnow() - start_time).total_seconds() * 1000
                await self.log(
                    event_type=ActivityType.TOOL_CALL_ERROR,
                    agent_name=agent_name,
                    duration_ms=duration,
                    data={
                        "plugin": context.function.plugin_name,
                        "function": context.function.name,
                        "error": str(e),
                    },
                )
                raise

        @kernel.filter(FilterTypes.PROMPT_RENDERING)
        async def prompt_render_filter(
            context: PromptRenderContext,
            next: Callable[[PromptRenderContext], Awaitable[None]],
        ) -> None:
            """Filter for logging prompt rendering."""
            await next(context)

            # Log rendered prompt (truncated for privacy)
            rendered = context.rendered_prompt or ""
            await self.log(
                event_type=ActivityType.PROMPT_RENDERED,
                agent_name=agent_name,
                data={
                    "function": context.function.name if context.function else "unknown",
                    "prompt_length": len(rendered),
                    "prompt_preview": rendered[:300] + "..." if len(rendered) > 300 else rendered,
                },
            )
