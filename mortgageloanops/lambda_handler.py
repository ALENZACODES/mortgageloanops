"""AWS Lambda entry points.

* `api_handler`      — API Gateway (HTTP API / REST) proxy: POST /process, GET /health
* `inbound_handler`  — SNS-triggered: inbound SMS / WhatsApp replies from AWS End User Messaging
Environment: MLO_LIVE=1, MLO_SMS_ORIGINATION, MLO_WHATSAPP_PHONE_NUMBER_ID, MLO_EMAIL_FROM, MLO_BEDROCK_MODEL_ID (optional)
"""
from __future__ import annotations

import json
import os

from .conversation import Conversation, Store, normalize_inbound
from .messaging import Messenger
from .pipeline import process_application
from . import lenders, __version__

_messenger = None


def _m() -> Messenger:
    global _messenger
    if _messenger is None:
        _messenger = Messenger(outbox_dir="/tmp/outbox")
    return _messenger


def _resp(code, body):
    return {"statusCode": code, "headers": {"Content-Type": "application/json"}, "body": json.dumps(body, default=str)}


def api_handler(event, context=None):
    path = event.get("rawPath") or event.get("path", "")
    method = (event.get("requestContext", {}).get("http", {}).get("method") or event.get("httpMethod", "GET")).upper()
    if method == "GET" and path.endswith("/health"):
        return _resp(200, {"ok": True, "version": __version__, "lenders_in_registry": lenders.registry_count(), "mode": "live" if _m().live else "dry-run"})
    if method == "POST" and path.endswith("/process"):
        try:
            return _resp(200, process_application(json.loads(event.get("body") or "{}"), _m()))
        except (KeyError, ValueError, TypeError) as e:
            return _resp(400, {"error": f"{type(e).__name__}: {e}"})
    return _resp(404, {"error": "not found"})


def inbound_handler(event, context=None):
    agent = None
    if os.environ.get("MLO_BEDROCK_MODEL_ID"):
        from .agent import Agent
        agent = Agent()
    conv = Conversation(_m(), Store("/tmp/state.json"), agent=agent, portal_url=os.environ.get("MLO_PORTAL_URL", "https://portal.example.com"))
    results = [conv.handle(i) for i in normalize_inbound(event)]
    return {"handled": len(results), "results": results}
