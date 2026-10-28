"""Borrower messaging on AWS End User Messaging (SMS), AWS End User Messaging Social (WhatsApp) and SES.

Channel order with a hard per-channel timeout (default 5s), then a secure-portal fallback:
    RCS -> SMS -> WhatsApp -> Email (SES) -> portal link
RCS is only attempted when MLO_RCS_AGENT_ARN is set (an AWS RCS agent must exist and be Active).

* DRY-RUN (default): nothing is sent; each message is written to an outbox as JSON in the exact shape
  that would be passed to the AWS API.
* LIVE (MLO_LIVE=1 or live=True): uses boto3 clients
    - 'pinpoint-sms-voice-v2'  .send_text_message        (AWS End User Messaging SMS and RCS: the same API;
                                                          an RCS agent ARN as OriginationIdentity sends via RCS only)
    - 'socialmessaging'        .send_whatsapp_message    (AWS End User Messaging Social)
    - 'sesv2'                  .send_email               (Amazon SES)
  Clients can be injected for testing. Every message passes the guardrail before any channel is tried.
"""
from __future__ import annotations

import json
import os
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutTimeout
from pathlib import Path

from . import guardrail
from .compliance import Policy

CHANNELS = ("rcs", "sms", "whatsapp", "email")


class Messenger:
    def __init__(self, live: bool | None = None, region: str | None = None, clients: dict | None = None,
                 timeout: float = 5.0, outbox_dir: str = "outbox", config: dict | None = None,
                 policy: Policy | None = None):
        self.policy = policy or Policy()
        self.live = (os.environ.get("MLO_LIVE") == "1") if live is None else live
        self.region = region or os.environ.get("AWS_REGION", "ca-central-1")
        self.timeout = timeout
        self.outbox = Path(outbox_dir)
        self.clients = clients or {}
        self.config = config or {
            "sms_origination": os.environ.get("MLO_SMS_ORIGINATION", ""),
            "rcs_agent_arn": os.environ.get("MLO_RCS_AGENT_ARN", ""),
            "whatsapp_phone_number_id": os.environ.get("MLO_WHATSAPP_PHONE_NUMBER_ID", ""),
            "meta_api_version": os.environ.get("MLO_META_API_VERSION", "v20.0"),
            "email_from": os.environ.get("MLO_EMAIL_FROM", ""),
        }
        self.log: list[dict] = []

    # ---- client plumbing -------------------------------------------------------------------------
    def _client(self, service: str):
        if service not in self.clients:
            import boto3  # imported lazily so dry-run needs no dependencies
            self.clients[service] = boto3.client(service, region_name=self.region)
        return self.clients[service]

    # ---- request builders (exact AWS API shapes) ---------------------------------------------------
    def build_sms(self, to: str, body: str) -> dict:
        return {"DestinationPhoneNumber": to, "OriginationIdentity": self.config["sms_origination"],
                "MessageBody": body, "MessageType": "TRANSACTIONAL"}

    def build_rcs(self, to: str, body: str) -> dict:
        # Documented direct-send shape: an AWS RCS agent ARN as the origination identity delivers via RCS only.
        return {"DestinationPhoneNumber": to, "OriginationIdentity": self.config.get("rcs_agent_arn", ""), "MessageBody": body}

    def build_whatsapp(self, to: str, body: str) -> dict:
        msg = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
        return {"originationPhoneNumberId": self.config["whatsapp_phone_number_id"],
                "metaApiVersion": self.config["meta_api_version"], "message": json.dumps(msg).encode("utf-8")}

    def build_whatsapp_template(self, to: str, template_name: str, lang_code: str = "en_US",
                                 components: list | None = None) -> dict:
        """Build an approved WhatsApp template message (preferred for outbound business-initiated messages).

        AWS End User Messaging Social (EUM) passes this to the Meta Cloud API.
        Template messages bypass the 24-hour messaging window restriction.
        The template must be pre-approved in the Meta Business Manager.

        Args:
            to: E.164 destination phone number.
            template_name: Approved template name in Meta Business Manager.
            lang_code: BCP-47 language code registered with the template (default: en_US).
            components: Optional list of template components (header, body, button parameters).
        """
        msg = {
            "messaging_product": "whatsapp",
            "to": to,
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": lang_code},
            }
        }
        if components:
            msg["template"]["components"] = components
        return {
            "originationPhoneNumberId": self.config["whatsapp_phone_number_id"],
            "metaApiVersion": self.config["meta_api_version"],
            "message": json.dumps(msg).encode("utf-8"),
        }

    def build_email(self, to: str, subject: str, body: str) -> dict:
        return {"FromEmailAddress": self.config["email_from"], "Destination": {"ToAddresses": [to]},
                "Content": {"Simple": {"Subject": {"Data": subject}, "Body": {"Text": {"Data": body}}}}}

    # ---- single-channel sends --------------------------------------------------------------------
    def _send(self, channel: str, contact: dict, subject: str, body: str) -> dict:
        if channel == "rcs":
            req = self.build_rcs(contact["phone"], body)
            fn = lambda: self._client("pinpoint-sms-voice-v2").send_text_message(**req)
        elif channel == "sms":
            req = self.build_sms(contact["phone"], body)
            fn = lambda: self._client("pinpoint-sms-voice-v2").send_text_message(**req)
        elif channel == "whatsapp":
            req = self.build_whatsapp(contact["phone"], body)
            fn = lambda: self._client("socialmessaging").send_whatsapp_message(**req)
        elif channel == "email":
            req = self.build_email(contact["email"], subject, body)
            fn = lambda: self._client("sesv2").send_email(**req)
        else:
            raise ValueError(channel)
        if not self.live:
            self.outbox.mkdir(parents=True, exist_ok=True)
            rec = {"id": str(uuid.uuid4()), "channel": channel, "mode": "dry-run", "request": _jsonable(req)}
            (self.outbox / f"{channel}-{rec['id'][:8]}.json").write_text(json.dumps(rec, indent=2))
            return rec
        with ThreadPoolExecutor(max_workers=1) as ex:
            fut = ex.submit(fn)
            resp = fut.result(timeout=self.timeout)  # raises on timeout or AWS error
        return {"channel": channel, "mode": "live", "response_id": resp.get("MessageId") or resp.get("messageId")}

    # ---- public API ------------------------------------------------------------------------------
    def send_with_fallback(self, contact: dict, subject: str, body: str, portal_url: str,
                           order: tuple = CHANNELS, simulate_failures: tuple = (), now_utc=None) -> dict:
        g = guardrail.check(subject + "\n" + body)
        if not g["allowed"]:
            self._event("blocked", violations=g["violations"])
            return {"delivered_via": None, "blocked_by_guardrail": g["violations"], "attempts": self.log[-1:]}
        policy = self.policy
        if policy.is_suppressed(contact):
            self._event("suppressed")
            return {"delivered_via": None, "suppressed": True, "attempts": []}
        attempts = []
        for ch in order:
            ok, why = policy.channel_allowed(ch, contact, now_utc)
            if not ok:
                attempts.append({"channel": ch, "ok": False, "skipped": why})
                continue
            if ch == "rcs" and (not contact.get("phone") or not self.config.get("rcs_agent_arn")):
                continue
            if ch == "sms" and not contact.get("phone"):
                continue
            if ch == "whatsapp" and not contact.get("phone"):
                continue
            if ch == "email" and not contact.get("email"):
                continue
            t0 = time.time()
            try:
                if ch in simulate_failures:
                    raise RuntimeError(f"simulated {ch} failure")
                res = self._send(ch, contact, subject, body)
                attempts.append({"channel": ch, "ok": True, "ms": int((time.time() - t0) * 1000)})
                self._event("sent", channel=ch)
                return {"delivered_via": ch, "result": res, "attempts": attempts}
            except FutTimeout:
                attempts.append({"channel": ch, "ok": False, "error": f"timeout>{self.timeout}s"})
            except Exception as e:  # AWS throttling, unverified identity, etc.
                attempts.append({"channel": ch, "ok": False, "error": f"{type(e).__name__}: {e}"})
            self._event("fallback", channel=ch)
        self._event("portal_fallback", url=portal_url)
        return {"delivered_via": "portal", "portal_url": portal_url, "attempts": attempts}

    def _event(self, kind: str, **kw):
        self.log.append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "event": kind, **kw})


def _jsonable(o):
    if isinstance(o, bytes):
        return o.decode("utf-8")
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    return o
