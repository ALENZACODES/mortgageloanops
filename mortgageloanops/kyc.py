"""Identity / watch-list screening interface.

This module does NOT ship any sanctions or PEP data and therefore never reports a person as "clear".
Without a screening list it returns NOT_SCREENED and flags manual review. If you supply a watch-list file
(one name per line), it does normalized name matching against that file only. Production use requires a
licensed screening provider and FINTRAC-compliant procedures.
"""
from __future__ import annotations

import re
from pathlib import Path


def _norm(name: str) -> frozenset:
    return frozenset(t for t in re.sub(r"[^a-z\s]", " ", name.lower()).split() if t)


def screen(name: str, watchlist_path: str | None = None) -> dict:
    if not name or not name.strip():
        return {"status": "ERROR", "requires_manual_review": True, "detail": "name required"}
    if not watchlist_path:
        return {"status": "NOT_SCREENED", "requires_manual_review": True,
                "detail": "No screening list configured; identity and watch-list checks must be done by a person."}
    p = Path(watchlist_path)
    if not p.exists():
        return {"status": "NOT_SCREENED", "requires_manual_review": True, "detail": f"watch-list not found: {p}"}
    target = _norm(name)
    hits = [ln.strip() for ln in p.read_text(encoding="utf-8").splitlines() if ln.strip() and _norm(ln) == target]
    if hits:
        return {"status": "POTENTIAL_MATCH", "requires_manual_review": True, "matches": hits,
                "detail": "Name matches an entry in the supplied list; escalate to compliance."}
    return {"status": "NO_MATCH_IN_PROVIDED_LIST", "requires_manual_review": True,
            "detail": "No match in the supplied list only. This is not a sanctions or PEP clearance."}
