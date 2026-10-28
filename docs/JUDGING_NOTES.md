# Judging notes — MortgageLoanOps

Mapped to the official criteria for reviewers.

---

## Technical Execution (40 %)

### AWS CDS services used

| Service | Where | API call |
|---|---|---|
| **AWS End User Messaging — RCS** | `messaging.py` `build_rcs` / `_send("rcs")` | `pinpoint-sms-voice-v2.send_text_message` with an RCS agent ARN as `OriginationIdentity` |
| **AWS End User Messaging — SMS** | `messaging.py` `build_sms` / `_send("sms")` | `pinpoint-sms-voice-v2.send_text_message` |
| **AWS End User Messaging Social — WhatsApp** | `messaging.py` `build_whatsapp` / `build_whatsapp_template` / `_send("whatsapp")` | `socialmessaging.send_whatsapp_message` with Meta Cloud API message payload |
| **Amazon SES** | `messaging.py` `build_email` / `_send("email")` | `sesv2.send_email` |
| **Amazon Bedrock (Converse + tool-use)** | `agent.py` `Agent.ask` | `bedrock-runtime.converse` with `toolConfig`; model calls real calculators |
| **AWS Bedrock AgentCore** | `agentcore.py` + `lambda_agentcore.py` | Action-group executor; `AgentCoreFunction` in `infra/template.yaml` |

### Channel fallback order and timeout
```
RCS (if MLO_RCS_AGENT_ARN set)
  └─ 5 s timeout → SMS
       └─ 5 s timeout → WhatsApp (EUM Social)
            └─ 5 s timeout → SES Email
                 └─ secure portal URL (always available)
```
`send_with_fallback` in `messaging.py` (line ~120).

### WhatsApp — two message types
- **Text messages** (`build_whatsapp`): borrower-reply context.
- **Template messages** (`build_whatsapp_template`): business-initiated outbound, bypasses the 24-hour messaging window; template must be pre-approved in Meta Business Manager.

### Architecture
`docs/ARCHITECTURE.svg` — full system diagram.

### Inbound two-way messaging
SNS topic → `inbound_handler` Lambda → `conversation.py` → `Conversation.handle`.  
Handles STOP / START / HELP / broker-callback keywords; redacts PII from the transcript.

### Agentic workflow (end-to-end)
1. Broker submits a question to Bedrock AgentCore.
2. AgentCore invokes `AgentCoreFunction` (`lambda_agentcore.py`).
3. `agentcore.handle` calls `Agent.ask` which opens a Bedrock Converse tool-use loop.
4. Model calls `qualify_purchase`, `estimate_prepayment_penalty`, or `estimate_home_value`.
5. Results from real Canadian mortgage calculators come back; model synthesises.
6. Guardrail applied to the answer; response returned in the AgentCore envelope.

Run it without an AWS account:
```bash
python scripts/agentcore_demo.py
```

### Reproducibility
```bash
git clone https://github.com/ALENZACODES/mortgageloanops && cd mortgageloanops
pip install -e ".[dev]"
pytest -q                  # 77 tests; includes 10,000-case property tests
python -m mortgageloanops demo   # dry-run: 3 sample files, inspect outbox/
python scripts/agentcore_demo.py # AgentCore agentic loop dry-run
```

### Observability
`lambda_handler.py` emits CloudWatch custom metrics under the `MortgageLoanOps` namespace:
`FileProcessed`, `ProcessLatencyMs`, `QualifyPass`, `ProcessError`, `InboundMessage`, `ConversationAction`.

---

## Potential Value / Impact (20 %)

**Problem:** Canadian mortgage brokers lose leads between first inquiry and first useful conversation. A typical file takes 20–40 minutes of broker time before the borrower knows whether they qualify.

**Measurable impact per file:**
- Qualification result, stress-test rate, GDS/TDS → delivered to borrower in < 30 s.
- IRD prepayment penalty estimate → broker and borrower both receive it on deal intake.
- Indicative home value (regional benchmark curves) → surfaces immediately for renewals and refinances.
- Current BoC 5-yr conventional posted rate → auto-filled for renewals missing lender data.

