"""Public market context from Bank of Canada Valet and Statistics Canada series.

Data file: ``data/mortgage-rates-national.json`` (retrieved 2026-10-10 by the author's canadian-mortgage-suite
project; sources and terms: Bank of Canada Valet V80691335 / V80691311, StatCan 34-10-0145-01).
These are NATIONAL chartered-bank averages, not any specific lender's posted rate. They are context for a
broker, not a quote, and are never placed in borrower messages.
"""
from __future__ import annotations

import json
from bisect import bisect_right
from pathlib import Path

_PATH = Path(__file__).parent / "data" / "mortgage-rates-national.json"
_cache: dict | None = None


def _data() -> dict:
    global _cache
    if _cache is None:
        _cache = json.loads(_PATH.read_text())
    return _cache


def _series(name: str) -> list[tuple[str, float]]:
    pts = _data()["series"][name]["data"]
    return sorted((p["date"], float(p["rate"])) for p in pts)


def rate_on(series: str, date: str) -> dict:
    """Latest observation on or before ``date`` (YYYY-MM-DD). Raises ValueError if none."""
    s = _series(series)
    i = bisect_right([d for d, _ in s], date)
    if i == 0:
        raise ValueError(f"no {series} observation on or before {date}")
    d, r = s[i - 1]
    return {"series": series, "date": d, "rate": r}


def latest(series: str) -> dict:
    d, r = _series(series)[-1]
    return {"series": series, "date": d, "rate": r}


def context() -> dict:
    """Latest BoC prime and conventional 5-year posted rate, with provenance."""
    posted, prime = latest("posted_5yr_conventional"), latest("prime_rate")
    return {"posted_5yr_conventional": posted, "prime": prime, "retrieved": _data()["retrieved"],
            "scope": "national chartered-bank average (BoC Valet); not a lender quote"}
