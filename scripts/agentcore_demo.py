#!/usr/bin/env python3
"""Dry-run demo of the Bedrock AgentCore integration.

Shows the full agentic workflow without an AWS account:
  broker question → AgentCore envelope → guardrail → Bedrock tool-use loop
  (fake Bedrock client) → calculators → guardrailed answer → response envelope.

Usage:
    python scripts/agentcore_demo.py
"""
import json, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

# ── Fake Bedrock client that simulates a tool-use turn then a text answer ──
class _FakeBedrockClient:
    """Simulates one tool-use turn then a final text answer."""
    def __init__(self):
        self._call = 0

    def converse(self, *, modelId, messages, system, toolConfig, inferenceConfig):
        self._call += 1
        if self._call == 1:
            # First call: model decides to call the qualify_purchase tool
            return {
                "stopReason": "tool_use",
                "output": {"message": {
                    "role": "assistant",
                    "content": [{
                        "toolUse": {
                            "toolUseId": "tu-001",
                            "name": "qualify_purchase",
                            "input": {
                                "price": 750000,
                                "down_payment": 150000,
                                "annual_income": 120000,
                                "contract_rate": 4.79,
                                "property_tax_annual": 4800,
                                "other_debt_monthly": 0,
                                "amort_years": 25,
                                "first_time_buyer": True,
                                "new_build": False,
                            }
                        }
                    }]
                }}
            }
        else:
            # Second call: model returns a human-readable answer
            return {
                "stopReason": "end_turn",
                "output": {"message": {
                    "role": "assistant",
                    "content": [{"text": (
                        "Based on the qualification tool result: at a qualifying rate of 6.79% "
                        "(contract 4.79% + 2%), the GDS is approximately 31.4% and TDS 31.4%, "
                        "which falls within typical lender limits for a prime borrower. "
                        "A licensed broker should confirm with the specific lender."
                    )}]
                }}
            }


def main():
    import unittest.mock as mock
    from mortgageloanops.agentcore import handle

    question = "Can a borrower qualify for $750,000 at 4.79% with $120,000 income and $150,000 down?"
    session_id = "demo-session-001"

    print("=" * 70)
    print("MortgageLoanOps — Bedrock AgentCore dry-run demo")
    print("=" * 70)
    print(f"\nBroker question: {question}\n")

    os.environ["MLO_BEDROCK_MODEL_ID"] = "amazon.nova-micro-v1:0"

    with mock.patch("mortgageloanops.agentcore.Agent") as MockAgent:
        fake_client = _FakeBedrockClient()
        real_agent_cls = MockAgent.__class__  # keep real class accessible
        instance = mock.MagicMock()

        # Replicate what Agent.ask() does but with our fake client
        from mortgageloanops.agent import Agent as RealAgent, run_tool
        real_agent = RealAgent(client=fake_client, model_id="amazon.nova-micro-v1:0")
        instance.ask.side_effect = lambda q: real_agent.ask(q)
        MockAgent.return_value = instance

        response = handle({"inputText": question, "sessionId": session_id})

    print("AgentCore response envelope:")
    print(json.dumps({
        "messageVersion": response["messageVersion"],
        "sessionId": response["sessionId"],
        "response": response["response"],
        "tool_calls_count": len(response.get("toolCallsSummary", [])),
    }, indent=2))

    tool_calls = response.get("toolCallsSummary", [])
    if tool_calls:
        print(f"\nTool calls made ({len(tool_calls)}):")
        for tc in tool_calls:
            print(f"  → {tc['name']}({json.dumps(tc['input'], separators=(',',':'))})")
            result_preview = json.dumps(tc['output'])[:120]
            print(f"    ← {result_preview}...")

    print("\nAnswer delivered to broker:")
    print(" ", response["response"]["responseBody"]["TEXT"]["body"])
    print("\n✓ End-to-end agentic flow complete (dry-run; no AWS account needed)")
    print("  Deploy with: sam deploy --guided")

if __name__ == "__main__":
    main()
