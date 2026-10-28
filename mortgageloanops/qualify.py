"""OSFI Guideline B-20 style qualification: stress test, GDS and TDS.

Qualifying rate = max(contract rate + 2%, 5.25%). Ratio limits use the common insured-lending limits
(GDS 39%, TDS 44%); individual lenders set their own limits.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from . import insured
from .payments import payment

MIN_QUALIFYING_RATE = 5.25
GDS_LIMIT = 39.0
TDS_LIMIT = 44.0


def qualifying_rate(contract_rate_pct: float) -> float:
    return max(contract_rate_pct + 2.0, MIN_QUALIFYING_RATE)


@dataclass
class Qualification:
    qualifying_rate: float
    contract_payment: float
    stressed_payment: float
    gds: float
    tds: float
    ltv: float
    amort_years: int
    passes: bool
    reasons: list

    def to_dict(self):
        return asdict(self)


def qualify(*, price: float, down_payment: float, annual_income: float, contract_rate: float,
            property_tax_annual: float = 0.0, heat_annual: float = 1800.0, condo_fees_monthly: float = 0.0,
            other_debt_monthly: float = 0.0, amort_years: int = 25, first_time_buyer: bool = False,
            new_build: bool = False) -> Qualification:
    reasons = []
    principal = price - down_payment
    if principal <= 0 or annual_income <= 0:
        return Qualification(qualifying_rate(contract_rate), 0, 0, 100.0, 100.0, 0.0, amort_years, False,
                             ["principal and income must be positive"])
    ltv = principal / price * 100
    max_am = insured.max_amortization_years(down_payment, price, first_time_buyer, new_build)
    if amort_years > max_am:
        reasons.append(f"amortization {amort_years}y exceeds maximum {max_am}y for this file")
    if down_payment < insured.min_down_payment(price):
        reasons.append(f"down payment below minimum ${insured.min_down_payment(price):,.0f}")
    if price >= insured.PRICE_CAP and ltv > 80:
        reasons.append("price at/above $1.5M requires at least 20% down")
    qr = qualifying_rate(contract_rate)
    contract_pmt = payment(principal, contract_rate, amort_years)
    stressed = payment(principal, qr, amort_years)
    income_m = annual_income / 12
    housing = stressed + property_tax_annual / 12 + heat_annual / 12 + 0.5 * condo_fees_monthly
    gds = housing / income_m * 100
    tds = (housing + other_debt_monthly) / income_m * 100
    if gds > GDS_LIMIT:
        reasons.append(f"GDS {gds:.1f}% exceeds {GDS_LIMIT:.0f}%")
    if tds > TDS_LIMIT:
        reasons.append(f"TDS {tds:.1f}% exceeds {TDS_LIMIT:.0f}%")
    return Qualification(qr, round(contract_pmt, 2), round(stressed, 2), round(gds, 2), round(tds, 2),
                         round(ltv, 2), amort_years, not reasons, reasons)
