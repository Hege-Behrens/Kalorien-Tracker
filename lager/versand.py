"""E-Mail-Versand der Bestandsliste ueber iCloud SMTP."""

import os
import smtplib
import ssl
from email.message import EmailMessage

SMTP_HOST = "smtp.mail.me.com"
SMTP_PORT = 587


def zerlegen(roh):
    return [e.strip() for e in (roh or "").replace(";", ",").split(",") if e.strip()]


def empfaenger_liste(lager=None):
    """Empfaenger der Bestandsliste.

    Vorrang hat die Einstellung im Projekt, damit die Liste versioniert und
    ohne Zugriff auf die Serverkonfiguration aenderbar ist. Die
    Umgebungsvariable bleibt als Ausweichweg bestehen.
    """
    if lager is not None:
        aus_einstellungen = zerlegen(lager.einstellungen.get("empfaenger", ""))
        if aus_einstellungen:
            return aus_einstellungen
    return zerlegen(os.environ.get("BESTANDSLISTE_EMPFAENGER", ""))


def senden(betreff, text, anhang_pfad=None, empfaenger=None, lager=None):
    absender = os.environ.get("ICLOUD_EMAIL", "")
    passwort = os.environ.get("ICLOUD_APP_PASSWORD", "")
    empfaenger = empfaenger or empfaenger_liste(lager)

    if not (absender and passwort):
        raise RuntimeError(
            "ICLOUD_EMAIL und ICLOUD_APP_PASSWORD muessen gesetzt sein. "
            "Das App-Passwort wird auf appleid.apple.com erzeugt."
        )
    if not empfaenger:
        raise RuntimeError(
            "Keine Empfaenger gesetzt. Setzen mit:  ./inventur.py empfaenger a@b.de c@d.de"
        )

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
