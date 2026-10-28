"""Prepayment penalty (IRD) calculator.

Two standard methods are implemented. Which one applies, and the exact comparison rate, is set by the
lender's mortgage contract; this module is an estimate for planning, not a payout statement.

* Variable rate / any mortgage: three months' interest.
* Fixed rate: the GREATER of three months' interest and the interest rate differential (IRD).
  - "comparison" method (typical of monolines/credit unions): IRD = (contract rate - comparison rate)
    x balance x remaining term in years, where the comparison rate is the lender's current rate for a
    term closest to the remaining term.
  - "posted" method (typical of the large banks): the comparison rate is the lender's CURRENT POSTED rate
    for the remaining term minus the discount the borrower originally received, which tends to produce
    a larger penalty because the discount is measured against the posted rate.
"""
from __future__ import annotations

from dataclasses import dataclass, asdict

from .payments import payment


def three_months_interest(balance: float, rate_pct: float) -> float:
    return balance * (rate_pct / 100) / 12 * 3


def ird_comparison(balance: float, contract_rate: float, comparison_rate: float, months_remaining: float) -> float:
    return max(0.0, (contract_rate - comparison_rate) / 100 * balance * months_remaining / 12)


def ird_posted(balance: float, contract_rate: float, original_posted_rate: float,
               current_posted_rate_for_remaining_term: float, months_remaining: float) -> float:
    """Bank method. discount = original_posted - contract; comparison = current_posted - discount."""
    discount = original_posted_rate - contract_rate
    comparison = current_posted_rate_for_remaining_term - discount
    return ird_comparison(balance, contract_rate, comparison, months_remaining)


@dataclass
class Penalty:
    method: str
    three_months: float
    ird: float
    penalty: float

    def to_dict(self):
        return asdict(self)


def penalty(*, balance: float, contract_rate: float, months_remaining: float, is_variable: bool = False,
            comparison_rate: float | None = None, original_posted_rate: float | None = None,
            current_posted_rate: float | None = None) -> Penalty:
    if balance <= 0 or months_remaining <= 0:
        raise ValueError("balance and months_remaining must be positive")
    tmi = three_months_interest(balance, contract_rate)
    if is_variable:
        return Penalty("variable: 3 months interest", round(tmi, 2), 0.0, round(tmi, 2))
    if original_posted_rate is not None and current_posted_rate is not None:
        ird = ird_posted(balance, contract_rate, original_posted_rate, current_posted_rate, months_remaining)
        method = "fixed: greater of 3 months interest and IRD (posted-rate method)"
    elif comparison_rate is not None:
        ird = ird_comparison(balance, contract_rate, comparison_rate, months_remaining)
        method = "fixed: greater of 3 months interest and IRD (comparison-rate method)"
    else:
        raise ValueError("fixed-rate penalty needs comparison_rate, or original_posted_rate + current_posted_rate")
    return Penalty(method, round(tmi, 2), round(ird, 2), round(max(tmi, ird), 2))


def refinance_analysis(*, balance: float, current_rate: float, new_rate: float, months_remaining: float,
                       amort_years_remaining: float, penalty_amount: float, other_costs: float = 0.0) -> dict:
    """Does breaking the mortgage pay off? Compares payments over the remaining term."""
    cur = payment(balance, current_rate, amort_years_remaining)
    new = payment(balance, new_rate, amort_years_remaining)
    monthly_saving = cur - new
    gross = monthly_saving * months_remaining
    cost = penalty_amount + other_costs
    net = gross - cost
    break_even = cost / monthly_saving if monthly_saving > 0 else None
    return {
        "current_payment": round(cur, 2), "new_payment": round(new, 2),
        "monthly_saving": round(monthly_saving, 2),
        "gross_saving_over_term": round(gross, 2), "total_cost_to_break": round(cost, 2),
        "net_saving_over_term": round(net, 2),
        "break_even_months": None if break_even is None else round(break_even, 1),
        "recommendation": "consider refinancing" if net > 0 else "stay in current mortgage",
    }
