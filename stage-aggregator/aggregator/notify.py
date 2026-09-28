import os
import smtplib
import ssl
from email.message import EmailMessage
from datetime import datetime, timezone, timedelta

from .models import Offer, Evaluation


def build_digest(rows):
    ranked = sorted(rows, key=lambda row: Evaluation.model_validate_json(row["evaluation"]).score, reverse=True)
    lines = [f"{len(ranked)} nouvelle(s) offre(s) ajoutée(s) à stage-tracker :", ""]
    for row in ranked:
        offer = Offer.model_validate_json(row["offer"])
        evaluation = Evaluation.model_validate_json(row["evaluation"])
        lines.extend([f"{evaluation.score}/100 ({row['evaluator']}) — {offer.title} — {offer.company}",
                      f"Lieu : {offer.location}", evaluation.reason, f"Source : {offer.source} — {offer.url}", ""])
    return "\n".join(lines)


def send_smtp(body):
    required = ("SMTP_HOST", "MAIL_FROM", "MAIL_TO")
    if any(not os.getenv(name) for name in required):
        raise ValueError("SMTP_HOST, MAIL_FROM et MAIL_TO requis")
    message = EmailMessage()
    message["From"] = os.environ["MAIL_FROM"]
    message["To"] = os.environ["MAIL_TO"]
    message["Subject"] = "Nouvelles offres de stage pertinentes"
    message.set_content(body)
    tls = os.getenv("SMTP_TLS", "ssl")
    if tls not in ("ssl", "starttls"):
        raise ValueError("SMTP_TLS doit être ssl ou starttls")
    port = int(os.getenv("SMTP_PORT", "465" if tls == "ssl" else "587"))
    context = ssl.create_default_context()
    factory = smtplib.SMTP_SSL if tls == "ssl" else smtplib.SMTP
    kwargs = {"context": context} if tls == "ssl" else {}
    with factory(os.environ["SMTP_HOST"], port, timeout=30, **kwargs) as smtp:
        if tls == "starttls":
            smtp.starttls(context=context)
        if os.getenv("SMTP_USERNAME"):
            smtp.login(os.environ["SMTP_USERNAME"], os.environ.get("SMTP_PASSWORD", ""))
        refused = smtp.send_message(message)
        if refused:
            raise RuntimeError("Au moins un destinataire a été refusé")


def notify_pending(state, interval_days, sender=send_smtp):
    rows = state.notifications()
    if not rows:
        return 0
    last = state.metadata("last_digest")
    if last and datetime.now(timezone.utc) - datetime.fromisoformat(last) < timedelta(days=interval_days):
        return 0
    sender(build_digest(rows))
    # Marquer uniquement après l'acceptation SMTP. Un crash entre les deux peut redoubler le résumé.
    state.mark_notified(rows)
    return len(rows)
