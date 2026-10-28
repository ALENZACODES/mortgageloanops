"""Outbound-message guardrail for borrower communications.

Blocks text that quotes specific rates, promises approval, or guarantees outcomes, so that automated
messages stay informational and rate/approval discussions happen with a licensed broker. This is a
heuristic safety net, not legal advice or a statement of regulatory compliance.
"""
from __future__ import annotations

import re

RULES = [
    ("RATE_QUOTE", re.compile(r"\b\d{1,2}(?:\.\d{1,3})?\s*%\s*(?:rate|apr|interest|fixed|variable)?|\b(?:rate|apr|interest)\s*(?:of|at|from|as low as)?\s*\d{1,2}(?:\.\d{1,3})?\s*%", re.I)),
    ("APPROVAL_PROMISE", re.compile(r"\b(?:you(?:'re| are)\s+)?(?:pre-?)?approved\b|\bapproved\s+for\s+\$", re.I)),
    ("GUARANTEE", re.compile(r"\bguarantee[sd]?\b|\bno\s+credit\s+check\b|\blowest\s+rate\b", re.I)),
]


def check(text: str) -> dict:
    violations = [name for name, rx in RULES if rx.search(text)]
    return {"allowed": not violations, "violations": violations}
