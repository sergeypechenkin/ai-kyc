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
- Azure OpenAI deployment (gpt-5-mini)
- Azure AI Search (optional, for document grounding)

### Setup

1. Clone and install dependencies:
   ```bash
   cd ai-kyc
   python -m venv .venv
   .venv\Scripts\activate  # Windows
   pip install -e ".[dev]"
   ```

2. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env with your Azure credentials
   ```

3. Start the backend:
   ```bash
   uvicorn src.api.main:app --reload --port 8000
   ```

4. Start the frontend:
   ```bash
   cd web
   npm install
   npm run dev
   ```

5. Open http://localhost:5173

## Project Structure

```
ai-kyc/
├── src/
│   ├── api/                    # FastAPI backend
│   ├── agents/
│   │   ├── core/               # Base abstractions, registry, orchestrator
│   │   ├── customer/           # Customer Agent
│   │   └── bank_employee/      # Bank Employee Agent
│   ├── plugins/                # Semantic Kernel plugins
│   └── infrastructure/         # Azure clients, mock data service
├── web/                        # React frontend
├── data/
│   ├── mock/                   # CSV files for demo data
│   └── bank-documents/         # PDFs for document grounding
├── tools/                      # Ingestion scripts
└── infra/                      # Bicep templates
```

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
