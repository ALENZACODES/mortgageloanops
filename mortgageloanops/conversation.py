"""Two-way messaging: inbound SMS / WhatsApp replies -> state -> guardrailed reply on the same channel.

Inbound events arrive from AWS End User Messaging via Amazon SNS (two-way messaging destination).
`normalize_inbound` accepts the SMS shape (originationNumber / messageBody) and the WhatsApp shape
(whatsAppWebhookEntry), and any pre-normalized {"channel","from","text"} dict. Opt-out keywords are always honoured first.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path

from . import guardrail
from .messaging import Messenger

STOP = re.compile(r"^\s*(stop|stopall|unsubscribe|cancel|end|quit)\s*[.!]?\s*$", re.I)
HELP = re.compile(r"^\s*help\s*[.!]?\s*$", re.I)
BROKER = re.compile(r"\b(broker|call me|callback|call back|speak to|talk to)\b", re.I)


def normalize_inbound(event: dict) -> list[dict]:
    """Return [{'channel','from','text'}] from an SNS-delivered End User Messaging event or a normalized dict."""
    if "channel" in event and "text" in event:
        return [event]
    out = []
    for rec in event.get("Records", []):
        body = rec.get("Sns", {}).get("Message")
        if body:
            out += normalize_inbound(json.loads(body) if isinstance(body, str) else body)
    if "originationNumber" in event and "messageBody" in event:
        out.append({"channel": "sms", "from": event["originationNumber"], "text": event["messageBody"]})
    wh = event.get("whatsAppWebhookEntry")
    if wh:
        entry = json.loads(wh) if isinstance(wh, str) else wh
        for ch in entry.get("changes", []):
            for m in ch.get("value", {}).get("messages", []):
                text = (m.get("text") or {}).get("body", "")
                num = m.get("from", "")
                out.append({"channel": "whatsapp", "from": num if num.startswith("+") else "+" + num, "text": text})
    return out


class Store:
    """Tiny JSON-file state (opt-outs, callback requests, transcript). Swap for DynamoDB in production."""
    def __init__(self, path: str | None = None):
        self.path = Path(path) if path else None
        self.d = {"opted_out": [], "callbacks": [], "transcript": []}
        if self.path and self.path.exists():
            self.d = json.loads(self.path.read_text())

    def save(self):
        if self.path:
            self.path.write_text(json.dumps(self.d, indent=1))


class Conversation:
    def __init__(self, messenger: Messenger, store: Store | None = None, agent=None, portal_url: str = "https://portal.example.com"):
        self.m, self.s, self.agent, self.portal = messenger, store or Store(), agent, portal_url

    def is_opted_out(self, number: str) -> bool:
        return number in self.s.d["opted_out"]

    def handle(self, inbound: dict) -> dict:
        num, text, ch = inbound["from"], inbound.get("text", ""), inbound["channel"]
        self.s.d["transcript"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "dir": "in", "channel": ch, "from": num, "text": guardrail.redact(text)})
        if STOP.match(text):
            if num not in self.s.d["opted_out"]:
                self.s.d["opted_out"].append(num)
            reply, action = "You're unsubscribed and won't receive further messages. Reply START to resubscribe.", "opt_out"
        elif self.is_opted_out(num) and not re.match(r"^\s*start\s*$", text, re.I):
            self.s.save(); return {"action": "ignored_opted_out", "sent": None}
        elif re.match(r"^\s*start\s*$", text, re.I):
            if num in self.s.d["opted_out"]:
                self.s.d["opted_out"].remove(num)
            self.m.policy.unsuppress(num)
            reply, action = "You're subscribed again. A licensed broker will be in touch.", "opt_in"
        elif HELP.match(text):
            reply, action = "This is your mortgage broker's assistant. Reply BROKER for a call back or STOP to unsubscribe.", "help"
        elif BROKER.search(text):
            self.s.d["callbacks"].append({"from": num, "t": time.strftime("%Y-%m-%dT%H:%M:%S"), "text": text})
            reply, action = "Thanks, a licensed broker will call you back. You can upload documents securely here: " + self.portal, "callback_requested"
        elif self.agent is not None:
            r = self.agent.ask(text); reply, action = r["answer"], "agent_answer"
        else:
            reply, action = "Thanks for your message. A licensed broker will review it and follow up. Reply BROKER for a call back.", "ack"
        contact = {"phone": num} if ch in ("sms", "whatsapp") else {"email": num}
        order = (ch,) if ch in ("sms", "whatsapp") else ("email",)
        res = self.m.send_with_fallback(contact, "Re: your message", reply, self.portal, order=order)
        if res.get("blocked_by_guardrail"):  # never go silent on a blocked reply: send neutral text instead
            action += "+guardrail_replaced"
            reply = guardrail.safe_replacement()
            res = self.m.send_with_fallback(contact, "Re: your message", reply, self.portal, order=order)
        if action == "opt_out":
            self.m.policy.suppress(num)  # applied after the confirmation is sent
        self.s.d["transcript"].append({"t": time.strftime("%Y-%m-%dT%H:%M:%S"), "dir": "out", "action": action, "delivered_via": res["delivered_via"], "text": guardrail.redact(reply)})
        self.s.save()
        return {"action": action, "sent": res["delivered_via"], "reply": reply}
