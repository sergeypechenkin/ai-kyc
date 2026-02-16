"""
Deploy agents to Azure AI Foundry.
"""

import os
from dotenv import load_dotenv
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from azure.ai.projects.models import PromptAgentDefinition, FunctionTool

load_dotenv()


def deploy_to_foundry():
    """Deploy KYC agents to Azure AI Foundry."""
    
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    model = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME", "gpt-4o-mini")
    
    print(f"Connecting to Foundry: {endpoint}")
    
    credential = DefaultAzureCredential()
    client = AIProjectClient(credential=credential, endpoint=endpoint)
    
    # Customer Agent tools
    customer_tools = [
        FunctionTool(
            name="get_customer_profile",
            description="Get customer profile by ID or email",
            parameters={"type": "object", "properties": {"customer_id": {"type": "string"}, "email": {"type": "string"}}},
        ),
        FunctionTool(
            name="search_bank_documents",
            description="Search bank policy documents",
            parameters={"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]},
        ),
    ]
    
    # Employee Agent tools
    employee_tools = [
        FunctionTool(
            name="get_pending_verifications",
            description="Get pending KYC verifications",
            parameters={"type": "object", "properties": {"status": {"type": "string"}, "limit": {"type": "integer"}}},
        ),
        FunctionTool(
            name="approve_verification",
            description="Approve KYC verification",
            parameters={"type": "object", "properties": {"verification_id": {"type": "string"}, "notes": {"type": "string"}}, "required": ["verification_id"]},
        ),
    ]
    
    # Customer Agent definition
    customer_definition = PromptAgentDefinition(
        model=model,
        instructions="""You are a helpful banking assistant for Zava Bank.

You help customers with:
- Opening new bank accounts
- Uploading identity documents (passport, driver's license, ID card)
- Checking KYC verification status
- Answering questions about bank products and services

Guidelines:
- Always be professional, friendly, and helpful
- Guide customers through the account opening process step by step
- Explain what documents are needed and why
- Never ask for sensitive information like passwords or full SSN""",
        tools=customer_tools,
    )
    
    # Employee Agent definition
    employee_definition = PromptAgentDefinition(
        model=model,
        instructions="""You are an AI assistant for Zava Bank employees handling KYC verification.

You help bank employees with:
- Reviewing pending KYC verification requests
- Approving or rejecting customer documents
- Checking compliance status and requirements
- Searching bank policies and procedures

Guidelines:
- Present verification requests clearly with all relevant details
- Highlight any potential issues or red flags
- Follow bank compliance policies strictly""",
        tools=employee_tools,
    )

    print("\nCreating Customer Agent...")
    customer_agent = client.agents.create(
        name="kyc-customer-agent",
        definition=customer_definition,
        description="Customer-facing agent for KYC onboarding",
    )
    print(f"  [OK] ID: {customer_agent.id}")
    
    print("\nCreating Employee Agent...")
    employee_agent = client.agents.create(
        name="kyc-employee-agent",
        definition=employee_definition,
        description="Bank employee agent for KYC verification",
    )
    print(f"  [OK] ID: {employee_agent.id}")
    
    # Save to .env
    with open(".env", "a") as f:
        f.write(f"\n# Foundry Agent IDs\nFOUNDRY_CUSTOMER_AGENT_ID={customer_agent.id}\nFOUNDRY_EMPLOYEE_AGENT_ID={employee_agent.id}\n")
    
    print("\n[OK] Agent IDs saved to .env")


def list_agents():
    endpoint = os.getenv("FOUNDRY_PROJECT_ENDPOINT")
    client = AIProjectClient(credential=DefaultAzureCredential(), endpoint=endpoint)
    print("Agents in Foundry:")
    for agent in client.agents.list():
        print(f"  - {agent.name}: {agent.id}")


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "list":
        list_agents()
    else:
        deploy_to_foundry()