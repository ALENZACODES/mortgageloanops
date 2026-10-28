from datetime import datetime, timezone
import pytest
from mortgageloanops import guardrail
from mortgageloanops.compliance import Policy
from mortgageloanops.messaging import Messenger
from mortgageloanops.conversation import Conversation, Store


@pytest.mark.parametrize("text,viol", [
    ("gua​rantee your approval", "GUARANTEE"),
    ("Rate: 4．25％", "RATE_QUOTE"),
    ("prime - 0.5 for you", "RATE_QUOTE"),
    ("You will be approved", "APPROVAL_PROMISE"),
    ("Act now, limited time!", "PRESSURE"),
    ("Please reply with your SIN", "SENSITIVE_REQUEST"),
    ("send your card number here", "SENSITIVE_REQUEST"),
    ("share the one-time code we texted", "SENSITIVE_REQUEST"),
    ("Your SIN 123-456-789 is on file", "SENSITIVE_DATA_LEAK"),
    ("Card 4111 1111 1111 1111", "SENSITIVE_DATA_LEAK"),
    ("This is risk-free", "GUARANTEE"),
])
def test_stronger_rules(text, viol):
    assert viol in guardrail.check(text)["violations"]


def test_safe_replacement_and_neutral_text_pass():
    assert guardrail.check(guardrail.safe_replacement())["allowed"]
    assert guardrail.check("Your file was received. A licensed broker will follow up.")["allowed"]


def test_redact():
    r = guardrail.redact("SIN 123-456-789 card 4111 1111 1111 1111 mail a.b@x.ca")
    assert "123-456-789" not in r and "4111" not in r and "a.b@x.ca" not in r


def mk(tmp_path, **kw):
    return Messenger(live=False, outbox_dir=str(tmp_path), config={"sms_origination": "+1", "rcs_agent_arn": "", "whatsapp_phone_number_id": "p", "meta_api_version": "v20.0", "email_from": "a@b.ca"}, **kw)


def test_suppressed_contact_is_never_contacted(tmp_path):
    m = mk(tmp_path); m.policy.suppress("+14165551234")
    r = m.send_with_fallback({"phone": "+1 (416) 555-1234", "email": "x@y.ca"}, "s", "Hello", "https://p")
    assert r["suppressed"] and r["delivered_via"] is None and not list(tmp_path.glob("*.json"))


def test_quiet_hours_skip_phone_channels_but_allow_email(tmp_path):
    m = mk(tmp_path, policy=Policy(quiet_hours=(8, 21)))
    night = datetime(2026, 10, 28, 7, 0, tzinfo=timezone.utc)  # 02:00 at UTC-5
    r = m.send_with_fallback({"phone": "+14165551234", "email": "x@y.ca"}, "s", "Hello", "https://p", now_utc=night)
    assert r["delivered_via"] == "email"
    day = datetime(2026, 10, 28, 17, 0, tzinfo=timezone.utc)  # 12:00
    assert m.send_with_fallback({"phone": "+14165551234"}, "s", "Hello", "https://p", now_utc=day)["delivered_via"] == "sms"


def test_consent_required_per_channel(tmp_path):
    m = mk(tmp_path, policy=Policy(require_consent=True))
    c = {"phone": "+14165551234", "email": "x@y.ca", "consent": {"email": True}}
    assert m.send_with_fallback(c, "s", "Hello", "https://p")["delivered_via"] == "email"
    assert m.send_with_fallback({"phone": "+14165551234"}, "s", "Hello", "https://p")["delivered_via"] == "portal"


def test_stop_sends_confirmation_then_suppresses_and_start_restores(tmp_path):
    m = mk(tmp_path); conv = Conversation(m, Store(str(tmp_path / "s.json")))
    r = conv.handle({"from": "+14165551234", "text": "STOP", "channel": "sms"})
    assert r["action"] == "opt_out" and r["sent"] == "sms"
    assert m.send_with_fallback({"phone": "+14165551234"}, "s", "Hi", "https://p")["suppressed"]
    conv.handle({"from": "+14165551234", "text": "START", "channel": "sms"})
    assert m.send_with_fallback({"phone": "+14165551234"}, "s", "Hi", "https://p")["delivered_via"] == "sms"


