# Migration to Microsoft Agent Framework (MAF)

This document describes the migration from Semantic Kernel to Microsoft Agent Framework.

## Overview

The KYC Demo application has been migrated from Semantic Kernel to Microsoft Agent Framework (MAF). MAF provides:

- **Native multi-agent orchestration** with workflows
- **Azure Foundry integration** for production deployments
- **Agent Inspector** for debugging and tracing
- **Simplified tool definitions** using `@tool` decorator
- **Streaming support** out of the box

## Architecture Changes

### Before (Semantic Kernel)

```
src/
├── agents/
│   ├── core/
│   │   ├── base_agent.py      # KycAgent base class
│   │   ├── orchestrator.py    # Custom AgentOrchestrator
│   │   └── models.py          # AgentMessage, AgentResponse
│   ├── customer/agent.py      # CustomerAgent (ChatCompletionAgent)
│   └── bank_employee/agent.py # BankEmployeeAgent
├── plugins/
│   ├── customer_data.py       # @kernel_function decorators
│   ├── kyc_verify.py
│   └── document_search.py
└── api/
    ├── main.py                # FastAPI with SK kernel
    └── websocket.py           # WebSocket handling
```

### After (Microsoft Agent Framework)

```
src/
├── maf/
│   ├── tools/
│   │   ├── customer_data.py   # @tool decorators
│   │   ├── kyc_verification.py
│   │   ├── document_search.py
│   │   ├── account_creation.py
│   │   └── inter_agent.py
│   ├── agents/
│   │   ├── customer_agent.py  # Agent instructions + tools
│   │   └── bank_employee_agent.py
│   ├── workflow.py            # KycWorkflow orchestration
│   └── server.py              # FastAPI HTTP server
└── agents/                    # Legacy SK implementation (preserved)
```

## Key Differences

### Tool Definitions

**Semantic Kernel:**
```python
from semantic_kernel.functions import kernel_function

class CustomerDataPlugin:
    @kernel_function(
        name="get_customer_by_email",
        description="Look up a customer by email"
    )
    def get_customer_by_email(self, email: str) -> str:
        ...
```

**Microsoft Agent Framework:**
```python
from agent_framework import tool

@tool
def get_customer_by_email(email: str) -> str:
    """Look up a customer by email."""
    ...
```

### Agent Creation

**Semantic Kernel:**
```python
from semantic_kernel.agents import ChatCompletionAgent
from semantic_kernel.connectors.ai.function_choice_behavior import FunctionChoiceBehavior

agent = ChatCompletionAgent(
    kernel=kernel,
    name="customer-agent",
    instructions=INSTRUCTIONS,
    function_choice_behavior=FunctionChoiceBehavior.Auto()
)
```

**Microsoft Agent Framework:**
```python
from agent_framework.azure import AzureOpenAIChatClient

client = AzureOpenAIChatClient(endpoint=endpoint, deployment_name=deployment)
agent = client.as_agent(
    name="customer-agent",
    instructions=INSTRUCTIONS,
    tools=[tool1, tool2, ...]
)
```

### Orchestration

**Semantic Kernel (custom):**
```python
class AgentOrchestrator:
    async def route_message(self, message, role):
        if role == ChatRole.CUSTOMER:
            return await self._customer_agent.process(message)
        else:
            return await self._employee_agent.process(message)
```

**Microsoft Agent Framework:**
```python
from agent_framework import Executor, WorkflowBuilder, handler

class KycAgentExecutor(Executor):
    @handler
    async def handle_message(self, input_data, ctx):
        response = await self.agent.run(...)
        await ctx.yield_output(response)
```

## Running the Application

### MAF Version (Recommended)

1. **Install dependencies:**
   ```bash
   pip install -e ".[maf]"
   # or
   pip install -r requirements-maf.txt
   ```

2. **Configure environment:**
   ```bash
   cp .env.example .env
   # Edit .env with your Foundry/Azure OpenAI settings
   ```

3. **Run the server:**
   ```bash
   python -m src.maf.server --port 8000
   ```

4. **Debug with Agent Inspector (VS Code):**
   - Press F5 and select "Debug MAF Agent Server"
   - Agent Inspector will open automatically

### Legacy SK Version

1. **Install dependencies:**
   ```bash
   pip install -e ".[sk]"
   ```

2. **Run the server:**
   ```bash
   uvicorn src.api.main:app --port 8000 --reload
   ```

## Configuration

### Environment Variables

| Variable | MAF | SK | Description |
|----------|-----|-----|-------------|
| `FOUNDRY_PROJECT_ENDPOINT` | ✅ | ❌ | Foundry project endpoint |
| `FOUNDRY_MODEL_DEPLOYMENT_NAME` | ✅ | ❌ | Foundry model deployment |
| `AZURE_OPENAI_ENDPOINT` | ✅ | ✅ | Azure OpenAI endpoint (fallback) |
| `AZURE_OPENAI_DEPLOYMENT_NAME` | ✅ | ✅ | Azure OpenAI deployment |
| `AZURE_SEARCH_ENDPOINT` | ✅ | ✅ | Azure AI Search endpoint |
| `AZURE_SEARCH_INDEX_NAME` | ✅ | ✅ | Search index name |
| `ENABLE_DOCUMENT_GROUNDING` | ✅ | ✅ | Enable document grounding |

## API Compatibility

The MAF version maintains API compatibility with the SK version:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check |
| `/api/chat` | POST | Send chat message |
| `/api/config` | GET/POST | Configuration |
| `/api/chat/clear` | POST | Clear chat history |
| `/ws/{channel}` | WS | WebSocket chat |

## Benefits of Migration

1. **Simpler code** - Less boilerplate, cleaner tool definitions
2. **Better debugging** - Agent Inspector visualizes message flow
3. **Native streaming** - Built-in streaming support
4. **Foundry integration** - Deploy to Azure Foundry with ease
5. **Future-proof** - MAF is Microsoft's strategic direction for AI agents

## Next Steps

1. **Deploy to Foundry** - Use `azd up` with updated Bicep templates
2. **Add tracing** - Integrate MAF tracing for production monitoring
3. **Evaluate agents** - Use MAF evaluation tools to measure performance
