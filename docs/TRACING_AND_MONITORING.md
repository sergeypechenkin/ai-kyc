# Agent Tracing and Monitoring Guide

This guide explains how to enable and verify agent tracing and monitoring in the AI-KYC application using Azure Application Insights and OpenTelemetry.

## Overview

The application uses:
- **Azure Application Insights** - Cloud-based monitoring service for telemetry aggregation
- **OpenTelemetry** - Industry-standard tracing instrumentation framework
- **Microsoft Agent Framework (MAF)** - Agent runtime with built-in telemetry support

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    MAF Agent Application                         │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐         │
│  │  Customer    │  │  Employee    │  │    Tools     │         │
│  │    Agent     │  │    Agent     │  │  (search,    │         │
│  │              │  │              │  │   KYC, etc)  │         │
│  └──────┬───────┘  └──────┬───────┘  └──────┬───────┘         │
│         │                  │                  │                  │
│         └──────────────────┴──────────────────┘                  │
│                             │                                     │
│                    ┌────────▼────────┐                           │
│                    │  OpenTelemetry  │                           │
│                    │  Instrumentation│                           │
│                    └────────┬────────┘                           │
└─────────────────────────────┼─────────────────────────────────────┘
                              │
                              │ Traces, Spans, Metrics
                              ▼
                    ┌─────────────────────┐
                    │ Azure Application   │
                    │     Insights        │
                    │                     │
                    │  • Distributed      │
                    │    Tracing          │
                    │  • Performance      │
                    │  • Dependencies     │
                    │  • Custom Events    │
                    └─────────────────────┘
```

## Configuration

### 1. Required Azure Resources

Ensure these resources exist in `rg-ai-kyc` resource group:

- **Azure OpenAI Service** - For agent LLM inference
- **Log Analytics Workspace** - Stores telemetry data
- **Application Insights** - Monitoring and analytics interface

The Bicep template ([infra/main.bicep](../infra/main.bicep)) creates these automatically.

### 2. Environment Variables

In your `.env` file, configure:

```bash
# ===== REQUIRED FOR TRACING =====
APPLICATIONINSIGHTS_CONNECTION_STRING=InstrumentationKey=...;IngestionEndpoint=https://...

# ===== AZURE OPENAI =====
AZURE_OPENAI_ENDPOINT=https://<resource>.openai.azure.com/
AZURE_OPENAI_DEPLOYMENT_NAME=gpt-4o

# ===== OPTIONAL: Foundry Integration =====
FOUNDRY_PROJECT_ENDPOINT=https://<resource>.services.ai.azure.com/api/projects/<project>
```

#### Getting the Connection String

**Option 1: Azure Portal**
1. Navigate to your Application Insights resource
2. Go to **Settings → Properties**
3. Copy **Connection String**

**Option 2: Azure CLI**
```bash
az monitor app-insights component show \
  --resource-group rg-ai-kyc \
  --app aikyc-appi-dev \
  --query connectionString \
  --output tsv
```

**Option 3: From Bicep deployment output**
```bash
az deployment group show \
  --resource-group rg-ai-kyc \
  --name main \
  --query properties.outputs.appInsightsConnectionString.value \
  --output tsv
```

### 3. Install Required Packages

The application requires these OpenTelemetry packages:

```bash
pip install -r requirements-maf.txt
```

Key packages:
- `azure-monitor-opentelemetry>=1.4.0` - Azure Monitor exporter
- `opentelemetry-instrumentation-openai>=0.24.0` - OpenAI SDK instrumentation

## How It Works

### Automatic Instrumentation

The server ([src/maf/server.py](../src/maf/server.py)) automatically configures OpenTelemetry on startup:

```python
app_insights_conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if app_insights_conn_str:
    from azure.monitor.opentelemetry import configure_azure_monitor
    configure_azure_monitor(
        connection_string=app_insights_conn_str,
        enable_live_metrics=True,
    )
    
    # Enable OpenAI instrumentation
    from opentelemetry.instrumentation.openai import OpenAIInstrumentor
    OpenAIInstrumentor().instrument()