def test_inbound_sin_is_redacted_in_transcript(tmp_path):
    m = mk(tmp_path); st = Store(str(tmp_path / "s.json")); conv = Conversation(m, st)
    conv.handle({"from": "+14165551234", "text": "my sin is 123-456-789", "channel": "sms"})
    assert "123-456-789" not in str(st.d["transcript"])


def test_renewal_surfaces_ird_and_home_value_to_broker_and_borrower(tmp_path):
    from mortgageloanops.pipeline import process_application
    from mortgageloanops.samples import SAMPLES
    r = process_application(SAMPLES["renewal_ird"], mk(tmp_path))
    text = " ".join(r["broker_handoff"]["summary"])
    assert "home value" in text and "prepayment penalty" in text and "Refinance analysis" in text
    assert r["borrower_message"]["delivered_via"] == "sms" and not r["borrower_message"]["blocked_by_guardrail"]
    sent = next(tmp_path.glob("sms-*.json")).read_text()
    assert "indicative value" in sent and "prepayment penalty" in sent and "not an appraisal" in sent
    assert r["current_ltv"] == round(400000 / r["home_value"]["estimate"] * 100, 1)


def test_purchase_file_with_value_shows_home_value_in_broker_summary(tmp_path):
    from mortgageloanops.pipeline import process_application
    from mortgageloanops.samples import SAMPLES
    r = process_application(SAMPLES["purchase_fthb"], mk(tmp_path))
    assert any("Indicative home value" in l for l in r["broker_handoff"]["summary"])


def test_market_data_lookup_and_provenance():
    from mortgageloanops import market
    c = market.context()
    assert c["posted_5yr_conventional"]["rate"] > 0 and "not a lender quote" in c["scope"]
    r = market.rate_on("prime_rate", "2020-01-05")
    assert r["date"] <= "2020-01-05" and r["rate"] == 3.95
    import pytest as _p
    with _p.raises(ValueError):
        market.rate_on("prime_rate", "1999-01-01")


def test_renewal_without_posted_rate_uses_market_and_flags_it(tmp_path):
    from mortgageloanops.pipeline import process_application
    from mortgageloanops.samples import SAMPLES
    app = {k: v for k, v in SAMPLES["renewal_ird"].items() if k != "current_posted_rate"}
    r = process_application(app, mk(tmp_path))
    assert "posted_rate_assumption" in r and any("Market context" in l for l in r["broker_handoff"]["summary"])
    assert "%" not in str(next(tmp_path.glob("sms-*.json")).read_text())  # no rates in borrower message


# ── AgentCore tests ───────────────────────────────────────────────────────────

def test_agentcore_handle_no_model_returns_graceful_message():
    import os
    from mortgageloanops.agentcore import handle
    env_backup = os.environ.pop("MLO_BEDROCK_MODEL_ID", None)
    try:
        r = handle({"inputText": "What is the GDS limit?", "sessionId": "test-1"})
        assert "not configured" in r["response"]["responseBody"]["TEXT"]["body"]
        assert r["sessionId"] == "test-1"
    finally:
        if env_backup:
            os.environ["MLO_BEDROCK_MODEL_ID"] = env_backup


def test_agentcore_handle_empty_input():
    from mortgageloanops.agentcore import handle
    r = handle({"inputText": "", "sessionId": "test-2"})
    assert "No question" in r["response"]["responseBody"]["TEXT"]["body"]


def test_agentcore_handle_guardrail_blocks_prohibited_input():
    from mortgageloanops.agentcore import handle
    r = handle({"inputText": "guarantee me approval for this mortgage", "sessionId": "test-3"})
    body = r["response"]["responseBody"]["TEXT"]["body"]
    assert "guarantee" not in body.lower() or "can't" in body.lower() or "won't" in body.lower()


def test_agentcore_response_envelope_shape():
    from mortgageloanops.agentcore import handle
    r = handle({"inputText": "", "sessionId": "envelope-check"})
    assert "messageVersion" in r
    assert "response" in r and "responseBody" in r["response"]
    assert "TEXT" in r["response"]["responseBody"]
    assert "sessionId" in r
