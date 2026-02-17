# Agent Tracing and Monitoring - Implementation Summary

## Problem Identified

You reported that despite using MAF agents created in Azure AI Foundry for many days, no traces or monitoring data appeared. 

**Root Cause:**
1. **Missing OpenTelemetry instrumentation packages** - The required packages `azure-monitor-opentelemetry` and `opentelemetry-instrumentation-openai-v2` were not installed
2. **Missing telemetry code in workflow** - Agent operations in `workflow.py` were not creating OpenTelemetry spans with proper gen_ai attributes
3. **No startup validation** - No feedback to confirm tracing was actually configured

## Solution Implemented

### 1. Installed Required Packages

Added to `requirements-maf.txt`:
```
azure-monitor-opentelemetry>=1.4.0
opentelemetry-instrumentation-openai-v2>=2.0
```

These packages:
- **azure-monitor-opentelemetry**: Exports traces/metrics to Azure Application Insights
- **opentelemetry-instrumentation-openai-v2**: Auto-instruments OpenAI SDK calls to capture LLM requests/responses

### 2. Enhanced Server Initialization ([src/maf/server.py](../src/maf/server.py))

Added startup validation and clearer logging:

```python
# Configure Azure Monitor for OpenTelemetry (Application Insights)
app_insights_conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if app_insights_conn_str:
    configure_azure_monitor(
        connection_string=app_insights_conn_str,
        enable_live_metrics=True,
    )
    print("[OK] Application Insights configured")
    
    # Enable OpenAI instrumentation
    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
    OpenAIInstrumentor().instrument()
    print("[OK] OpenAI instrumentation enabled")
else:
    print("[WARN] APPLICATIONINSIGHTS_CONNECTION_STRING not set; traces will not be sent")
```

Now you'll see clear startup messages indicating whether tracing is enabled.

### 3. Added Agent Operation Tracing ([src/maf/workflow.py](../src/maf/workflow.py))

Enhanced `process_message()` and `process_message_stream()` methods with OpenTelemetry spans:

```python
with track_agent_operation(
    agent_name=role.value,
    operation="chat",
    attributes={
        "gen_ai.system": "azure_openai",
        "gen_ai.operation.name": "chat",
        "gen_ai.agent.name": role.value,
        "gen_ai.request.model": _get_deployment_name(),
        "gen_ai.prompt_length": len(message),
    },
) as span:
    response = await executor.agent.run(executor.conversation_history)
    response_text = _extract_response_text(response)
    if span:
        span.set_attribute("gen_ai.response.model", _get_deployment_name())
        span.set_attribute("gen_ai.completion_length", len(response_text))
```

This creates spans with:
- Agent name and operation type
- Model deployment name
- Prompt/completion lengths
- Execution duration

### 4. Created Validation Script ([test_tracing.py](../test_tracing.py))

Created a comprehensive test script that validates:
- ✅ Application Insights connection string is set
- ✅ Required OpenTelemetry packages are installed
- ✅ Azure Monitor can be configured
- ✅ OpenAI instrumentation works
- ✅ Test spans can be created
- ✅ Azure OpenAI configuration is complete

Run with: `python test_tracing.py`

### 5. Created Comprehensive Documentation ([docs/TRACING_AND_MONITORING.md](../docs/TRACING_AND_MONITORING.md))

Created detailed guide covering:
- Architecture diagram of telemetry flow
- Step-by-step configuration instructions
- How to retrieve Application Insights connection string
- KQL queries for analyzing traces
- Troubleshooting common issues
- Best practices for production

## How to Verify Tracing is Working

### Step 1: Run Configuration Test

```bash
python test_tracing.py
```

Expected output:
```
✅ All critical tests passed!
```

### Step 2: Start the Server

```bash
python -m src.maf.server --port 8087
```

Look for these startup messages:
```
[OK] Application Insights configured
[OK] OpenAI instrumentation enabled
[OK] MAF Workflow initialized
```

### Step 3: Send Test Requests

```bash
# Customer agent
curl -X POST http://localhost:8087/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "I want to open a business account", "role": "customer"}'

# Employee agent
curl -X POST http://localhost:8087/api/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "Show me pending verifications", "role": "employee"}'
```

### Step 4: View Traces in Azure Portal

**Option A: Live Metrics (Real-time)**
1. Open Azure Portal → Application Insights resource `aikyc-appi-dev`
2. Navigate to **Investigate → Live Metrics**
3. Watch traces appear in real-time as you send requests

**Option B: Transaction Search (Historical)**
1. Open Azure Portal → Application Insights resource
2. Navigate to **Investigate → Transaction search**
3. Set time range to "Last 30 minutes"
4. Filter by:
   - **Operation Name**: `agent.chat`, `POST /api/chat`
   - **Dependency Type**: `openai`
