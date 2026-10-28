"""AWS Bedrock AgentCore compatibility layer for MortgageLoanOps.

AgentCore invokes a Lambda function with a structured envelope and expects a matching response.
This module wraps the existing Bedrock Converse Agent (agent.py) in that envelope so the same
mortgage-calculator tool-use loop can be registered and invoked as a Bedrock AgentCore agent.

Reference: https://docs.aws.amazon.com/bedrock/latest/userguide/agents-core.html
"""
from __future__ import annotations

import json
import logging
import os
from typing import Any

from . import guardrail
from .agent import Agent, run_tool, tool_config, SYSTEM

logger = logging.getLogger(__name__)

# AgentCore envelope keys
_INPUT_KEY = "inputText"        # the user's natural-language question
_SESSION_KEY = "sessionId"      # propagated back in the response
_ACTION_GROUP = "mortgageLoanOpsActionGroup"


def _format_response(session_id: str, text: str, tool_calls: list[dict]) -> dict:
    """Return the AgentCore Lambda response envelope."""
    return {
        "messageVersion": "1.0",
        "sessionId": session_id,
        "response": {
            "actionGroup": _ACTION_GROUP,
            "responseBody": {
                "TEXT": {"body": text}
            },
        },
        "toolCallsSummary": tool_calls,
    }


def handle(event: dict, context: Any = None) -> dict:
    """AgentCore Lambda entry point.

    AgentCore passes:
        {
          "inputText": "<user question>",
          "sessionId": "<uuid>",
          "agentId": "...",
          "agentAliasId": "...",
          "sessionAttributes": {},
          "promptSessionAttributes": {}
        }
    """
    session_id = event.get(_SESSION_KEY, "no-session")
    question = event.get(_INPUT_KEY, "").strip()

    if not question:
        return _format_response(session_id, "No question provided.", [])

    # Guard the incoming question too
    g_in = guardrail.check(question)
    if not g_in["allowed"]:
        safe = guardrail.safe_replacement()
        return _format_response(session_id, safe, [])

    model_id = os.environ.get("MLO_BEDROCK_MODEL_ID")
    if not model_id:
        return _format_response(session_id, "Agent not configured: set MLO_BEDROCK_MODEL_ID.", [])

    try:
        agent = Agent(model_id=model_id)
        result = agent.ask(question)
        return _format_response(session_id, result["answer"], result.get("tool_calls", []))
    except Exception as exc:  # pylint: disable=broad-except
        logger.exception("AgentCore handler error")
        return _format_response(session_id, "An error occurred; a licensed broker will follow up.", [])


class AgentCoreApp:
    """Convenience wrapper used in local development and tests.

    Usage::

        app = AgentCoreApp(model_id="amazon.nova-micro-v1:0")
        response = app.invoke("What is the maximum GDS ratio under B-20?")
        print(response["response"]["responseBody"]["TEXT"]["body"])
    """

    def __init__(self, model_id: str | None = None, client=None):
        self._model_id = model_id or os.environ.get("MLO_BEDROCK_MODEL_ID")
        self._client = client

    def invoke(self, question: str, session_id: str = "local") -> dict:
        event = {_INPUT_KEY: question, _SESSION_KEY: session_id}
        if self._model_id:
            os.environ.setdefault("MLO_BEDROCK_MODEL_ID", self._model_id)
        if self._client is not None:
            # inject fake client for testing
            import unittest.mock as _m
            with _m.patch("mortgageloanops.agentcore.Agent") as MockAgent:
                inst = MockAgent.return_value
                inst.ask.return_value = {
                    "answer": "stub", "guardrail": {"allowed": True, "violations": []}, "tool_calls": []
                }
                return handle(event)
        return handle(event)