```

This captures:
- **HTTP requests** to the API
- **OpenAI API calls** (prompts, completions, token usage)
- **Custom spans** from agent operations
- **Exceptions** and errors

### Custom Agent Tracing

The workflow ([src/maf/workflow.py](../src/maf/workflow.py)) adds custom spans for agent operations:

```python
with track_agent_operation(
    agent_name="customer-agent",
    operation="chat",
    attributes={
        "gen_ai.system": "azure_openai",
        "gen_ai.agent.name": "customer-agent",
        "gen_ai.request.model": "gpt-4o",
        "gen_ai.prompt_length": len(message),
    },
) as span:
    response = await agent.run(conversation_history)
    span.set_attribute("gen_ai.completion_length", len(response_text))
```

### Tool Call Tracking

Tools are automatically traced using the `@track_tool_call` decorator ([src/maf/telemetry.py](../src/maf/telemetry.py)):

```python
@track_tool_call("search_documents")
async def search_bank_documents(query: str) -> str:
    # Tool implementation
    ...
```

Each tool invocation creates a span with:
- Tool name and arguments
- Execution duration
- Result length
- Success/failure status

## Verifying Tracing

### 1. Start the Application

```bash
python -m src.maf.server --port 8087
```

Expected output:
```
[OK] Application Insights configured
[OK] OpenAI instrumentation enabled
[INFO] Using DefaultAzureCredential for Azure OpenAI
[OK] MAF Workflow initialized
INFO:     Application startup complete.
```

### 2. Send Test Messages

**Customer chat:**
```bash
curl -X POST http://localhost:8087/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "I want to open a business account",
    "role": "customer"
  }'
```

**Employee chat:**
```bash
curl -X POST http://localhost:8087/api/chat \
  -H "Content-Type: application/json" \
  -d '{
    "message": "Show me pending verifications",
    "role": "employee"
  }'
```

### 3. View Traces in Application Insights

**Portal: Transaction Search**
1. Open Azure Portal → Application Insights resource
2. Navigate to **Investigate → Transaction search**
3. Filter by:
   - **Operation Name**: `agent.chat`, `agent.customer`, `tool.*`
   - **Dependency Type**: `openai`
   - **Time Range**: Last 30 minutes

**Portal: Application Map**
1. Navigate to **Investigate → Application map**
2. See dependencies: `FastAPI → Azure OpenAI`
3. Click nodes to see performance metrics

**Portal: Performance**
1. Navigate to **Investigate → Performance**
2. Select **Operations** tab
3. Sort by **Count** or **Average Duration**
4. Look for:
   - `/api/chat` - HTTP requests
   - `agent.chat` - Agent operations
   - `tool.search_documents` - Tool calls

### 4. Query with KQL

Use **Logs** (KQL editor) for advanced queries:

**All agent operations:**
```kusto
traces
| where customDimensions.SpanName startswith "agent."
| project timestamp, message, customDimensions
| order by timestamp desc
| take 50
```

**OpenAI API calls with token usage:**
```kusto
dependencies
| where type == "openai"
| extend model = tostring(customDimensions['gen_ai.request.model'])
| extend prompt_tokens = toint(customDimensions['gen_ai.usage.prompt_tokens'])
| extend completion_tokens = toint(customDimensions['gen_ai.usage.completion_tokens'])
| project timestamp, name, duration, model, prompt_tokens, completion_tokens
| order by timestamp desc
```

**Tool invocations:**
```kusto
traces
| where customDimensions.SpanName startswith "tool."
| extend tool_name = tostring(customDimensions['tool.name'])
| extend duration_ms = toreal(customDimensions['duration_ms'])
| summarize count(), avg(duration_ms) by tool_name
| order by count_ desc
```

**Error tracking:**
```kusto
exceptions
| union (traces | where severityLevel >= 3)
| project timestamp, message, severityLevel, customDimensions
| order by timestamp desc
| take 20
```

## Troubleshooting

### No Traces Appearing

**Check 1: Connection String**
```bash
# Verify the env var is set
echo $env:APPLICATIONINSIGHTS_CONNECTION_STRING