5. Wait 2-3 minutes for data propagation

**Option C: KQL Queries**

Navigate to **Monitoring → Logs** and run:

```kusto
// All agent operations
traces
| where customDimensions.SpanName startswith "agent."
| project timestamp, message, customDimensions
| order by timestamp desc
| take 50
```

```kusto
// OpenAI API calls with token usage
dependencies
| where type == "openai"
| extend model = tostring(customDimensions['gen_ai.request.model'])
| extend prompt_tokens = toint(customDimensions['gen_ai.usage.prompt_tokens'])
| extend completion_tokens = toint(customDimensions['gen_ai.usage.completion_tokens'])
| project timestamp, name, duration, model, prompt_tokens, completion_tokens
| order by timestamp desc
```

```kusto
// Tool invocations
traces
| where customDimensions.SpanName startswith "tool."
| extend tool_name = tostring(customDimensions['tool.name'])
| extend duration_ms = toreal(customDimensions['duration_ms'])
| summarize count(), avg(duration_ms) by tool_name
| order by count_ desc
```

## What You Should See

Once tracing is working, you'll see:

### In Live Metrics:
- **Incoming Requests**: HTTP requests to `/api/chat`
- **Outgoing Requests**: Calls to Azure OpenAI
- **Request Rate**: Requests per second
- **Response Time**: Average latency
- **Failure Rate**: Error percentage

### In Transaction Search:
- **Requests**: Each `/api/chat` endpoint call
- **Dependencies**: Each OpenAI API call with token counts
- **Custom Traces**: Agent operations (`agent.chat`, `agent.customer`, `agent.employee`)
- **Tool Calls**: Tool invocations (`tool.search_documents`, `tool.get_customer_by_email`, etc.)

### In Application Map:
- Dependency graph showing: `FastAPI → Azure OpenAI`
- Performance metrics for each component
- Failure rates visualized

## Key Files Modified

| File | Changes |
|------|---------|
| [src/maf/server.py](../src/maf/server.py) | Added clear startup logging, warning when connection string missing |
| [src/maf/workflow.py](../src/maf/workflow.py) | Added `track_agent_operation()` spans for all agent runs, helper functions for model name |
| [src/maf/telemetry.py](../src/maf/telemetry.py) | No changes (already had proper helpers) |
| [requirements-maf.txt](../requirements-maf.txt) | Added `azure-monitor-opentelemetry` and `opentelemetry-instrumentation-openai-v2` |

## New Files Created

| File | Purpose |
|------|---------|
| [test_tracing.py](../test_tracing.py) | Validation script to test tracing configuration |
| [docs/TRACING_AND_MONITORING.md](../docs/TRACING_AND_MONITORING.md) | Comprehensive guide for tracing and monitoring |

## Configuration Required

Ensure your `.env` file has:

```bash
# Required for tracing
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;IngestionEndpoint=https://...

# Required for agents
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o-mini

# Optional: Foundry integration
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
```

To get the connection string:
```bash
az monitor app-insights component show \
  --resource-group rg-ai-kyc \
  --app aikyc-appi-dev \
  --query connectionString \
  --output tsv
```

## Next Steps

1. **Run validation**: `python test_tracing.py`
2. **Start server**: `python -m src.maf.server --port 8087`
3. **Send test requests** and verify traces appear
4. **Create dashboards** in Application Insights for:
   - Agent performance by role (customer vs employee)
   - Token usage trends
   - Tool call frequency
   - Error rates
5. **Set up alerts** for:
   - High error rates (> 5%)
   - Slow responses (> 5s)
   - OpenAI quota exhaustion

## Why Tracing is Critical

Without tracing, you can't:
- ❌ Debug production issues (no visibility into failures)
- ❌ Monitor performance (no latency metrics)
- ❌ Track costs (no token usage data)
- ❌ Identify bottlenecks (no dependency timing)
- ❌ Detect anomalies (no baseline for comparison)

With tracing, you can:
- ✅ See every agent invocation with full context
- ✅ Track OpenAI API usage and costs
- ✅ Identify slow tool calls
- ✅ Debug errors with full stack traces
- ✅ Monitor SLAs and set up alerts
- ✅ Optimize agent performance based on data

## Support

For issues or questions:
- Review: [docs/TRACING_AND_MONITORING.md](../docs/TRACING_AND_MONITORING.md)
- Check Application Insights: **Live Metrics** for real-time data
- Run: `python test_tracing.py` to validate configuration
- View logs in Azure Portal if data isn't appearing after 5 minutes
