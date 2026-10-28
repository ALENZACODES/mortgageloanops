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
