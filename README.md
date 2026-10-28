# MortgageLoanOps

Canadian mortgage operations on AWS in one small, dependency-free Python app. It combines three tools:

| Module | What it does |
|---|---|
| **LendOps** (`qualify`, `insured`, `lenders`, `kyc`, `guardrail`) | OSFI B-20 style stress test, GDS/TDS, Dec 15 2024 insured-mortgage rules, lender-category matching, screening interface, outbound-message guardrail |
| **IRD** (`ird`) | Prepayment penalty (3 months' interest vs. interest-rate differential, comparison-rate and posted-rate methods) and a break-even refinance analysis |
| **Benchmark** (`homevalue`, `index_anchors`) | Indicative home value by indexing a purchase price with regional benchmark curves, ported from the Benchmark Home Value project |

Borrower messages go out through **AWS End User Messaging SMS**, **AWS End User Messaging Social (WhatsApp)** and **Amazon SES**, with a 5-second per-channel timeout and a secure-portal fallback. Every message passes a guardrail first: no rate quotes, no approval promises, no guarantees.

> Status: working prototype. Everything below marked "tested" is covered by the test suite. Live AWS sending is implemented against the documented API shapes and tested with fake clients; it has not been run against a real AWS account in this repository's CI. See [Limitations](#limitations).

## Quick start (no AWS account needed)

```bash
git clone https://github.com/ALENZACODES/mortgageloanops && cd mortgageloanops
python -m mortgageloanops demo        # runs 3 sample files, writes the would-be AWS requests to ./outbox
python -m mortgageloanops serve 8000  # web UI at http://localhost:8000
pip install pytest && pytest -q       # 35 tests incl. a 10,000-case property test
```

Requires Python 3.10+. No third-party packages are needed for dry-run mode.

## Live AWS mode

```bash
pip install boto3
export MLO_LIVE=1 AWS_REGION=ca-central-1
export MLO_SMS_ORIGINATION=+1XXXXXXXXXX                 # registered origination number / pool ID
export MLO_WHATSAPP_PHONE_NUMBER_ID=phone-number-id-... # from AWS End User Messaging Social
export MLO_EMAIL_FROM=ops@your-verified-domain.com      # verified SES identity
python -m mortgageloanops serve 8000
```

See [docs/AWS_SETUP.md](docs/AWS_SETUP.md) and [infra/iam-policy.json](infra/iam-policy.json).

## How a file flows

`intake → screening (honest: NOT_SCREENED without a list) → B-20 qualification → lender match → IRD/refinance (renewals) → home value → guardrail → SMS → WhatsApp → email → portal → broker handoff + audit trail`

Architecture diagram: [docs/architecture.svg](docs/architecture.svg) · details: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)

## Limitations

- **Not legal, lending or compliance advice.** Outputs are estimates for a licensed broker to verify.
- **Lender registry** lists 34 lender names by category with *illustrative* category-level policy; `panel_verified` is `False` for all. It is not any lender's live guideline.
- **Screening** ships no sanctions/PEP data and never reports a person as "clear". Connect a licensed provider for production.
- **Home value** is a regional-index estimate (indicative anchors), not an appraisal or the full AVM. The AVM lives in the Benchmark Home Value project; its reported held-out accuracy is documented there.
- **Tests** are unit tests and randomized invariant tests (10,000 cases each), not a backtest against real lending outcomes.
- **Live AWS** paths are verified with fake clients that assert the exact request shapes; real delivery needs your AWS account, verified identities and registered numbers.

## License

MIT. See [LICENSE](LICENSE).
