
import smtplib
import ssl
from email.message import EmailMessage

from flask import current_app


def send_email(to, subject, body):
    app = current_app
    cfg = app.config
    if cfg.get("TESTING"):
        app.extensions.setdefault("outbox", []).append({"to": to, "subject": subject, "body": body})
        return
    if not cfg.get("SMTP_HOST"):
        app.logger.warning("SMTP not configured; email to %s not sent.\n%s\n%s", to, subject, body)
        return
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = cfg["SMTP_FROM"], to, subject
    msg.set_content(body)
    ctx = ssl.create_default_context()
    if cfg["SMTP_SSL"]:
        server = smtplib.SMTP_SSL(cfg["SMTP_HOST"], cfg["SMTP_PORT"], context=ctx, timeout=15)
    else:
        server = smtplib.SMTP(cfg["SMTP_HOST"], cfg["SMTP_PORT"], timeout=15)
    with server:
        if not cfg["SMTP_SSL"]:
            server.starttls(context=ctx)
        if cfg["SMTP_USER"]:
            server.login(cfg["SMTP_USER"], cfg["SMTP_PASSWORD"])
        server.send_message(msg)


def send_signup_code(to, name, code, minutes):
    send_email(
        to, f"Your Gari Yangu verification code: {code}",
        f"Hi {name},\n\nYour Gari Yangu verification code is {code}.\n"
        f"It expires in {minutes} minutes. If you didn't try to sign up, you can ignore this email.\n",
    )


def send_reset_code(to, name, code, minutes):
    send_email(
        to, f"Your Gari Yangu password reset code: {code}",
        f"Hi {name},\n\nYour Gari Yangu password reset code is {code}.\n"
        f"It expires in {minutes} minutes. If you didn't ask to reset your password, ignore this email "
        f"and your password will stay the same.\n",
    )
