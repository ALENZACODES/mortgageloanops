"""Canadian mortgage payment maths.

Fixed-rate mortgages in Canada compound semi-annually (Interest Act s.6); variable-rate mortgages are
quoted with monthly compounding. The payment formula is the standard annuity formula applied to the
effective monthly rate.
"""
from __future__ import annotations


def monthly_rate(annual_rate_pct: float, compounding: str = "semi") -> float:
    """Effective monthly rate from a quoted annual rate (percent)."""
    if annual_rate_pct < 0:
        raise ValueError("rate must be >= 0")
    r = annual_rate_pct / 100.0
    if compounding == "semi":
        return (1 + r / 2) ** (1 / 6) - 1
    if compounding == "monthly":
        return r / 12
    raise ValueError("compounding must be 'semi' or 'monthly'")


def payment(principal: float, annual_rate_pct: float, amort_years: float, compounding: str = "semi") -> float:
    """Monthly payment."""
    if principal <= 0 or amort_years <= 0:
        raise ValueError("principal and amortization must be positive")
    i = monthly_rate(annual_rate_pct, compounding)
    n = round(amort_years * 12)
    if i == 0:
        return principal / n
    return principal * i / (1 - (1 + i) ** -n)


def balance_after(principal: float, annual_rate_pct: float, amort_years: float, months_paid: int, compounding: str = "semi") -> float:
    """Remaining balance after `months_paid` regular payments."""
    i = monthly_rate(annual_rate_pct, compounding)
    pmt = payment(principal, annual_rate_pct, amort_years, compounding)
    if i == 0:
        return max(0.0, principal - pmt * months_paid)
    return max(0.0, principal * (1 + i) ** months_paid - pmt * (((1 + i) ** months_paid - 1) / i))
