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

import time as _time


def _emit(namespace: str, metric: str, value: float, unit: str = "Count", dims: dict | None = None) -> None:
    """Emit a CloudWatch custom metric (best-effort; never raises)."""
    import os as _os
    if not _os.environ.get("MLO_LIVE"):
        return
    try:
        import boto3 as _boto3
        cw = _boto3.client("cloudwatch", region_name=_os.environ.get("AWS_REGION", "ca-central-1"))
        cw.put_metric_data(
            Namespace=namespace,
            MetricData=[{
                "MetricName": metric,
                "Value": value,
                "Unit": unit,
                "Dimensions": [{"Name": k, "Value": v} for k, v in (dims or {}).items()],
            }],
        )
    except Exception:  # pylint: disable=broad-except
        pass  # metrics are non-critical

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
            t0 = _time.monotonic()
            body_parsed = json.loads(event.get("body") or "{}")
            result = process_application(body_parsed, _m())
            elapsed_ms = (_time.monotonic() - t0) * 1000
            _emit("MortgageLoanOps", "FileProcessed", 1, dims={"Kind": body_parsed.get("kind", "UNKNOWN")})
            _emit("MortgageLoanOps", "ProcessLatencyMs", elapsed_ms, unit="Milliseconds")
            if result.get("qualify", {}).get("pass"):
                _emit("MortgageLoanOps", "QualifyPass", 1)
            return _resp(200, result)
        except (KeyError, ValueError, TypeError) as e:
            _emit("MortgageLoanOps", "ProcessError", 1)
            return _resp(400, {"error": f"{type(e).__name__}: {e}"})
    return _resp(404, {"error": "not found"})


def inbound_handler(event, context=None):
    agent = None
    if os.environ.get("MLO_BEDROCK_MODEL_ID"):
        from .agent import Agent
        agent = Agent()
    conv = Conversation(_m(), Store("/tmp/state.json"), agent=agent, portal_url=os.environ.get("MLO_PORTAL_URL", "https://portal.example.com"))
    results = [conv.handle(i) for i in normalize_inbound(event)]
    for r in results:
        channel = r.get("channel", "unknown")
        _emit("MortgageLoanOps", "InboundMessage", 1, dims={"Channel": channel})
        action = r.get("action", "")
        if action:
            _emit("MortgageLoanOps", "ConversationAction", 1, dims={"Action": action})
    return {"handled": len(results), "results": results}
