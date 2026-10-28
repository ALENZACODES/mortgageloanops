# MortgageLoanOps

> **AWS CDS Agentic AI Partner Hackathon — Oct 2026**
> 6 AWS services · 79 tests · runs dry-run with zero AWS credentials
> [`python scripts/agentcore_demo.py`](scripts/agentcore_demo.py) — full agentic loop in ~2 s · [Judging notes](docs/JUDGING_NOTES.md) · [WhatsApp prize](docs/WHATSAPP_PRIZE.md)

Canadian mortgage operations on AWS in one small, dependency-free Python app. It combines three tools:

| Module | What it does |
|---|---|
| **LendOps** (`qualify`, `insured`, `lenders`, `kyc`, `guardrail`) | OSFI B-20 style stress test, GDS/TDS, Dec 15 2024 insured-mortgage rules, lender-category matching, screening interface, outbound-message guardrail |
| **IRD** (`ird`) | Prepayment penalty (3 months' interest vs. interest-rate differential, comparison-rate and posted-rate methods) and a break-even refinance analysis |
| **Benchmark** (`homevalue`, `index_anchors`) | Indicative home value by indexing a purchase price with regional benchmark curves, ported from the Benchmark Home Value project |

**Also included:** a Bedrock Q&A agent that must call the real calculators for every number (`agent.py`, Amazon Bedrock Converse tool use; not the AgentCore runtime), two-way messaging that handles inbound SMS/WhatsApp replies with STOP/START/HELP/BROKER handling (`conversation.py`), and Lambda handlers plus a SAM template (`lambda_handler.py`, `infra/template.yaml`).

Borrower messages go out through **AWS End User Messaging SMS and RCS**, **AWS End User Messaging Social (WhatsApp)** and **Amazon SES**, with a 5-second per-channel timeout and a secure-portal fallback. Channel order: **RCS** (when `MLO_RCS_AGENT_ARN` is set) → SMS → WhatsApp → email → portal. Every message passes a guardrail first (rate quotes, approval promises, guarantees, pressure language, requests for SIN/card/password/one-time codes, and leaked SIN/card numbers; text is Unicode-normalised so zero-width or full-width tricks don't slip through). Then a send-time policy applies (`compliance.py`): STOP suppression list, optional per-channel consent, and optional quiet hours for phone channels. Logs and transcripts redact SIN-, card- and email-like strings.

> Status: working prototype. Everything below marked "tested" is covered by the test suite. Live AWS sending is implemented against the documented API shapes and tested with fake clients; it has not been run against a real AWS account in this repository's CI. See [Limitations](#limitations).

## Quick start (no AWS account needed)

```bash
git clone https://github.com/ALENZACODES/mortgageloanops && cd mortgageloanops
python -m mortgageloanops demo        # runs 3 sample files, writes the would-be AWS requests to ./outbox
python -m mortgageloanops serve 8000  # web UI at http://localhost:8000
python scripts/agentcore_demo.py      # AgentCore end-to-end broker Q&A (dry-run, no AWS account needed)
pip install pytest && pytest -q       # 79 tests incl. a 10,000-case property test
```

Requires Python 3.10+. No third-party packages are needed for dry-run mode.

## Live AWS mode

```bash
pip install boto3
export MLO_LIVE=1 AWS_REGION=ca-central-1
export MLO_SMS_ORIGINATION=+1XXXXXXXXXX                 # registered origination number / pool ID
export MLO_RCS_AGENT_ARN=arn:aws:sms-voice:...:rcs-agent/rcs-...   # optional: enables the RCS channel (agent must be Active)
export MLO_WHATSAPP_PHONE_NUMBER_ID=phone-number-id-... # from AWS End User Messaging Social
export MLO_EMAIL_FROM=ops@your-verified-domain.com      # verified SES identity
python -m mortgageloanops serve 8000
python scripts/agentcore_demo.py  # AgentCore end-to-end broker Q&A (dry-run)
```

See [docs/AWS_SETUP.md](docs/AWS_SETUP.md) and [infra/iam-policy.json](infra/iam-policy.json).

## Deploy and prove it live

```bash
sam build && sam deploy --guided      # uses infra/template.yaml (Lambda + HTTP API + SNS topic)
MLO_LIVE=1 python scripts/live_smoke.py +1YOURMOBILE you@example.com   # one real message per configured channel (RCS if set, SMS, WhatsApp, SES)
```
Point your SMS number's / WhatsApp number's two-way destination at the SNS topic output to enable inbound replies.

Step-by-step demo and a plain table of what is real vs. pending: [docs/DEMO_WALKTHROUGH.md](docs/DEMO_WALKTHROUGH.md)

## How a file flows

`intake → screening (honest: NOT_SCREENED without a list) → B-20 qualification → lender match → IRD/refinance (renewals) → home value → guardrail → RCS (if configured) → SMS → WhatsApp → email → portal → broker handoff + audit trail`

Architecture diagram: [docs/architecture.svg](docs/architecture.svg) · details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) · judging notes: [docs/JUDGING_NOTES.md](docs/JUDGING_NOTES.md)

## Limitations

- **Not legal, lending or compliance advice.** Outputs are estimates for a licensed broker to verify.
- **Lender registry** lists 34 lender names by category with *illustrative* category-level policy; `panel_verified` is `False` for all. It is not any lender's live guideline.
- **Screening** ships no sanctions/PEP data and never reports a person as "clear". Connect a licensed provider for production.
- **Home value** is a regional-index estimate (indicative anchors), not an appraisal or the full AVM. The AVM lives in the Benchmark Home Value project; its reported held-out accuracy is documented there.
- **Tests** are unit tests and randomized invariant tests (10,000 cases each), not a backtest against real lending outcomes.
- **Live AWS** paths (RCS, SMS, WhatsApp, SES, Bedrock Converse, SNS inbound parsing, SAM template) are verified with fake clients that assert request shapes and logic. They have **not** been run against a real AWS account from this repository yet; inbound event shapes should be confirmed against your own SNS payloads. Run `scripts/live_smoke.py` and `sam deploy` to prove them.

## License

MIT. See [LICENSE](LICENSE).
