import json, time
from mortgageloanops.messaging import Messenger

CFG = {"sms_origination": "+15551230000", "whatsapp_phone_number_id": "phone-number-id-abc", "meta_api_version": "v20.0", "email_from": "ops@example.com"}
CONTACT = {"phone": "+14165550100", "email": "b@example.com"}


class FakeSMS:
    def __init__(self, fail=False, delay=0): self.calls, self.fail, self.delay = [], fail, delay
    def send_text_message(self, **kw):
        self.calls.append(kw); time.sleep(self.delay)
        if self.fail: raise RuntimeError("ThrottlingException")
        return {"MessageId": "sms-1"}

class FakeWA:
    def __init__(self, fail=False): self.calls, self.fail = [], fail
    def send_whatsapp_message(self, **kw):
        self.calls.append(kw)
        if self.fail: raise RuntimeError("InvalidParametersException")
        return {"messageId": "wa-1"}

class FakeSES:
    def __init__(self): self.calls = []
    def send_email(self, **kw): self.calls.append(kw); return {"MessageId": "ses-1"}


def mk(sms=None, wa=None, ses=None, timeout=5.0):
    clients = {"pinpoint-sms-voice-v2": sms or FakeSMS(), "socialmessaging": wa or FakeWA(), "sesv2": ses or FakeSES()}
    return Messenger(live=True, clients=clients, timeout=timeout, config=CFG), clients


def test_sms_request_shape_matches_end_user_messaging_sms_api():
    m, c = mk()
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://p")
    assert r["delivered_via"] == "sms"
    call = c["pinpoint-sms-voice-v2"].calls[0]
    assert call == {"DestinationPhoneNumber": "+14165550100", "OriginationIdentity": "+15551230000", "MessageBody": "hello", "MessageType": "TRANSACTIONAL"}


def test_falls_back_sms_to_whatsapp_with_social_api_shape():
    m, c = mk(sms=FakeSMS(fail=True))
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://p")
    assert r["delivered_via"] == "whatsapp"
    call = c["socialmessaging"].calls[0]
    assert call["originationPhoneNumberId"] == "phone-number-id-abc" and call["metaApiVersion"] == "v20.0"
    msg = json.loads(call["message"]); assert msg["messaging_product"] == "whatsapp" and msg["to"] == "+14165550100" and msg["text"]["body"] == "hello"


def test_falls_back_to_ses_then_uses_sesv2_shape():
    m, c = mk(sms=FakeSMS(fail=True), wa=FakeWA(fail=True))
    r = m.send_with_fallback(CONTACT, "Subj", "hello", "https://p")
    assert r["delivered_via"] == "email"
    call = c["sesv2"].calls[0]
    assert call["FromEmailAddress"] == "ops@example.com" and call["Destination"]["ToAddresses"] == ["b@example.com"]
    assert call["Content"]["Simple"]["Subject"]["Data"] == "Subj"


def test_timeout_triggers_fallback():
    m, c = mk(sms=FakeSMS(delay=0.6), timeout=0.2)
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://p")
    assert r["attempts"][0]["ok"] is False and "timeout" in r["attempts"][0]["error"]
    assert r["delivered_via"] == "whatsapp"


def test_all_channels_fail_goes_to_portal():
    m, c = mk(sms=FakeSMS(fail=True), wa=FakeWA(fail=True))
    c["sesv2"].send_email = lambda **k: (_ for _ in ()).throw(RuntimeError("MessageRejected"))
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://portal/x")
    assert r["delivered_via"] == "portal" and r["portal_url"] == "https://portal/x"


def test_guardrail_blocks_before_any_aws_call():
    m, c = mk()
    r = m.send_with_fallback(CONTACT, "s", "You are approved for $400,000 at 3.99%", "https://p")
    assert r["delivered_via"] is None and r["blocked_by_guardrail"]
    assert not c["pinpoint-sms-voice-v2"].calls and not c["socialmessaging"].calls and not c["sesv2"].calls


def test_dry_run_writes_outbox_and_needs_no_aws(tmp_path):
    m = Messenger(live=False, outbox_dir=str(tmp_path), config=CFG)
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://p")
    assert r["delivered_via"] == "sms" and r["result"]["mode"] == "dry-run"
    assert len(list(tmp_path.glob("sms-*.json"))) == 1


RCS_CFG = dict(CFG, rcs_agent_arn="arn:aws:sms-voice:us-east-1:123456789012:rcs-agent/rcs-a1b2c3d4")


def mk_rcs(sms=None, **kw):
    clients = {"pinpoint-sms-voice-v2": sms or FakeSMS(), "socialmessaging": FakeWA(), "sesv2": FakeSES()}
    return Messenger(live=True, clients=clients, config=RCS_CFG, **kw), clients


