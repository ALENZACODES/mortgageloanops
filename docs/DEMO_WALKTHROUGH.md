# Two-minute walkthrough

No AWS account is needed. Requires Python 3.10+.

```bash
git clone https://github.com/ALENZACODES/mortgageloanops && cd mortgageloanops
python -m mortgageloanops demo          # 3 sample files: first-time buyer, renewal, refinance
ls outbox                               # the exact AWS requests that would be sent (dry-run)
python -m mortgageloanops serve 8000    # web UI: http://localhost:8000
pytest -q                               # 77 tests incl. 10,000-case property tests
```

## What to look for

1. **Qualification** – the stress-test rate is `max(contract + 2%, 5.25%)`; GDS/TDS are computed from a real amortisation (semi-annual compounding), not a shortcut.
2. **Insured rules** – minimum down payment, 30-year insured amortisation for eligible buyers, and the $1.5M cap.
3. **IRD** – a renewal file shows the prepayment penalty (3 months' interest vs. interest-rate differential) and a break-even refinance analysis.
4. **Benchmark** – an indicative home value from regional index curves (an estimate, not an appraisal).
5. **Screening** – always `NOT_SCREENED` unless a list is supplied; it never reports a person as "clear".
6. **Messaging** – open the files in `outbox/`: RCS (only if `MLO_RCS_AGENT_ARN` is set), SMS, WhatsApp and SES requests in the documented AWS API shapes.
7. **Guardrail** – try a message containing "approved", "3.99%", or "send your SIN"; it is blocked before any channel is tried.
8. **AgentCore broker Q&A** – `python scripts/agentcore_demo.py` shows the full agentic loop: broker question → Bedrock tool-use → qualify calculator → guardrailed answer in the AgentCore envelope.
9. **STOP/START** – the inbound handler suppresses a number after STOP and restores it after START.

## What is real and what is pending

| Area | Status |
|---|---|
| Mortgage maths, IRD, home-value indexing, guardrail, policy, conversation logic | Implemented and covered by tests |
| AWS request shapes (SMS, RCS, WhatsApp, SES, Bedrock Converse) | Implemented; asserted against **fake clients** |
| Live sending on a real AWS account | **Not yet run.** Use `scripts/live_smoke.py` once an origination number, WhatsApp number and verified SES identity exist |
| Deployment (Lambda + HTTP API + SNS via SAM) | Template written; **not yet deployed** |
| Bedrock AgentCore | **Implemented.** `agentcore.py` + `lambda_agentcore.py`; `scripts/agentcore_demo.py` shows the end-to-end broker Q&A flow |
| AWS Partner / ACE registration | Not completed |
