"""Telemetry helpers for Application Insights integration.

Provides custom tracking for agent operations, tool calls, and performance metrics.
"""

import os
import time
from typing import Any
from contextlib import contextmanager
from functools import wraps

# OpenTelemetry imports (optional - graceful degradation)
try:
    from opentelemetry import trace
    from opentelemetry.trace import StatusCode
    TELEMETRY_AVAILABLE = True
except ImportError:
    TELEMETRY_AVAILABLE = False
    trace = None
    StatusCode = None


def get_tracer(name: str = "ai-kyc"):
    """Get an OpenTelemetry tracer.
    
    Args:
        name: Tracer name
        
    Returns:
        Tracer instance or None if telemetry not available
    """
    if not TELEMETRY_AVAILABLE:
        return None
    return trace.get_tracer(name)


@contextmanager
def track_agent_operation(
    agent_name: str,
    operation: str,
    attributes: dict[str, Any] | None = None
):
    """Context manager to track agent operations.
    
    Args:
        agent_name: Name of the agent
        operation: Operation being performed
        attributes: Additional span attributes
        
    Yields:
        Span for adding events/attributes
    """
    tracer = get_tracer()
    
    if tracer is None:
        # Fallback: just yield None and track nothing
        yield None
        return
    
    span_attributes = {
        "agent.name": agent_name,
        "agent.operation": operation,
        **(attributes or {})
    }
    
    with tracer.start_as_current_span(
        f"agent.{operation}",
        attributes=span_attributes
    ) as span:
        start_time = time.time()
        try:
            yield span
            span.set_status(StatusCode.OK)
        except Exception as e:
            span.set_status(StatusCode.ERROR, str(e))
            span.record_exception(e)
            raise
        finally:
            duration_ms = (time.time() - start_time) * 1000
            span.set_attribute("duration_ms", duration_ms)


def track_tool_call(tool_name: str):
    """Decorator to track tool function calls.
    
    Args:
        tool_name: Name of the tool
        
    Returns:
        Decorated function
    """
    def decorator(func):
        @wraps(func)
        async def async_wrapper(*args, **kwargs):
            with track_agent_operation("system", f"tool.{tool_name}", {
                "tool.name": tool_name,
                "tool.args": str(kwargs)[:200]  # Truncate for safety
            }) as span:
                result = await func(*args, **kwargs)
                if span:
                    span.set_attribute("tool.result_length", len(str(result)))
                return result
        
        @wraps(func)
        def sync_wrapper(*args, **kwargs):
            with track_agent_operation("system", f"tool.{tool_name}", {
                "tool.name": tool_name,
                "tool.args": str(kwargs)[:200]
            }) as span:
                result = func(*args, **kwargs)
                if span:
                    span.set_attribute("tool.result_length", len(str(result)))
                return result
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper
    
    return decorator


def track_custom_event(
    name: str,
    properties: dict[str, Any] | None = None
):
    """Track a custom event.
    
    Args:
        name: Event name
        properties: Event properties
    """
    tracer = get_tracer()
    if tracer is None:
        return
    
    span = trace.get_current_span()
    if span:
        span.add_event(name, attributes=properties or {})


def track_metric(name: str, value: float, attributes: dict[str, Any] | None = None):
    """Track a custom metric.
    
    Note: For proper metric tracking, use OpenTelemetry metrics API.
    This is a simplified version using span attributes.
    
    Args:
        name: Metric name
        value: Metric value
        attributes: Metric attributes/dimensions
    """
    tracer = get_tracer()
    if tracer is None:
        return
    
    with tracer.start_as_current_span(f"metric.{name}") as span:
        span.set_attribute("metric.name", name)
        span.set_attribute("metric.value", value)
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(f"metric.{k}", v)
