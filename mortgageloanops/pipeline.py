"""End-to-end file processing: intake -> screening -> qualification -> lender match -> IRD / refinance ->
home value -> guardrailed borrower message over AWS messaging -> broker handoff report."""
from __future__ import annotations

import time

from . import qualify, lenders, ird, homevalue, kyc, insured
from .messaging import Messenger


def process_application(app: dict, messenger: Messenger | None = None, watchlist_path: str | None = None,
                        simulate_failures: tuple = ()) -> dict:
    messenger = messenger or Messenger(live=False)
    audit = []

    def log(stage, **kw):
        audit.append({"t": time.strftime("%H:%M:%S"), "stage": stage, **kw})

    borrower = app["borrower"]
    kind = app.get("type", "PURCHASE")
    log("intake", type=kind, province=app.get("province"))

    screening = kyc.screen(borrower["name"], watchlist_path)
    log("screening", status=screening["status"])

    out = {"type": kind, "borrower": borrower["name"], "screening": screening}

    if kind in ("PURCHASE", "FTHB"):
        q = qualify.qualify(price=app["price"], down_payment=app["down_payment"], annual_income=app["income"],
                            contract_rate=app["contract_rate"], property_tax_annual=app.get("property_tax", 0),
                            condo_fees_monthly=app.get("condo_fees", 0), other_debt_monthly=app.get("other_debt", 0),
                            amort_years=app.get("amort_years", 25), first_time_buyer=kind == "FTHB" or app.get("first_time_buyer", False),
                            new_build=app.get("new_build", False))
        out["qualification"] = q.to_dict()
        log("qualification", passes=q.passes, gds=q.gds, tds=q.tds)
        out["lender_matches"] = [l.name for l in lenders.match(province=app["province"], credit_score=app["credit_score"],
                                                              ltv=q.ltv, gds=q.gds, tds=q.tds)]
        out["insurance_required"] = insured.is_insurable(app["price"], app["down_payment"])
        log("lender_match", count=len(out["lender_matches"]))
    elif kind == "RENEWAL":
        pen = ird.penalty(balance=app["balance"], contract_rate=app["contract_rate"], months_remaining=app["months_remaining"],
                          is_variable=app.get("is_variable", False), comparison_rate=app.get("comparison_rate"),
                          original_posted_rate=app.get("original_posted_rate"), current_posted_rate=app.get("current_posted_rate"))
        out["penalty"] = pen.to_dict()
        out["refinance"] = ird.refinance_analysis(balance=app["balance"], current_rate=app["contract_rate"], new_rate=app["new_rate"],
                                                  months_remaining=app["months_remaining"], amort_years_remaining=app["amort_years_remaining"],
                                                  penalty_amount=pen.penalty, other_costs=app.get("other_costs", 0))
        log("ird", penalty=pen.penalty, recommendation=out["refinance"]["recommendation"])

    if app.get("postal_code") and app.get("purchase_price"):
        out["home_value"] = homevalue.indexed_value(app["purchase_price"], app["purchase_year"], app["purchase_month"], app["postal_code"])
        log("home_value", estimate=out["home_value"]["estimate"])

    portal = f"https://portal.example.com/file/{app.get('id', 'demo')}"
    hv, pen_d, refi = out.get("home_value"), out.get("penalty"), out.get("refinance")
    if hv and kind == "RENEWAL":
        out["current_ltv"] = round(app["balance"] / hv["estimate"] * 100, 1)
    broker_lines = []
    if hv:
        broker_lines.append(f"Indicative home value ${hv['estimate']:,.0f} (range ${hv['low']:,.0f}-${hv['high']:,.0f}, {hv['region']} index; not an appraisal)")
        if "current_ltv" in out:
            broker_lines.append(f"Balance ${app['balance']:,.0f} is about {out['current_ltv']}% of that estimate")
    if pen_d:
        broker_lines.append(f"Estimated prepayment penalty ${pen_d['penalty']:,.0f} ({pen_d.get('method', 'IRD/3-month')}); confirm with the lender's statement")
    if refi:
        broker_lines.append(f"Refinance analysis: {refi['recommendation']}")

    first = borrower['name'].split()[0]
    body = (f"Hi {first}, thanks for your mortgage inquiry. A licensed mortgage broker is reviewing your file and will contact you to discuss options.")
    if hv:
        body += (f" For context, an indicative value for your property is about ${hv['estimate']:,.0f} (range ${hv['low']:,.0f} to ${hv['high']:,.0f}). "
                 "It is an estimate, not an appraisal.")
    if pen_d:
        body += f" Your estimated prepayment penalty is about ${pen_d['penalty']:,.0f}; your lender's statement is the final figure."
    body += f" You can securely upload documents here: {portal}"
    delivery = messenger.send_with_fallback(borrower, "Your mortgage inquiry", body, portal, simulate_failures=simulate_failures)
    out["borrower_message"] = {"delivered_via": delivery["delivered_via"], "attempts": delivery["attempts"],
                               "blocked_by_guardrail": delivery.get("blocked_by_guardrail")}
    log("messaging", via=delivery["delivered_via"])

    out["broker_handoff"] = {"summary": broker_lines,
                             "requires_manual_review": screening["requires_manual_review"] or bool(out.get("qualification") and not out["qualification"]["passes"]),
                             "audit": audit}
    return out
