# AWS setup for live mode

1. **SES**: verify a sender identity (domain or address). In the SES sandbox, recipient addresses must also be verified. Set `MLO_EMAIL_FROM`.
2. **AWS End User Messaging SMS**: register an origination identity (10DLC / toll-free / short code as required in your destination country) and set `MLO_SMS_ORIGINATION`. Sandbox destinations must be verified.
3. **AWS End User Messaging Social**: link a WhatsApp Business Account and phone number; set `MLO_WHATSAPP_PHONE_NUMBER_ID` (format `phone-number-id-...`). Outside the 24-hour customer-service window WhatsApp requires approved templates.
4. **IAM**: attach `infra/iam-policy.json` (scope `Resource` to your identities for production).
5. Run `MLO_LIVE=1 python -m mortgageloanops serve 8000` and POST a sample file to `/api/process`. The response's `borrower_message.attempts` shows which channel delivered.

Region availability differs per service; choose a region where all three are available to you.
