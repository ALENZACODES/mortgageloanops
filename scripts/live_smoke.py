"""Send ONE real test message per AWS channel and print the AWS response IDs. Run once, then record it for the demo.
  MLO_LIVE=1 AWS_REGION=... MLO_SMS_ORIGINATION=... MLO_WHATSAPP_PHONE_NUMBER_ID=... MLO_EMAIL_FROM=... \
  python scripts/live_smoke.py +1YOURMOBILE you@example.com
Sandbox rules apply: the recipients must be verified in SES / End User Messaging SMS."""
import os, sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from mortgageloanops.messaging import Messenger

if os.environ.get("MLO_LIVE") != "1":
    sys.exit("Set MLO_LIVE=1 (and the MLO_* variables) to send real messages.")
phone, email = sys.argv[1], sys.argv[2]
m = Messenger(live=True)
for ch in ("rcs", "sms", "whatsapp", "email"):
    if ch == "rcs" and not m.config.get("rcs_agent_arn"):
        print("rcs SKIPPED (set MLO_RCS_AGENT_ARN)"); continue
    try:
        r = m._send(ch, {"phone": phone, "email": email}, "MortgageLoanOps test", "Test message from MortgageLoanOps. No action needed.")
        print(ch, "OK", r)
    except Exception as e:
        print(ch, "FAILED", type(e).__name__, e)