# Should output: InstrumentationKey=...;IngestionEndpoint=...
```

If empty, ensure:
- `.env` file exists in project root
- `APPLICATIONINSIGHTS_CONNECTION_STRING` is set
- Server was restarted after updating `.env`

**Check 2: Server Logs**
Look for startup messages:
```
[OK] Application Insights configured
[OK] OpenAI instrumentation enabled
```

If you see:
```
[WARN] APPLICATIONINSIGHTS_CONNECTION_STRING not set; traces will not be sent
```
→ Connection string is missing from `.env`

**Check 3: Data Latency**
- Application Insights has 1-2 minute ingestion delay
- Wait 2-5 minutes after sending requests
- Use **Live Metrics** for real-time monitoring

**Check 4: Azure Resource Health**
```bash
az monitor app-insights component show \
  --resource-group rg-ai-kyc \
  --app aikyc-appi-dev \
  --query provisioningState
```
Should return: `"Succeeded"`

### Traces Missing for Specific Operations

**OpenAI calls not traced:**
```python
# Verify OpenAI instrumentation is enabled
from opentelemetry.instrumentation.openai import OpenAIInstrumentor
print(OpenAIInstrumentor().is_instrumented_by_opentelemetry)
# Should print: True
```

**Custom spans not appearing:**
Check that `track_agent_operation` context manager is used:
```python
# ✅ Correct
with track_agent_operation("agent", "chat") as span:
    result = await agent.run(...)

# ❌ Missing tracing
result = await agent.run(...)
```

### High Data Volume / Cost

**Sampling Configuration**
To reduce telemetry volume, configure sampling in [src/maf/server.py](../src/maf/server.py):

```python
configure_azure_monitor(
    connection_string=app_insights_conn_str,
    enable_live_metrics=True,
    sampling_ratio=0.1,  # Sample 10% of traces
)
```

**Disable Verbose Tracing**
Set environment variable:
```bash
OTEL_TRACES_SAMPLER=parentbased_traceidratio
OTEL_TRACES_SAMPLER_ARG=0.1
```

## Live Metrics

For real-time monitoring during development:

1. Open Application Insights → **Investigate → Live Metrics**
2. Start the server
3. Send test requests
4. Watch metrics in real-time:
   - Request rate
   - Response time
   - Failure rate
   - Dependencies (OpenAI calls)

## Best Practices

1. **Always set connection string in production** - Without it, you're blind to issues
2. **Use consistent span naming** - Prefix with operation type (`agent.`, `tool.`, etc.)
3. **Add context attributes** - Include customer IDs, agent names, model versions
4. **Don't log PII** - Truncate prompts/completions to avoid sensitive data
5. **Monitor token usage** - Track OpenAI costs via custom metrics
6. **Set up alerts** - Create alerts for high error rates or latency

## Next Steps

1. **Deploy Infrastructure**:
   ```bash
   az deployment group create \
     --resource-group rg-ai-kyc \
     --template-file infra/main.bicep
   ```

2. **Update .env** with connection string from deployment output

3. **Restart the server** and verify tracing

4. **Create dashboards** in Application Insights for:
   - Agent performance metrics
   - Token usage by agent
   - Tool call frequency
   - Error rates by operation

5. **Set up alerts** for:
   - High error rates (> 5%)
   - Slow responses (> 5s)
   - OpenAI quota exhaustion

## Additional Resources

- [Application Insights Overview](https://learn.microsoft.com/en-us/azure/azure-monitor/app/app-insights-overview)
- [OpenTelemetry Python Instrumentation](https://opentelemetry.io/docs/languages/python/)
- [Azure Monitor OpenTelemetry](https://learn.microsoft.com/en-us/azure/azure-monitor/app/opentelemetry-enable?tabs=python)
- [KQL Quick Reference](https://learn.microsoft.com/en-us/azure/data-explorer/kql-quick-reference)
