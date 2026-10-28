# Devpost submission: copy/paste text and checklist

**Project name:** MortgageLoanOps

**Tagline:** Qualify, explain and message a Canadian mortgage file in minutes, over AWS End User Messaging and SES, without ever quoting a rate or promising an approval.

## Text description
Canadian mortgage brokers lose leads and time between the first inquiry and the first useful conversation. MortgageLoanOps triages each file and keeps the borrower informed on the channel they actually answer.

**What it does**
- **Qualification (LendOps):** OSFI B-20 style stress test (qualifying rate = max(contract + 2%, 5.25%)) using the correct Canadian semi-annual-compounding payment formula, GDS/TDS, the insured-mortgage rules in force since Dec 15 2024 ($1.5M price cap, 30-year insured amortization for first-time buyers and new builds), and matching against lender categories.
- **Renewals (IRD):** estimates the prepayment penalty (greater of three months' interest and the interest-rate differential, comparison-rate and posted-rate methods) and tells the broker whether breaking the mortgage pays off, with a break-even.
- **Home value (Benchmark):** indicative value by indexing a purchase price with regional benchmark curves, ported from the Benchmark Home Value project.
- **Bedrock agent + two-way conversation:** an agent answers borrower/broker questions by calling the real calculators (it never does the maths itself), and inbound SMS/WhatsApp replies are handled with opt-out (STOP), help and broker-callback logic.
- **Borrower messaging on AWS CDS:** after a guardrail check that blocks rate quotes, approval promises, guarantees, pressure language and requests for SIN/card/password/one-time codes, plus a send-time policy (STOP suppression, optional consent and quiet hours), the borrower is messaged through **AWS End User Messaging RCS** (via an RCS agent), then **SMS**, then **AWS End User Messaging Social (WhatsApp)**, then **Amazon SES**, with a 5-second per-channel timeout and a secure-portal fallback. Each file also produces an audit trail and a broker hand-off report.

**AWS services used (6):**
| Service | File | API call |
|---|---|---|
| AWS End User Messaging — RCS | `messaging.py` | `pinpoint-sms-voice-v2.send_text_message` (RCS agent ARN as OriginationIdentity) |
| AWS End User Messaging — SMS | `messaging.py` | `pinpoint-sms-voice-v2.send_text_message` |
| AWS End User Messaging Social — WhatsApp | `messaging.py` | `socialmessaging.send_whatsapp_message`; also `build_whatsapp_template()` for business-initiated outbound |
| Amazon SES | `messaging.py` | `sesv2.send_email` |
| Amazon Bedrock (Converse + tool-use) | `agent.py` | `bedrock-runtime.converse` with `toolConfig`; model must call real calculators — never free-forms the math |
| AWS Bedrock AgentCore | `agentcore.py` + `lambda_agentcore.py` | Action-group Lambda executor; broker Q&A via AgentCore envelope; `AgentCoreFunction` in `infra/template.yaml` |

**WhatsApp prize:** WhatsApp is a primary channel in the fallback chain, with two message types implemented:
- **Session reply** (`build_whatsapp`): sent when a borrower has already messaged in, within Meta's 24-hour window.
- **Template message** (`build_whatsapp_template`): sent automatically for every RENEWAL file — the canonical business-initiated use case where the 24-hour window is closed. The template `mortgage_renewal_reminder` sends the borrower's first name, estimated prepayment penalty amount and secure upload portal URL as named components. The pipeline calls `socialmessaging.send_whatsapp_message(originationPhoneNumberId, metaApiVersion, message)` and writes the exact Meta Cloud API JSON to the outbox for review.
- Inbound WhatsApp: STOP/START/HELP/BROKER commands handled; arbitrary questions routed to the Bedrock agent.
- Full detail: [docs/WHATSAPP_PRIZE.md](docs/WHATSAPP_PRIZE.md)

**Bedrock AgentCore:** `agentcore.py` implements the action-group Lambda protocol (`messageVersion`, `sessionId`, `response.responseBody.TEXT`). A broker-safe guardrail distinction is applied: rate quotes are allowed inbound from brokers (only `SENSITIVE_REQUEST` / `SENSITIVE_DATA_LEAK` blocked) but blocked outbound to borrowers. Run `python scripts/agentcore_demo.py` to see the full agentic loop without an AWS account.

**Verification:** 79 automated tests, including a 10,000-case randomized invariant test, request-shape tests for all AWS calls (RCS, SMS, WhatsApp session + WhatsApp template, SES, AgentCore envelope shape, guardrail policy, BoC rate feed provenance) using fake clients, and timeout/fallback tests. Tests were checked to fail when the code is deliberately broken.

**Honest limitations:** lender policy is illustrative by category (34 lender names, none panel-verified); identity/PEP screening is an interface that never reports "clear"; the home value is an indicative index estimate, not an appraisal; the AI agent uses Amazon Bedrock Converse tool use **and** is wrapped in a Bedrock AgentCore action-group Lambda (`agentcore.py` + `lambda_agentcore.py`); the AWS paths are tested with fake clients and have not yet been run on a live account by the author of this text. Update this line after you run `scripts/live_smoke.py` and deploy with `sam deploy`.

## Submission checklist
| Item | Status |
|---|---|
| Public repo with MIT license visible in About | Done: https://github.com/ALENZACODES/mortgageloanops |
| Run instructions | Done (README) |
| Architecture diagram | Done: docs/ARCHITECTURE.svg |
| Text description | Done (above) |
| ~3-minute demo video | Done: 2:58, silent, captioned, dry-run. **Record a short live-AWS clip and voiceover before submitting if you can** |
| Deployed project URL or interaction instructions | `sam deploy` template + Lambda handlers included; **not deployed yet, needs your AWS account** |
| AWS Partner Central / ACE opportunity ID with campaign code "AWS CDS Agentic AI Hackathon -Sept. 2026." | **Needs you** (your AWS Partner Central login) |
| Devpost registration / accepting rules | **Needs you** (the contest is for AWS Partners; confirm your organization is eligible) |
