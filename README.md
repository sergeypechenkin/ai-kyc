# AI-KYC Demo Application

A demonstration application showcasing a KYC (Know Your Customer) workflow using Microsoft Semantic Kernel's multi-agent architecture.

## Features

- **Dual Chat Interface**: Separate chat windows for Customer and Bank Employee roles
- **Multi-Agent System**: Customer Agent and Bank Employee Agent that communicate with each other
- **Real-time Activity Logging**: Detailed view of agent internals (tool calls, inter-agent messages, token usage)
- **Document Grounding**: Toggle-able RAG capability using Azure AI Search for bank documentation
- **Extensible Architecture**: Designed for adding future agents (Audit, PEP Screening, Document Extraction)

## Architecture

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────────────┐
│  Customer Chat  │     │ Employee Chat   │     │  Activity Log Window    │
└────────┬────────┘     └────────┬────────┘     └────────────┬────────────┘
         │                       │                           │
         └───────────────────────┼───────────────────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   FastAPI + WebSocket   │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Agent Orchestrator    │
                    │  ┌─────────┐ ┌────────┐ │
                    │  │Customer │◄►│ Bank   │ │
                    │  │ Agent   │ │Employee│ │
                    │  └─────────┘ └────────┘ │
                    └────────────┬────────────┘
                                 │
                    ┌────────────▼────────────┐
                    │   Shared Plugins        │
                    │   Azure AI Search       │
                    │   Mock Data Service     │
                    └─────────────────────────┘
```

## Quick Start

### Prerequisites

- Python 3.11+
- Node.js 18+
- Azure OpenAI deployment (gpt-4o or gpt-4o-mini)
- Azure Application Insights (for tracing)
- Azure AI Search (optional, for document grounding)

### Setup

1. Clone and install dependencies:
   ```bash
   cd ai-kyc
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install -r requirements-maf.txt
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your Azure credentials:
   # - AZURE_OPENAI_ENDPOINT
   # - AZURE_OPENAI_DEPLOYMENT_NAME
   # - APPLICATIONINSIGHTS_CONNECTION_STRING (required for tracing)
   # - FOUNDRY_PROJECT_ENDPOINT (optional)
   ```

3. **Validate tracing configuration** (important!):
   ```bash
   python test_tracing.py
   ```
   
   You should see:
   ```
   ✅ All critical tests passed!
   ```

4. Start the MAF backend:
   ```bash
   python -m src.maf.server --port 8087
   ```
   
   Look for these startup messages:
   ```
   [OK] Application Insights configured
   [OK] OpenAI instrumentation enabled
   [OK] MAF Workflow initialized
   ```

5. Start the frontend:
   ```bash
   
   npm install
   cd web && npm run dev
   ```

6. Open http://localhost:5173

### Quick Start/Stop Scripts

For convenience, use these PowerShell scripts:

```bash
# Start both backend and frontend
.\start.ps1

# Stop all running instances
.\stop.ps1

# Restart everything (stop + start)
.\restart.ps1
```

### Verifying Tracing Works

After starting the server and sending test requests:

1. **Real-time**: Azure Portal → Application Insights → Live Metrics
2. **Historical**: Azure Portal → Application Insights → Transaction search (wait 2-3 minutes)
3. **Queries**: Azure Portal → Application Insights → Logs (KQL)

See [docs/TRACING_AND_MONITORING.md](docs/TRACING_AND_MONITORING.md) for detailed instructions.

## Project Structure

```
ai-kyc/
├── src/
│   ├── maf/                    # Microsoft Agent Framework (MAF) implementation
│   │   ├── server.py           # FastAPI server with OpenTelemetry
│   │   ├── workflow.py         # Multi-agent orchestration
│   │   ├── telemetry.py        # Tracing helpers
│   │   ├── agents/             # Agent definitions
│   │   └── tools/              # Agent tools (search, KYC, etc.)
│   ├── api/                    # Legacy Semantic Kernel backend
│   ├── agents/                 # Legacy SK agents
│   ├── plugins/                # Legacy SK plugins
│   └── infrastructure/         # Azure clients, mock data service
├── web/                        # React frontend
├── data/
│   ├── mock/                   # CSV files for demo data
│   └── bank-documents/         # PDFs for document grounding
├── docs/
│   ├── TRACING_AND_MONITORING.md     # Comprehensive tracing guide
│   └── TRACING_IMPLEMENTATION.md     # Implementation summary
├── tools/                      # Ingestion scripts
├── infra/                      # Bicep templates (includes App Insights)
├── start.ps1                   # Start backend + frontend
├── stop.ps1                    # Stop all services
├── restart.ps1                 # Restart all services
├── test_tracing.py             # Validation script
└── quick_test_tracing.ps1      # End-to-end test script
```

## Monitoring and Observability

This application includes comprehensive tracing and monitoring using Azure Application Insights and OpenTelemetry.

### What's Traced

- **Agent Operations**: Every agent invocation with role, model, prompt/completion lengths
- **OpenAI API Calls**: All LLM requests with token usage, cost tracking
- **Tool Invocations**: Each tool call with arguments, duration, results
- **HTTP Requests**: All API endpoints with latency, status codes
- **Errors**: Full exception traces with context

### Quick Test

```bash
# Validate tracing configuration
python test_tracing.py

# Run end-to-end test (starts server, sends requests, checks health)
.\quick_test_tracing.ps1
```

### Viewing Traces

**Live Metrics (Real-time)**
```
Azure Portal → Application Insights → Live Metrics
```

**Transaction Search (Historical)**
```
Azure Portal → Application Insights → Transaction search
Filter: Last 30 minutes, Operation Name: "agent.chat"
```

**KQL Queries**
```kusto
// Agent operations
traces
| where customDimensions.SpanName startswith "agent."
| order by timestamp desc

// OpenAI token usage
dependencies
| where type == "openai"
| extend tokens = toint(customDimensions['gen_ai.usage.total_tokens'])
| summarize sum(tokens) by bin(timestamp, 1h)
```

**Full Guide**: [docs/TRACING_AND_MONITORING.md](docs/TRACING_AND_MONITORING.md)

## Adding New Agents

```python
from src.agents.core import KycAgent, kyc_agent, AgentCapability

@kyc_agent
class AuditAgent(KycAgent):
    name = "audit-agent"
    description = "Audit Agent for compliance"
    capabilities = [AgentCapability.AUDIT_TRAIL]

    async def process(self, message):
        # Implementation
        ...
```

## License

MIT
