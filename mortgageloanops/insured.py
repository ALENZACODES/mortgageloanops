"""Insured-mortgage rules in force since December 15, 2024.

Source: Department of Finance Canada, "Delivering the Boldest Mortgage Reforms in Decades" (Sept 2024):
price cap for insured mortgages raised from $1M to $1.5M; 30-year insured amortization for first-time
buyers and buyers of new builds. Minimum down payment: 5% of the first $500,000 and 10% of the portion
above that, up to the cap; 20% for homes at or above the cap.
"""
from __future__ import annotations

PRICE_CAP = 1_500_000
EFFECTIVE = "2024-12-15"


def min_down_payment(price: float) -> float:
    if price <= 0:
        raise ValueError("price must be positive")
    if price >= PRICE_CAP:
        return price * 0.20
    if price <= 500_000:
        return price * 0.05
    return 25_000 + (price - 500_000) * 0.10


def max_amortization_years(down_payment: float, price: float, first_time_buyer: bool, new_build: bool) -> int:
    """30 years if uninsured (>=20% down), or insured and (first-time buyer or new build); otherwise 25."""
    if price > 0 and down_payment / price >= 0.20:
        return 30
    return 30 if (first_time_buyer or new_build) else 25


def is_insurable(price: float, down_payment: float) -> bool:
    """Insurance applies when down payment is under 20% and price is under the cap."""
    return price < PRICE_CAP and down_payment / price < 0.20
