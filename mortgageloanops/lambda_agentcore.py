"""AWS Lambda handler for the Bedrock AgentCore invocation endpoint.

This is a *separate* Lambda function from the main inbound-messaging handler (lambda_handler.py).
It is registered with Bedrock AgentCore as the action-group executor; AgentCore routes broker/
borrower questions here, this handler calls the mortgage calculators via Bedrock tool-use, and
returns the answer inside the AgentCore response envelope.

Environment variables:
    MLO_BEDROCK_MODEL_ID   Bedrock model ID (e.g. amazon.nova-micro-v1:0)
    MLO_LIVE               Set to "1" to enable live Bedrock calls (default: dry-run)
"""
from __future__ import annotations

from .agentcore import handle


def lambda_handler(event: dict, context) -> dict:  # noqa: ANN001
    """AWS Lambda entry point invoked by Bedrock AgentCore."""
    return handle(event, context)
