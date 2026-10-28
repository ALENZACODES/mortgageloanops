import json
import pytest
from mortgageloanops.agent import Agent, tool_config, run_tool
from mortgageloanops.conversation import Conversation, Store, normalize_inbound
from mortgageloanops.messaging import Messenger
from mortgageloanops import lambda_handler as lh


class FakeBedrock:
    """Behaves like bedrock-runtime Converse: first asks for a tool, then answers using the tool result."""
    def __init__(self, final_text=None):
        self.calls, self.final_text = [], final_text
    def converse(self, **kw):
        self.calls.append(kw)
        last = kw["messages"][-1]
        if last["role"] == "user" and "text" in last["content"][0]:
            return {"stopReason": "tool_use", "output": {"message": {"role": "assistant", "content": [
                {"toolUse": {"toolUseId": "t1", "name": "qualify_purchase", "input": {"price": 750000, "down_payment": 150000, "annual_income": 200000, "contract_rate": 5.0}}}]}}}
        tr = last["content"][0]["toolResult"]["content"][0]["json"]
        text = self.final_text or f"Estimated stressed payment is ${tr['stressed_payment']:,.0f}/month; a licensed broker will confirm."
        return {"stopReason": "end_turn", "output": {"message": {"role": "assistant", "content": [{"text": text}]}}}


def test_agent_calls_real_tool_and_reports_its_number():
    a = Agent(client=FakeBedrock(), model_id="test-model")
    r = a.ask("Can a $200k earner afford $750k?")
    assert r["tool_calls"][0]["name"] == "qualify_purchase"
    exact = r["tool_calls"][0]["output"]["stressed_payment"]
    assert f"{exact:,.0f}" in r["answer"] and r["guardrail"]["allowed"]


def test_agent_request_shape_matches_bedrock_converse():
    fb = FakeBedrock(); Agent(client=fb, model_id="m1").ask("hi")
    c = fb.calls[0]
    assert c["modelId"] == "m1" and c["messages"][0] == {"role": "user", "content": [{"text": "hi"}]}
    names = [t["toolSpec"]["name"] for t in c["toolConfig"]["tools"]]
    assert set(names) == {"qualify_purchase", "estimate_prepayment_penalty", "estimate_home_value"}
    assert all("json" in t["toolSpec"]["inputSchema"] for t in c["toolConfig"]["tools"])


def test_agent_output_is_guardrailed():
    r = Agent(client=FakeBedrock("You are approved for $700,000 at 3.99%!"), model_id="m").ask("q")
    assert not r["guardrail"]["allowed"] and "3.99" not in r["answer"] and "approved" not in r["answer"]


def test_agent_requires_model_id(monkeypatch):
    monkeypatch.delenv("MLO_BEDROCK_MODEL_ID", raising=False)
    with pytest.raises(RuntimeError):
        Agent(client=object())


def test_run_tool_errors_are_returned_not_raised():
    assert "error" in run_tool("qualify_purchase", {"price": 1})
    assert "error" in run_tool("nope", {})
    assert run_tool("estimate_prepayment_penalty", {"balance": 400000, "contract_rate": 5.2, "months_remaining": 30, "original_posted_rate": 6.9, "current_posted_rate": 5.8})["penalty"]["penalty"] == 11000


def mkconv(tmp_path, agent=None):
    m = Messenger(live=False, outbox_dir=str(tmp_path / "ob"))
    return Conversation(m, Store(str(tmp_path / "s.json")), agent=agent)


def test_stop_start_and_silence_after_opt_out(tmp_path):
    c = mkconv(tmp_path)
    assert c.handle({"channel": "sms", "from": "+1416", "text": "STOP"})["action"] == "opt_out"
    assert c.handle({"channel": "sms", "from": "+1416", "text": "hello?"})["action"] == "ignored_opted_out"
    assert c.handle({"channel": "sms", "from": "+1416", "text": "start"})["action"] == "opt_in"
    assert c.handle({"channel": "sms", "from": "+1416", "text": "hello"})["action"] == "ack"
    assert json.loads((tmp_path / "s.json").read_text())["opted_out"] == []


def test_broker_callback_and_reply_on_same_channel(tmp_path):
    c = mkconv(tmp_path)
    r = c.handle({"channel": "whatsapp", "from": "+1647", "text": "Can a broker call me tomorrow?"})
    assert r["action"] == "callback_requested" and r["sent"] == "whatsapp"
    assert c.s.d["callbacks"][0]["from"] == "+1647"


def test_conversation_uses_agent_when_present(tmp_path):
    c = mkconv(tmp_path, agent=Agent(client=FakeBedrock(), model_id="m"))
    r = c.handle({"channel": "sms", "from": "+1905", "text": "what would my payment be?"})
    assert r["action"] == "agent_answer" and "stressed payment" in r["reply"]


def test_normalize_inbound_shapes():
    assert normalize_inbound({"originationNumber": "+1416", "messageBody": "hi"}) == [{"channel": "sms", "from": "+1416", "text": "hi"}]
    wa = {"entry": 1, "changes": [{"value": {"messages": [{"from": "14165550100", "text": {"body": "yo"}}]}}]}
    assert normalize_inbound({"whatsAppWebhookEntry": json.dumps(wa)}) == [{"channel": "whatsapp", "from": "+14165550100", "text": "yo"}]
    sns = {"Records": [{"Sns": {"Message": json.dumps({"originationNumber": "+1416", "messageBody": "STOP"})}}]}
    assert normalize_inbound(sns)[0]["text"] == "STOP"


def test_lambda_api_and_inbound(tmp_path, monkeypatch):
    monkeypatch.setattr(lh, "_messenger", Messenger(live=False, outbox_dir=str(tmp_path)))
    h = lh.api_handler({"rawPath": "/health", "requestContext": {"http": {"method": "GET"}}})
    assert h["statusCode"] == 200 and json.loads(h["body"])["lenders_in_registry"] == 34
    from mortgageloanops.samples import SAMPLES
    p = lh.api_handler({"rawPath": "/process", "requestContext": {"http": {"method": "POST"}}, "body": json.dumps(SAMPLES["purchase_fthb"])})
    assert p["statusCode"] == 200 and json.loads(p["body"])["qualification"]["passes"]
    bad = lh.api_handler({"rawPath": "/process", "httpMethod": "POST", "body": "{}"})
    assert bad["statusCode"] == 400
    monkeypatch.chdir(tmp_path); monkeypatch.setattr("mortgageloanops.lambda_handler.Store", lambda p: Store(str(tmp_path / "st.json")))
    i = lh.inbound_handler({"originationNumber": "+1416", "messageBody": "HELP"})
    assert i["handled"] == 1 and i["results"][0]["action"] == "help"


def test_sam_template_is_valid_yaml_with_both_functions():
    import re, pathlib
    t = pathlib.Path("infra/template.yaml").read_text()
    try:
        import yaml
    except ImportError:
        pytest.skip("pyyaml not installed")
    class L(yaml.SafeLoader): pass
    L.add_multi_constructor("!", lambda l, s, n: None)
    d = yaml.load(t, Loader=L)
    assert {"ApiFunction", "InboundFunction", "InboundTopic"} <= set(d["Resources"])
    assert d["Resources"]["ApiFunction"]["Properties"]["Handler"] == "mortgageloanops.lambda_handler.api_handler"
