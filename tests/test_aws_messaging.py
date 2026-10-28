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