def test_rcs_goes_first_with_documented_request_shape():
    m, c = mk_rcs()
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://p")
    assert r["delivered_via"] == "rcs" and r["attempts"][0]["channel"] == "rcs"
    assert c["pinpoint-sms-voice-v2"].calls[0] == {"DestinationPhoneNumber": "+14165550100", "OriginationIdentity": RCS_CFG["rcs_agent_arn"], "MessageBody": "hello"}


def test_rcs_failure_falls_back_to_sms_then_whatsapp():
    class RcsDown(FakeSMS):
        def send_text_message(self, **kw):
            self.calls.append(kw)
            if kw["OriginationIdentity"].startswith("arn:"): raise RuntimeError("RCS agent not active")
            return {"MessageId": "sms-ok"}
    m, c = mk_rcs(sms=RcsDown())
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://p")
    assert [a["channel"] for a in r["attempts"]] == ["rcs", "sms"] and r["delivered_via"] == "sms"
    assert c["pinpoint-sms-voice-v2"].calls[1]["OriginationIdentity"] == "+15551230000"


def test_rcs_skipped_when_no_agent_configured():
    m, c = mk()          # CFG has no rcs_agent_arn
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://p")
    assert r["attempts"][0]["channel"] == "sms"


def test_rcs_message_is_guardrailed_too():
    m, c = mk_rcs()
    r = m.send_with_fallback(CONTACT, "s", "Rates from 3.99% today", "https://p")
    assert r["delivered_via"] is None and not c["pinpoint-sms-voice-v2"].calls


def test_dry_run_rcs_writes_outbox(tmp_path):
    m = Messenger(live=False, outbox_dir=str(tmp_path), config=RCS_CFG)
    r = m.send_with_fallback(CONTACT, "s", "hello", "https://p")
    assert r["delivered_via"] == "rcs" and len(list(tmp_path.glob("rcs-*.json"))) == 1


def test_build_whatsapp_template_shape():
    m, _ = mk()
    req = m.build_whatsapp_template(
        to="+14165550100",
        template_name="mortgage_qualification_result",
        lang_code="en_US",
        components=[{"type": "body", "parameters": [{"type": "text", "text": "John"}]}],
    )
    import json as _json
    msg = _json.loads(req["message"])
    assert msg["type"] == "template"
    assert msg["template"]["name"] == "mortgage_qualification_result"
    assert msg["template"]["language"]["code"] == "en_US"
    assert len(msg["template"]["components"]) == 1
    assert req["originationPhoneNumberId"] == "phone-number-id-abc"


def test_whatsapp_template_renewal_pipeline(tmp_path):
    """Renewal pipeline auto-sends a WhatsApp template for business-initiated outbound."""
    from mortgageloanops.pipeline import process_application
    from mortgageloanops.messaging import Messenger
    import json
    m = Messenger(live=False, outbox_dir=str(tmp_path), config={
        "sms_origination": "+15551230000",
        "whatsapp_phone_number_id": "phone-number-id-abc",
        "meta_api_version": "v20.0",
        "email_from": "ops@example.com",
    })
    app = {
        "type": "RENEWAL",
        "borrower": {"name": "Test Borrower", "phone": "+16135550100", "email": "t@example.com"},
        "province": "ON",
        "credit_score": 720,
        "balance": 350000,
        "contract_rate": 5.25,
        "months_remaining": 24,
        "is_variable": False,
        "current_posted_rate": 7.19,
        "original_posted_rate": 5.39,
        "comparison_rate": 4.79,
        "new_rate": 4.50,
        "amort_years_remaining": 18,
    }
    result = process_application(app, messenger=m)
    # WhatsApp template was queued
    assert result.get("whatsapp_template_sent", {}).get("status") == "queued"
    assert result["whatsapp_template_sent"]["template"] == "mortgage_renewal_reminder"
    # Outbox contains a WhatsApp template file
    template_files = list(tmp_path.glob("whatsapp-template-*.json"))
    assert len(template_files) == 1
    payload = json.loads(template_files[0].read_text())
    msg = json.loads(payload["request"]["message"])
    assert msg["type"] == "template"
    assert msg["template"]["name"] == "mortgage_renewal_reminder"
    assert msg["template"]["language"]["code"] == "en_US"
    # Body parameters include borrower first name, penalty amount, portal URL
    body_component = msg["template"]["components"][0]
    assert body_component["type"] == "body"
    params = [p["text"] for p in body_component["parameters"]]
    assert "Test" in params[0]   # first name
    assert "$" in params[1]       # penalty formatted as currency
    assert "portal" in params[2]  # portal URL
