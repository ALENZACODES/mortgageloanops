"""End-to-end file processing: intake -> screening -> qualification -> lender match -> IRD / refinance ->
home value -> guardrailed borrower message over AWS messaging -> broker handoff report."""
from __future__ import annotations

import time

from . import qualify, lenders, ird, homevalue, kyc, insured, market
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
        ctx = market.context()
        out["market_context"] = ctx
        if not app.get("is_variable", False) and app.get("current_posted_rate") is None:
            # fall back to the national BoC average only when the file has no lender posted rate; flagged below
            app = {**app, "current_posted_rate": ctx["posted_5yr_conventional"]["rate"]}
            out["posted_rate_assumption"] = "current posted rate taken from BoC national average; replace with the lender's posted rate"
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
    if "market_context" in out:
        c = out["market_context"]
        broker_lines.append(f"Market context (BoC, {c['posted_5yr_conventional']['date']}): 5-yr conventional posted {c['posted_5yr_conventional']['rate']}%, prime {c['prime']['rate']}% (national averages, not a quote)")
    if "posted_rate_assumption" in out:
        broker_lines.append("Note: " + out["posted_rate_assumption"])
    if refi:
        broker_lines.append(f"Refinance analysis: {refi['recommendation']}")

    first = borrower['name'].split()[0]

    # Renewal files use a WhatsApp template message (business-initiated, bypasses 24-hour window).
    # The template "mortgage_renewal_reminder" must be pre-approved in Meta Business Manager.
    # For purchase/FTHB we send a session reply (borrower messaged us first, within the 24-hr window).
    if kind == "RENEWAL" and borrower.get("phone") and pen_d:
        # Try to send a structured WhatsApp template first, fall back to the standard text chain.
        components = [
            {"type": "body", "parameters": [
                {"type": "text", "text": first},
                {"type": "text", "text": f"${pen_d['penalty']:,.0f}"},
                {"type": "text", "text": portal},
            ]}
        ]
        try:
            wa_req = messenger.build_whatsapp_template(
                to=borrower["phone"],
                template_name="mortgage_renewal_reminder",
                lang_code="en_US",
                components=components,
            )
            if messenger.live:
                messenger._client("socialmessaging").send_whatsapp_message(**wa_req)
            else:
                import uuid as _uuid
                messenger.outbox.mkdir(parents=True, exist_ok=True)
                rec = {"id": str(_uuid.uuid4()), "channel": "whatsapp_template", "mode": "dry-run",
                       "template": "mortgage_renewal_reminder", "request": {**wa_req, "message": wa_req["message"].decode()}}
                (messenger.outbox / f"whatsapp-template-{rec['id'][:8]}.json").write_text(__import__('json').dumps(rec, indent=2))
            out["whatsapp_template_sent"] = {"template": "mortgage_renewal_reminder", "status": "queued"}
        except Exception as e:
            out["whatsapp_template_sent"] = {"template": "mortgage_renewal_reminder", "status": "error", "detail": str(e)}

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
