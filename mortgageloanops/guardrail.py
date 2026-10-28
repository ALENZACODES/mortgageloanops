"""Outbound-message guardrail for borrower communications.

Blocks text that quotes specific rates, promises approval, guarantees outcomes, applies pressure,
asks for sensitive credentials over a message channel, or leaks sensitive identifiers. Text is
normalised first (Unicode NFKC, zero-width characters removed, whitespace collapsed) so simple
obfuscation such as "gua\u200brantee" or full-width digits does not slip through.

This is a heuristic safety net, not legal advice or a statement of regulatory compliance.
"""
from __future__ import annotations

import re
import unicodedata

_ZERO_WIDTH = dict.fromkeys(map(ord, "\u200b\u200c\u200d\u2060\ufeff\u00ad"))

RULES = [
    ("RATE_QUOTE", re.compile(r"\b\d{1,2}(?:\.\d{1,3})?\s*%\s*(?:rate|apr|interest|fixed|variable)?|\b(?:rate|apr|interest)\s*(?:of|at|from|as low as)?\s*\d{1,2}(?:\.\d{1,3})?\s*%|\b(?:prime|bps)\s*[-+]\s*\d", re.I)),
    ("APPROVAL_PROMISE", re.compile(r"\b(?:you(?:'re| are)\s+)?(?:pre-?)?approved\b|\bapproved\s+for\s+\$|\bwill\s+be\s+approved\b|\bcertain(?:ly)?\s+(?:to\s+)?(?:qualify|approve)", re.I)),
    ("GUARANTEE", re.compile(r"\bguarantee[sd]?\b|\bno\s+credit\s+check\b|\blowest\s+rate\b|\bbest\s+rate\b|\brisk[-\s]?free\b|\b100\s*%\s*(?:safe|sure|approval)", re.I)),
    ("PRESSURE", re.compile(r"\bact\s+now\b|\blimited[-\s]time\b|\bhurry\b|\blast\s+chance\b|\bexpires?\s+(?:today|tonight)\b|\bbefore\s+it'?s\s+too\s+late\b", re.I)),
    ("SENSITIVE_REQUEST", re.compile(r"\b(?:send|reply\s+with|text|share|provide|enter)\b[^.\n]{0,40}\b(?:sin|social\s+insurance|card\s+number|cvv|password|passcode|pin|banking\s+password|one[-\s]time\s+code|otp)\b", re.I)),
    ("SENSITIVE_DATA_LEAK", re.compile(r"\b\d{3}[-\s]\d{3}[-\s]\d{3}\b|\b(?:\d[-\s]?){15,16}\b")),
    ("ADVICE_CLAIM", re.compile(r"\b(?:legal|tax|investment)\s+advice\s+(?:from\s+us|is\s+provided)|\bwe\s+recommend\s+(?:you\s+)?(?:buy|sell|invest)\b", re.I)),
]

_SAFE_REPLACEMENT = ("Your file has been received. A licensed broker will contact you with details. "
                     "We never ask for passwords, card numbers or one-time codes by message.")


def normalize(text: str) -> str:
    t = unicodedata.normalize("NFKC", text or "").translate(_ZERO_WIDTH)
    return re.sub(r"[ \t]+", " ", t)


def check(text: str) -> dict:
    t = normalize(text)
    violations = [name for name, rx in RULES if rx.search(t)]
    return {"allowed": not violations, "violations": violations}


def safe_replacement() -> str:
    """Neutral text that can be sent when the original was blocked (passes check())."""
    return _SAFE_REPLACEMENT


def redact(text: str) -> str:
    """Mask SIN-like and card-like numbers and email addresses before text goes into logs."""
    t = re.sub(r"\b\d{3}[-\s]\d{3}[-\s]\d{3}\b", "[SIN-REDACTED]", text or "")
    t = re.sub(r"\b(?:\d[-\s]?){15,16}\b", "[CARD-REDACTED]", t)
    return re.sub(r"[\w.+-]+@[\w-]+\.[\w.-]+", "[EMAIL-REDACTED]", t)
