"""Quick test script to verify Application Insights tracing is configured.

Run this script to validate that:
1. Application Insights connection string is set
2. OpenTelemetry instrumentation loads correctly
3. Traces are being sent to Azure Monitor

Usage:
    python test_tracing.py
"""

import os
import sys
from dotenv import load_dotenv

print("=" * 70)
print("Agent Tracing Configuration Test")
print("=" * 70)

# Load environment
load_dotenv()

# Test 1: Connection String
print("\n[Test 1] Checking APPLICATIONINSIGHTS_CONNECTION_STRING...")
conn_str = os.getenv("APPLICATIONINSIGHTS_CONNECTION_STRING")
if conn_str:
    # Mask the key for security
    masked = conn_str[:50] + "..." + conn_str[-30:] if len(conn_str) > 80 else conn_str[:20] + "..."
    print(f"  ✅ FOUND: {masked}")
else:
    print("  ❌ NOT SET - Traces will not be sent to Application Insights")
    print("     Add APPLICATIONINSIGHTS_CONNECTION_STRING to your .env file")
    sys.exit(1)

# Test 2: Import OpenTelemetry packages
print("\n[Test 2] Checking OpenTelemetry packages...")
try:
    from azure.monitor.opentelemetry import configure_azure_monitor
    print("  ✅ azure-monitor-opentelemetry is installed")
except ImportError as e:
    print(f"  ❌ azure-monitor-opentelemetry NOT installed: {e}")
    print("     Run: pip install azure-monitor-opentelemetry>=1.4.0")
    sys.exit(1)

try:
    from opentelemetry.instrumentation.openai_v2 import OpenAIInstrumentor
    print("  ✅ opentelemetry-instrumentation-openai-v2 is installed")
except ImportError as e:
    print(f"  ❌ opentelemetry-instrumentation-openai-v2 NOT installed: {e}")
    print("     Run: pip install opentelemetry-instrumentation-openai-v2")
    sys.exit(1)

try:
    from opentelemetry import trace
    print("  ✅ opentelemetry-api is installed")
except ImportError as e:
    print(f"  ❌ opentelemetry-api NOT installed: {e}")
    sys.exit(1)

# Test 3: Configure Azure Monitor (dry run)
print("\n[Test 3] Configuring Azure Monitor...")
try:
    configure_azure_monitor(
        connection_string=conn_str,
        enable_live_metrics=True,
    )
    print("  ✅ Azure Monitor configured successfully")
except Exception as e:
    print(f"  ❌ Failed to configure Azure Monitor: {e}")
    sys.exit(1)

# Test 4: Instrument OpenAI
print("\n[Test 4] Instrumenting OpenAI SDK...")
try:
    OpenAIInstrumentor().instrument()
    print("  ✅ OpenAI instrumentation enabled")
except Exception as e:
    print(f"  ⚠️  OpenAI instrumentation failed (non-critical): {e}")

# Test 5: Create a test span
print("\n[Test 5] Creating test trace span...")
try:
    tracer = trace.get_tracer("test-tracer")
    with tracer.start_as_current_span("test-span") as span:
        span.set_attribute("test.attribute", "test-value")
        span.add_event("test-event")
    print("  ✅ Test span created (check Application Insights in 2-3 minutes)")
except Exception as e:
    print(f"  ❌ Failed to create test span: {e}")
    sys.exit(1)

# Test 6: Check Azure OpenAI configuration
print("\n[Test 6] Checking Azure OpenAI configuration...")
aoai_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
aoai_deployment = os.getenv("AZURE_OPENAI_DEPLOYMENT_NAME")

if aoai_endpoint and aoai_deployment:
    print(f"  ✅ AZURE_OPENAI_ENDPOINT: {aoai_endpoint}")
    print(f"  ✅ AZURE_OPENAI_DEPLOYMENT_NAME: {aoai_deployment}")
else:
    print("  ⚠️  Azure OpenAI configuration incomplete")
    if not aoai_endpoint:
        print("     Missing: AZURE_OPENAI_ENDPOINT")
    if not aoai_deployment:
        print("     Missing: AZURE_OPENAI_DEPLOYMENT_NAME")

# Summary
print("\n" + "=" * 70)
print("✅ All critical tests passed!")
print("=" * 70)
print("\nNext steps:")
print("  1. Start the MAF server:")
print("     python -m src.maf.server --port 8087")
print("\n  2. Send test requests:")
print('     curl -X POST http://localhost:8087/api/chat \\')
print('       -H "Content-Type: application/json" \\')
print('       -d \'{"message": "Hello", "role": "customer"}\'')
print("\n  3. View traces in Azure Portal:")
print("     Application Insights → Transaction search")
print("     Wait 2-3 minutes for data propagation")
print("\n  4. Use Live Metrics for real-time monitoring:")
print("     Application Insights → Live metrics")
print()