**Canadian market scope:**  
~500,000 mortgage renewals per year in Canada; the broker channel handles ~40% of new originations (CMHC). Each percentage point of friction reduction at intake scales across thousands of files.

---

## Functionality (10 %)

| Capability | Status |
|---|---|
| B-20 stress test (semi-annual compounding, GDS, TDS) | ✅ `qualify.py` |
| Insured-mortgage rules (Dec 15 2024: $1.5M cap, 30-yr amort for FTBs/new builds) | ✅ `insured.py` |
| IRD penalty (posted-rate and comparison-rate methods, 3-month interest floor) | ✅ `ird.py` |
| Break-even refinance analysis | ✅ `ird.refinance_analysis` |
| Regional benchmark home value (not an appraisal) | ✅ `homevalue.py` |
| Live BoC rate feed for renewals | ✅ `market.py` |
| Guardrail (7 rules, NFKC normalisation, PII redaction) | ✅ `guardrail.py` |
| Send-time compliance policy (STOP/START, consent, quiet hours) | ✅ `compliance.py` |
| Inbound two-way conversation (SNS → Lambda → state) | ✅ `conversation.py` |
| Bedrock Converse tool-use agent | ✅ `agent.py` |
| AgentCore action-group executor | ✅ `agentcore.py` + `lambda_agentcore.py` |
| WhatsApp template messages | ✅ `messaging.build_whatsapp_template` |
| CloudWatch custom metrics | ✅ `lambda_handler._emit` |
| SAM template (Lambda + HTTP API + SNS + AgentCore function) | ✅ `infra/template.yaml` |

---

## Creativity (10 %)

- Canadian mortgage compliance (B-20, insured rules, IRD) is not available in any AWS sample or public template; it was built from first principles.
- The guardrail prevents a *licensed* channel from acting like an unlicensed one — rate quotes and approval promises are blocked before any AWS send call.
- The channel fallback order mirrors real broker workflow: rich (RCS) → reliable (SMS) → where borrowers actually are (WhatsApp) → always-on (email).
- The BoC rate feed is sourced from public data and auto-fills the IRD calculation when the lender posted rate is missing — reducing a common data-gap in broker CRMs.

---

## Demo Presentation (20 %)

- **Demo video:** https://youtu.be/s4xR80V-mJ8
- **Runnable demo (no AWS account needed):**
  ```bash
  python -m mortgageloanops demo
  python scripts/agentcore_demo.py
  ```
- **DEMO_WALKTHROUGH.md** — step-by-step guide to what to look for in each output.

---

## Observability (production-readiness signal for CDS PMs)

CloudWatch custom metrics emitted by `lambda_handler._emit` (namespace `MortgageLoanOps`, gated by `MLO_LIVE`):

| Metric | Dimensions | What it shows |
|---|---|---|
| `FileProcessed` | Kind (purchase/renewal/homevalue) | Volume and mix by file type |
| `ProcessLatencyMs` | Kind | P50/P99 processing time per file type |
| `QualifyPass` | Kind | Approval rate for monitoring drift |
| `ProcessError` | Kind | Error rate per pipeline path |
| `InboundMessage` | Channel (sms/whatsapp/rcs) | Inbound channel breakdown |
| `ConversationAction` | Action (stop/start/help/broker/response) | Conversation engagement rates |

These feed naturally into a CloudWatch dashboard and alarm on `ProcessError > 0` or `QualifyPass` drift — standard production SRE practice.

---

## Quick reference for reviewers

```bash
# See the full agentic loop in under 10 seconds:
python scripts/agentcore_demo.py

# Run all 78 tests (including 10,000-case property test):
pytest -q

# See a renewal file auto-fill the BoC posted rate and emit market context:
python -m mortgageloanops demo 2>&1 | grep -A 20 "renewal_ird"
```

All three commands require only Python 3.10+ and no AWS account or API key.
