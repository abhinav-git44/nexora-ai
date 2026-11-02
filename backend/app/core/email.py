import logging
import smtplib
from email.message import EmailMessage
import httpx
from sqlalchemy.orm import Session
from app.core.config import get_settings
from app.models import EmailOutbox

log = logging.getLogger("nexora.email")


def send_email(db: Session, to: str, subject: str, body: str, kind: str = "generic"):
    """Records the email in the outbox and delivers it via the configured backend.
    'console' backend (default for dev) logs the message — links are visible in server logs and in the outbox table."""
    s = get_settings()
    row = EmailOutbox(to_email=to, subject=subject, body=body, kind=kind)
    db.add(row)
    try:
        if s.email_backend == "smtp" and s.smtp_host:
            msg = EmailMessage()
            msg["From"], msg["To"], msg["Subject"] = s.email_from, to, subject
            msg.set_content(body)
            with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
                smtp.starttls()
                if s.smtp_user:
                    smtp.login(s.smtp_user, s.smtp_password or "")
                smtp.send_message(msg)
            row.status = "sent"
        elif s.email_backend == "resend" and s.resend_api_key:
            r = httpx.post("https://api.resend.com/emails", timeout=10,
                           headers={"Authorization": f"Bearer {s.resend_api_key}"},
                           json={"from": s.email_from, "to": [to], "subject": subject, "text": body})
            r.raise_for_status()
            row.status = "sent"
        else:
            log.info("[email:console] to=%s subject=%s\n%s", to, subject, body)
            row.status = "logged"
    except Exception as e:
        row.status, row.error = "failed", str(e)[:500]
        log.exception("Email delivery failed")
    return row
