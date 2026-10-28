# Best of WhatsApp — Submission Notes

*For the Meta-sponsored "Best of WhatsApp" prize ($10,000 USD).*

MortgageLoanOps uses WhatsApp as a **primary borrower communication channel** via AWS End User Messaging Social. It implements both WhatsApp message types that matter for a real production mortgage workflow.

---

## Two WhatsApp message types, both implemented

### 1. Session reply (`build_whatsapp`)

Used when the borrower has already messaged in (purchase enquiry, question via inbound SNS handler). Within the 24-hour messaging window, a session reply is sent with the file summary and secure upload portal link.

```python
# messaging.py
def build_whatsapp(self, to: str, body: str) -> dict:
    msg = {"messaging_product": "whatsapp", "to": to, "type": "text", "text": {"body": body}}
    return {
        "originationPhoneNumberId": self.config["whatsapp_phone_number_id"],
        "metaApiVersion": self.config["meta_api_version"],
        "message": json.dumps(msg).encode("utf-8"),
    }
```

Sent via `socialmessaging.send_whatsapp_message(...)`.

---

### 2. Template message (`build_whatsapp_template`)

Used for **renewal reminders** — a business-initiated message sent to a borrower whose mortgage is coming up for renewal. This bypasses the 24-hour contact window and requires a template pre-approved in Meta Business Manager.

```python
# messaging.py
def build_whatsapp_template(self, to, template_name, lang_code="en_US", components=None) -> dict:
    msg = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "template",
        "template": {"name": template_name, "language": {"code": lang_code}},
    }
    if components:
        msg["template"]["components"] = components
    return {
        "originationPhoneNumberId": self.config["whatsapp_phone_number_id"],
        "metaApiVersion": self.config["meta_api_version"],
        "message": json.dumps(msg).encode("utf-8"),
    }
```

The pipeline calls this automatically for every RENEWAL file with a phone number:

```python
# pipeline.py — renewal path
wa_req = messenger.build_whatsapp_template(
    to=borrower["phone"],
    template_name="mortgage_renewal_reminder",
    lang_code="en_US",
    components=[{"type": "body", "parameters": [
        {"type": "text", "text": first_name},
        {"type": "text", "text": f"${penalty:,.0f}"},
        {"type": "text", "text": portal_url},
    ]}],
)
socialmessaging.send_whatsapp_message(**wa_req)
```

**Why this matters:** Mortgage renewal reminders are the canonical business-initiated WhatsApp use case. A borrower whose 5-year fixed is expiring in 90 days has not recently messaged the broker — the session window is closed. A template message is the *only* correct channel.

---

## Channel role in the fallback chain

```
RCS (if configured)
  └─ 5 s timeout → SMS
       └─ 5 s timeout → WhatsApp (session reply via EUM Social)
            └─ 5 s timeout → SES Email
                 └─ portal URL (always available)
```

For RENEWAL files, a WhatsApp template is attempted **before** the fallback chain runs. This means a renewal borrower may receive the template notification *and* a follow-up via the fallback chain — intentional, since the template is a proactive alert while the session reply confirms receipt of their file.

---

## Inbound WhatsApp handling

Inbound WhatsApp messages arrive via the SNS topic → `inbound_handler` Lambda. The conversation state machine (`conversation.py`) handles:

| Keyword | Response |
|---|---|
| `STOP` | Added to suppression list; no further messages sent |
| `START` | Removed from suppression list |
| `HELP` | Explains the service and lists available commands |
| `BROKER` | Triggers broker callback request |
| *(anything else)* | Passed to the Bedrock Converse agent for Q&A |

---

## Running the WhatsApp demo (no AWS account needed)

```bash
python -m mortgageloanops demo
cat outbox/whatsapp-template-*.json   # shows the Meta Cloud API template payload
cat outbox/whatsapp-*.json            # shows the session reply payload
```

The template outbox file contains the exact JSON that would be POSTed to the Meta Cloud API via AWS EUM Social:

```json
{
  "messaging_product": "whatsapp",
  "to": "+14165559876",
  "type": "template",
  "template": {
    "name": "mortgage_renewal_reminder",
    "language": {"code": "en_US"},
    "components": [
      {"type": "body", "parameters": [
        {"type": "text", "text": "Daniel"},
        {"type": "text", "text": "$3,247"},
        {"type": "text", "text": "https://portal.example.com/file/demo"}
      ]}
    ]
  }
}
```

---

## WhatsApp compliance features

- **STOP suppression**: respected before any WhatsApp send; stored in `compliance.py`
- **Quiet hours**: configurable per channel; WhatsApp messages respect a phone-channel quiet window
- **Consent gating**: optional per-contact WhatsApp consent flag checked before send
- **No rate quotes outbound**: the guardrail (`guardrail.py`) blocks any message containing a rate figure, approval promise or request for sensitive data — ensuring the WhatsApp channel never becomes an unlicensed advice channel
- **Audit trail**: every send attempt (success or fallback) is logged with timestamp, channel and error detail

---

## Template pre-approval workflow (production)

1. Create the template in Meta Business Manager with approved variables: `{{1}}` (borrower first name), `{{2}}` (penalty amount), `{{3}}` (portal URL)
2. Register the template name in AWS End User Messaging Social (linked to the WhatsApp Business Account)
3. Set `MLO_WHATSAPP_PHONE_NUMBER_ID` from the EUM Social console
4. The pipeline uses `template_name="mortgage_renewal_reminder"` — swap for the approved name if different

See [docs/AWS_SETUP.md](AWS_SETUP.md) for the full environment variable reference.
