"""Lender registry and category-level matching.

IMPORTANT: this is a starting registry of lender NAMES grouped by category. Thresholds below are
illustrative category-level policy, not any individual lender's current guidelines. A licensed broker must
confirm against live lender policy before submitting a file. `panel_verified` is False for every entry.
"""
from __future__ import annotations

from dataclasses import dataclass

ALL = ("ON", "BC", "AB")


@dataclass(frozen=True)
class Lender:
    name: str
    category: str          # BIG_BANK | MONOLINE | CREDIT_UNION | B_LENDER | PROVINCIAL_FI
    provinces: tuple
    panel_verified: bool = False


# Illustrative category policy
# max_ltv_insured is None where the category does not do high-ratio (insured) lending.
CATEGORY_POLICY = {
    "BIG_BANK":      {"min_score": 680, "max_ltv": 80, "max_ltv_insured": 95,   "max_gds": 39, "max_tds": 44},
    "MONOLINE":      {"min_score": 680, "max_ltv": 80, "max_ltv_insured": 95,   "max_gds": 39, "max_tds": 44},
    "CREDIT_UNION":  {"min_score": 640, "max_ltv": 80, "max_ltv_insured": 95,   "max_gds": 39, "max_tds": 44},
    "PROVINCIAL_FI": {"min_score": 640, "max_ltv": 80, "max_ltv_insured": 95,   "max_gds": 39, "max_tds": 44},
    "B_LENDER":      {"min_score": 600, "max_ltv": 80, "max_ltv_insured": None, "max_gds": 45, "max_tds": 50},
}

LENDERS = (
    [Lender(n, "BIG_BANK", ALL) for n in ("RBC", "TD", "BMO", "Scotiabank", "CIBC", "National Bank of Canada (incl. former CWB)")]
    + [Lender(n, "MONOLINE", ALL) for n in ("RMG Mortgages", "MCAP", "First National", "Merix Financial")]
    + [Lender(n, "B_LENDER", ALL) for n in ("Equitable Bank", "Home Trust", "ICICI Bank Canada", "B2B Bank", "Manulife Bank")]
    + [Lender(n, "CREDIT_UNION", ("ON",)) for n in ("Meridian", "Desjardins (Ontario)", "DUCA", "Alterna Savings", "FirstOntario", "Libro")]
    + [Lender(n, "CREDIT_UNION", ("BC",)) for n in ("Vancity", "Coast Capital", "Prospera", "Gulf & Fraser", "First West", "BlueShore Financial", "Interior Savings", "Kootenay Savings")]
    + [Lender(n, "CREDIT_UNION", ("AB",)) for n in ("Servus", "Connect First", "Vision Credit Union", "1st Choice Savings")]
    + [Lender("ATB Financial", "PROVINCIAL_FI", ("AB",))]
)


def registry_count() -> int:
    return len(LENDERS)


def match(*, province: str, credit_score: int, ltv: float, gds: float, tds: float) -> list:
    """Return lenders whose category policy the file satisfies."""
    out = []
    for l in LENDERS:
        if province not in l.provinces:
            continue
        p = CATEGORY_POLICY[l.category]
        cap = p["max_ltv"] if ltv <= 80 else p["max_ltv_insured"]
        if cap is not None and credit_score >= p["min_score"] and ltv <= cap and gds <= p["max_gds"] and tds <= p["max_tds"]:
            out.append(l)
    return out
