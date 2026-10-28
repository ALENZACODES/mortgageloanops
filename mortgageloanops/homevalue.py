"""Benchmark home-value estimate (repeat-sale indexing) from the Benchmark Home Value project.

Indexes a known purchase price forward with a regional price index. Indicative only: the anchors are
approximate regional benchmark curves, not sold-listing data, and this is not an appraisal. The full AVM
(LightGBM on open assessment data) lives in the separate Benchmark Home Value project.
"""
from __future__ import annotations

from .index_anchors import index_at, region, CALIB

NOW = (2026, 8)  # latest anchor in the table (Sep 2026)


def indexed_value(purchase_price: float, purchase_year: int, purchase_month: int, postal_code: str,
                  renovation_spend: float = 0.0) -> dict:
    """purchase_month is 1-12. Returns an indicative value with a +/- band."""
    if purchase_price <= 0:
        raise ValueError("purchase_price must be positive")
    fsa = postal_code.strip().upper().replace(" ", "")[:3]
    if len(fsa) < 3 or not fsa[0].isalpha():
        raise ValueError("postal_code must start with a valid FSA, e.g. M5V")
    reg = region(fsa)
    then = index_at(reg, purchase_year, purchase_month - 1)
    now = index_at(reg, *NOW)
    factor = now / then * CALIB.get(reg, 1.0)
    value = purchase_price * factor + renovation_spend * 0.6
    spread = 0.08 + (0.02 if reg in ("NON", "ABO", "TER", "ATL", "PRA") else 0.0)
    return {
        "region": reg, "index_factor": round(factor, 4), "estimate": round(value, -3),
        "low": round(value * (1 - spread), -3), "high": round(value * (1 + spread), -3),
        "method": "purchase price indexed with regional benchmark curve",
        "disclaimer": "Indicative only. Not an appraisal.",
    }
