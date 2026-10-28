"""Send-time policy checks applied before any channel is tried.

* suppression list (people who replied STOP are never contacted again on phone channels or email)
* optional per-channel express-consent requirement
* optional quiet hours for phone channels (SMS / RCS / WhatsApp); email is exempt

Quiet hours and consent requirements are configurable policy defaults, not a statement of what any law
requires; confirm the rules that apply to your business with counsel.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

PHONE_CHANNELS = ("rcs", "sms", "whatsapp")


def _norm(addr: str) -> str:
    return "".join(ch for ch in (addr or "").lower() if ch.isalnum() or ch in "@.+")


class Policy:
    def __init__(self, require_consent: bool = False, quiet_hours: tuple | None = None,
                 default_utc_offset_hours: float = -5.0):
        self.require_consent = require_consent
        self.quiet_hours = quiet_hours          # (first_allowed_hour, first_blocked_hour), e.g. (8, 21)
        self.default_offset = default_utc_offset_hours
        self.suppressed: set[str] = set()

    def suppress(self, address: str) -> None:
        self.suppressed.add(_norm(address))

    def unsuppress(self, address: str) -> None:
        self.suppressed.discard(_norm(address))

    def is_suppressed(self, contact: dict) -> bool:
        return any(_norm(contact.get(k, "")) in self.suppressed for k in ("phone", "email") if contact.get(k))

    def in_quiet_hours(self, contact: dict, now_utc: datetime | None = None) -> bool:
        if not self.quiet_hours:
            return False
        now_utc = now_utc or datetime.now(timezone.utc)
        off = contact.get("utc_offset_hours", self.default_offset)
        local = now_utc + timedelta(hours=off)
        start, end = self.quiet_hours
        return not (start <= local.hour < end)

    def channel_allowed(self, channel: str, contact: dict, now_utc: datetime | None = None) -> tuple[bool, str]:
        if self.require_consent and not (contact.get("consent") or {}).get(channel):
            return False, "NO_EXPRESS_CONSENT"
        if channel in PHONE_CHANNELS and self.in_quiet_hours(contact, now_utc):
            return False, "QUIET_HOURS"
        return True, ""
