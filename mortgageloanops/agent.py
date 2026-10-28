"""Bedrock agent: an LLM that answers broker/borrower questions by CALLING the real calculators.

Uses the Amazon Bedrock Runtime Converse API with tool use ('bedrock-runtime'.converse). The model never
computes mortgage numbers itself; it must call a tool, and tool results are what it reports. This is a
Converse tool-use loop, not the AgentCore runtime. Set MLO_BEDROCK_MODEL_ID to a model you have access to.
"""
from __future__ import annotations

import json
import os

from . import qualify, ird, homevalue, guardrail

TOOLS = {
    "qualify_purchase": {
        "description": "Run the B-20 stress test and GDS/TDS for a purchase. Returns qualifying rate, payments, ratios, pass/fail and reasons.",
        "schema": {"type": "object", "properties": {
            "price": {"type": "number"}, "down_payment": {"type": "number"}, "annual_income": {"type": "number"},
            "contract_rate": {"type": "number", "description": "percent, e.g. 4.5"},
            "property_tax_annual": {"type": "number"}, "other_debt_monthly": {"type": "number"},
            "amort_years": {"type": "integer"}, "first_time_buyer": {"type": "boolean"}, "new_build": {"type": "boolean"}},
            "required": ["price", "down_payment", "annual_income", "contract_rate"]},
        "fn": lambda a: qualify.qualify(**a).to_dict(),
    },
    "estimate_prepayment_penalty": {
        "description": "Estimate the penalty to break a mortgage (greater of 3 months interest and IRD) and whether refinancing pays off.",
        "schema": {"type": "object", "properties": {
            "balance": {"type": "number"}, "contract_rate": {"type": "number"}, "months_remaining": {"type": "number"},
            "is_variable": {"type": "boolean"}, "comparison_rate": {"type": "number"},
            "original_posted_rate": {"type": "number"}, "current_posted_rate": {"type": "number"},
            "new_rate": {"type": "number"}, "amort_years_remaining": {"type": "number"}},
            "required": ["balance", "contract_rate", "months_remaining"]},
        "fn": lambda a: _penalty(a),
    },
    "estimate_home_value": {
        "description": "Indicative home value from purchase price, purchase year/month and postal code (not an appraisal).",
        "schema": {"type": "object", "properties": {
            "purchase_price": {"type": "number"}, "purchase_year": {"type": "integer"}, "purchase_month": {"type": "integer"},
            "postal_code": {"type": "string"}, "renovation_spend": {"type": "number"}},
            "required": ["purchase_price", "purchase_year", "purchase_month", "postal_code"]},
        "fn": lambda a: homevalue.indexed_value(**a),
    },
}

SYSTEM = ("You assist a licensed Canadian mortgage broker's team. ALWAYS use the provided tools for any number; never do mortgage "
          "arithmetic yourself. You are not the broker: do not quote rates, promise approval, or guarantee outcomes. Say that figures are "
          "estimates for a licensed broker to confirm.")


def _penalty(a: dict) -> dict:
    a = dict(a)
    new_rate = a.pop("new_rate", None); am = a.pop("amort_years_remaining", None)
    p = ird.penalty(**a)
    out = {"penalty": p.to_dict()}
    if new_rate is not None and am is not None:
        out["refinance"] = ird.refinance_analysis(balance=a["balance"], current_rate=a["contract_rate"], new_rate=new_rate,
                                                  months_remaining=a["months_remaining"], amort_years_remaining=am, penalty_amount=p.penalty)
    return out


def tool_config() -> dict:
    return {"tools": [{"toolSpec": {"name": n, "description": t["description"], "inputSchema": {"json": t["schema"]}}} for n, t in TOOLS.items()]}


def run_tool(name: str, args: dict) -> dict:
    if name not in TOOLS:
        return {"error": f"unknown tool {name}"}
    try:
        return TOOLS[name]["fn"](args)
    except (ValueError, TypeError, KeyError) as e:
        return {"error": f"{type(e).__name__}: {e}"}


class Agent:
    def __init__(self, client=None, model_id: str | None = None, region: str | None = None, max_turns: int = 6):
        self.model_id = model_id or os.environ.get("MLO_BEDROCK_MODEL_ID")
        if not self.model_id:
            raise RuntimeError("set MLO_BEDROCK_MODEL_ID to a Bedrock model you have access to")
        if client is None:
            import boto3
            client = boto3.client("bedrock-runtime", region_name=region or os.environ.get("AWS_REGION", "ca-central-1"))
        self.client, self.max_turns = client, max_turns

    def ask(self, question: str) -> dict:
        messages = [{"role": "user", "content": [{"text": question}]}]
        tool_calls = []
        for _ in range(self.max_turns):
            resp = self.client.converse(modelId=self.model_id, messages=messages, system=[{"text": SYSTEM}], toolConfig=tool_config(),
                                        inferenceConfig={"maxTokens": 800, "temperature": 0})
            msg = resp["output"]["message"]; messages.append(msg)
            if resp.get("stopReason") != "tool_use":
                text = "".join(b.get("text", "") for b in msg["content"])
                g = guardrail.check(text)
                return {"answer": text if g["allowed"] else "I can't share that in a message; a licensed broker will follow up.",
                        "_raw_answer": text,
                        "guardrail": g, "tool_calls": tool_calls}
            results = []
            for b in msg["content"]:
                if "toolUse" in b:
                    tu = b["toolUse"]; out = run_tool(tu["name"], tu["input"])
                    tool_calls.append({"name": tu["name"], "input": tu["input"], "output": out})
                    results.append({"toolResult": {"toolUseId": tu["toolUseId"], "content": [{"json": json.loads(json.dumps(out, default=str))}]}})
            messages.append({"role": "user", "content": results})
        return {"answer": "I couldn't finish that; a broker will follow up.", "guardrail": {"allowed": True, "violations": []}, "tool_calls": tool_calls}
