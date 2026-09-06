"""E-Mail-Versand der Bestandsliste ueber iCloud SMTP."""

import os
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = "smtp.mail.me.com"
SMTP_PORT = 587


def empfaenger_liste():
    """Empfaenger aus der Umgebungsvariable BESTANDSLISTE_EMPFAENGER (kommagetrennt)."""
    roh = os.environ.get("BESTANDSLISTE_EMPFAENGER", "")
    return [e.strip() for e in roh.replace(";", ",").split(",") if e.strip()]


def senden(betreff, text, anhang_pfad=None, empfaenger=None):
    absender = os.environ.get("ICLOUD_EMAIL", "")
    passwort = os.environ.get("ICLOUD_APP_PASSWORD", "")
    empfaenger = empfaenger or empfaenger_liste()

    if not (absender and passwort):
        raise RuntimeError("ICLOUD_EMAIL und ICLOUD_APP_PASSWORD muessen gesetzt sein.")
    if not empfaenger:
        raise RuntimeError("Keine Empfaenger gesetzt (BESTANDSLISTE_EMPFAENGER).")

    nachricht = EmailMessage()
    nachricht["From"] = absender
    nachricht["To"] = ", ".join(empfaenger)
    nachricht["Subject"] = betreff
    nachricht.set_content(text)

    if anhang_pfad and os.path.exists(anhang_pfad):
        with open(anhang_pfad, "rb") as f:
            nachricht.add_attachment(
                f.read(),
                maintype="application",
                subtype="vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename=os.path.basename(anhang_pfad),
            )

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(absender, passwort)
        smtp.send_message(nachricht)

    return empfaenger
