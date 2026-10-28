"""10,000 randomized files checked against invariants that must always hold (a property test, not a backtest
against real lending outcomes)."""
import random
from mortgageloanops import qualify, payments, ird, lenders, guardrail, pipeline, homevalue

N = 10_000


def test_qualification_invariants_10k():
    rnd = random.Random(20261028)
    for _ in range(N):
        price = rnd.uniform(150_000, 2_500_000); dp = price * rnd.uniform(0.05, 0.6)
        inc = rnd.uniform(30_000, 600_000); rate = rnd.uniform(1.0, 9.0); am = rnd.choice([20, 25, 30])
        q = qualify.qualify(price=price, down_payment=dp, annual_income=inc, contract_rate=rate, amort_years=am,
                            property_tax_annual=price * 0.008, other_debt_monthly=rnd.uniform(0, 2500),
                            first_time_buyer=rnd.random() < 0.3, new_build=rnd.random() < 0.2)
        assert q.qualifying_rate >= 5.25 and q.qualifying_rate >= rate + 2.0 - 1e-9
        assert q.stressed_payment >= q.contract_payment
        assert q.tds >= q.gds
        assert q.passes == (not q.reasons)
        if q.passes:
            assert q.gds <= 39.0 and q.tds <= 44.0


def test_payment_and_penalty_invariants_10k():
    rnd = random.Random(7)
    for _ in range(N):
        bal = rnd.uniform(50_000, 2_000_000); r = rnd.uniform(0.5, 9.0); m = rnd.uniform(1, 60)
        p1 = payments.payment(bal, r, 25); p2 = payments.payment(bal, r + 1, 25)
        assert p2 > p1 > 0
        pen = ird.penalty(balance=bal, contract_rate=r, months_remaining=m, comparison_rate=rnd.uniform(0.5, 9.0))
        assert pen.penalty >= pen.three_months - 0.01 and pen.penalty >= 0
        v = ird.penalty(balance=bal, contract_rate=r, months_remaining=m, is_variable=True)
        assert v.penalty == v.three_months


def test_lender_match_monotonic_and_guardrail_10k():
    rnd = random.Random(3)
    for _ in range(N):
        prov = rnd.choice(["ON", "BC", "AB"]); sc = rnd.randint(300, 900); ltv = rnd.uniform(40, 95)
        gds = rnd.uniform(10, 60); tds = gds + rnd.uniform(0, 15)
        hi = {l.name for l in lenders.match(province=prov, credit_score=sc, ltv=ltv, gds=gds, tds=tds)}
        lo = {l.name for l in lenders.match(province=prov, credit_score=min(900, sc + 100), ltv=ltv, gds=gds, tds=tds)}
        assert hi <= lo                                        # better credit never removes a match
        assert all(l.provinces and prov in l.provinces for l in lenders.match(province=prov, credit_score=sc, ltv=ltv, gds=gds, tds=tds))
    for _ in range(N):
        pct = round(rnd.uniform(1, 12), 2)
        assert not guardrail.check(f"Our rate is {pct}% for you")["allowed"]


def test_pipeline_never_crashes_on_random_files(tmp_path):
    from mortgageloanops.messaging import Messenger
    rnd = random.Random(11); m = Messenger(live=False, outbox_dir=str(tmp_path))
    for i in range(300):
        app = {"id": str(i), "type": rnd.choice(["PURCHASE", "FTHB"]), "province": rnd.choice(["ON", "BC", "AB"]),
               "credit_score": rnd.randint(300, 900), "borrower": {"name": "Test User", "phone": "+14165550100", "email": "t@example.com"},
               "price": rnd.uniform(200_000, 1_800_000), "down_payment": rnd.uniform(10_000, 600_000),
               "income": rnd.uniform(30_000, 400_000), "contract_rate": rnd.uniform(2, 8)}
        out = pipeline.process_application(app, m)
        assert "qualification" in out and out["borrower_message"]["delivered_via"] in ("sms", "whatsapp", "email", "portal")
