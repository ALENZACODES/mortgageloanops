import json, math
import pytest
from mortgageloanops import payments, qualify, insured, ird, homevalue, lenders, kyc, guardrail
from mortgageloanops.index_anchors import region


def test_payment_matches_canadian_semiannual_reference():
    assert payments.payment(600_000, 5.0, 25) == pytest.approx(3489.63, abs=0.01)
    assert payments.payment(600_000, 7.0, 25) == pytest.approx(4202.49, abs=0.01)


def test_balance_after_full_amortization_is_zero():
    assert payments.balance_after(300_000, 5.0, 25, 300) == pytest.approx(0, abs=0.5)


def test_stress_rate_rules():
    assert qualify.qualifying_rate(2.0) == 5.25      # floor
    assert qualify.qualifying_rate(4.5) == 6.5       # contract + 2


def test_stress_uses_true_payment_not_linear_scaling():
    q = qualify.qualify(price=750_000, down_payment=150_000, annual_income=150_000, contract_rate=5.0)
    assert q.stressed_payment == pytest.approx(payments.payment(600_000, 7.0, 25), abs=0.01)
    linear = q.contract_payment * 7.0 / 5.0
    assert linear > q.stressed_payment * 1.10        # the old shortcut overstated by >10%


def test_insured_rules_dec_2024():
    assert insured.PRICE_CAP == 1_500_000
    assert insured.min_down_payment(400_000) == 20_000
    assert insured.min_down_payment(800_000) == 55_000          # 5% of 500k + 10% of 300k
    assert insured.min_down_payment(1_500_000) == 300_000       # 20% at/above cap
    assert insured.max_amortization_years(40_000, 800_000, True, False) == 30
    assert insured.max_amortization_years(40_000, 800_000, False, True) == 30
    assert insured.max_amortization_years(40_000, 800_000, False, False) == 25


def test_high_ratio_800k_purchase_no_crash_and_amort_enforced():
    q = qualify.qualify(price=800_000, down_payment=55_000, annual_income=250_000, contract_rate=4.5, amort_years=30)
    assert any("amortization" in r for r in q.reasons)           # repeat buyer cannot do 30y insured
    q2 = qualify.qualify(price=800_000, down_payment=55_000, annual_income=250_000, contract_rate=4.5, amort_years=30, first_time_buyer=True)
    assert not any("amortization" in r for r in q2.reasons)


def test_ird_posted_method_example():
    p = ird.penalty(balance=400_000, contract_rate=5.2, months_remaining=30, original_posted_rate=6.9, current_posted_rate=5.8)
    assert p.ird == pytest.approx(11_000) and p.penalty == p.ird


def test_penalty_never_below_three_months_and_variable_is_three_months():
    p = ird.penalty(balance=400_000, contract_rate=5.2, months_remaining=30, comparison_rate=6.0)   # rates rose -> IRD 0
    assert p.ird == 0 and p.penalty == p.three_months == pytest.approx(5_200)
    v = ird.penalty(balance=400_000, contract_rate=6.0, months_remaining=12, is_variable=True)
    assert v.penalty == pytest.approx(6_000)


def test_fixed_penalty_requires_comparison_inputs():
    with pytest.raises(ValueError):
        ird.penalty(balance=1, contract_rate=5, months_remaining=12)


def test_refinance_break_even():
    r = ird.refinance_analysis(balance=400_000, current_rate=5.2, new_rate=4.4, months_remaining=30,
                               amort_years_remaining=22, penalty_amount=11_000)
    assert r["monthly_saving"] > 0 and r["break_even_months"] > 30 and r["recommendation"] == "stay in current mortgage"


def test_lender_registry_count_is_real_and_cwb_not_a_credit_union():
    assert lenders.registry_count() == len(lenders.LENDERS) == 34
    assert not any("CWB" in l.name and l.category == "CREDIT_UNION" for l in lenders.LENDERS)
    assert all(l.panel_verified is False for l in lenders.LENDERS)


def test_high_ratio_file_matches_insured_capable_lenders_only():
    m = lenders.match(province="ON", credit_score=720, ltv=90, gds=30, tds=35)
    assert m and all(l.category != "B_LENDER" for l in m)


def test_lender_match_respects_inputs():
    assert lenders.match(province="ON", credit_score=450, ltv=75, gds=30, tds=35) == []
    assert lenders.match(province="ON", credit_score=800, ltv=75, gds=60, tds=70) == []


def test_kyc_never_reports_clear(tmp_path):
    assert kyc.screen("Harpreet Singh")["status"] == "NOT_SCREENED"
    wl = tmp_path / "wl.txt"; wl.write_text("Jane Q Public\n")
    assert kyc.screen("public jane q", str(wl))["status"] == "POTENTIAL_MATCH"
    r = kyc.screen("Harpreet Singh", str(wl))
    assert r["status"] == "NO_MATCH_IN_PROVIDED_LIST" and r["requires_manual_review"] is True


@pytest.mark.parametrize("text,viol", [
    ("Rates from 3.99% today", "RATE_QUOTE"), ("our rate is 4.25 %", "RATE_QUOTE"),
    ("You are approved for $500,000", "APPROVAL_PROMISE"), ("You're pre-approved!", "APPROVAL_PROMISE"),
    ("We guarantee it", "GUARANTEE"), ("lowest rate in town", "GUARANTEE")])
def test_guardrail_blocks(text, viol):
    assert viol in guardrail.check(text)["violations"]


def test_guardrail_allows_neutral_text():
    assert guardrail.check("A licensed broker will contact you about your file.")["allowed"]


def test_homevalue_indexing_direction_and_inputs():
    v = homevalue.indexed_value(750_000, 2022, 6, "M5V 2T6")
    assert v["region"] == "GTA" and v["low"] < v["estimate"] < v["high"]
    assert homevalue.indexed_value(500_000, 2016, 1, "T2P 1J9")["region"] in ("CGY", "EDM", "ABO")
    with pytest.raises(ValueError):
        homevalue.indexed_value(0, 2020, 1, "M5V")
    with pytest.raises(ValueError):
        homevalue.indexed_value(100, 2020, 1, "12")


def test_region_mapping_covers_all_first_letters():
    for ch in "ABCEGHJKLMNPRSTVXY":
        assert region(ch + "1A") in {"GTA","OTT","SWO","EON","NON","CGY","EDM","ABO","VAN","BCO","PRA","MTL","QCO","ATL","TER"}
