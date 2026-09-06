"""E-Mail-Versand der Bestandsliste per SMTP.

Der Anbieter wird aus der Absenderadresse abgeleitet, damit nur ein einziger
Satz Zugangsdaten hinterlegt werden muss.
"""

import os
import smtplib
import ssl
from email.message import EmailMessage

# Anbieter, deren SMTP-Zugang ueber ein App-Passwort laeuft.
SMTP_ANBIETER = {
    "gmail.com": ("smtp.gmail.com", 587),
    "googlemail.com": ("smtp.gmail.com", 587),
    "icloud.com": ("smtp.mail.me.com", 587),
    "me.com": ("smtp.mail.me.com", 587),
    "mac.com": ("smtp.mail.me.com", 587),
    "t-online.de": ("securesmtp.t-online.de", 587),
}

STANDARD_SMTP = ("smtp.gmail.com", 587)


def smtp_zugang(absender):
    """SMTP-Server zur Absenderadresse; ueberschreibbar per Umgebungsvariable."""
    host = os.environ.get("SMTP_HOST")
    if host:
        return host, int(os.environ.get("SMTP_PORT", "587"))
    domain = absender.split("@")[-1].lower()
    return SMTP_ANBIETER.get(domain, STANDARD_SMTP)


def zugangsdaten():
    """Absender und Passwort. MAIL_* hat Vorrang, ICLOUD_* bleibt gueltig."""
    absender = os.environ.get("MAIL_ABSENDER") or os.environ.get("ICLOUD_EMAIL", "")
    passwort = os.environ.get("MAIL_PASSWORT") or os.environ.get("ICLOUD_APP_PASSWORD", "")
    return absender.strip(), passwort.strip()


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
    absender, passwort = zugangsdaten()
    empfaenger = empfaenger or empfaenger_liste(lager)

    if not (absender and passwort):
        raise RuntimeError(
            "MAIL_ABSENDER und MAIL_PASSWORT muessen gesetzt sein. Bei Gmail ist "
            "das Passwort ein App-Passwort aus myaccount.google.com/apppasswords, "
            "nicht das normale Kontopasswort."
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

    host, port = smtp_zugang(absender)
    with smtplib.SMTP(host, port) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(absender, passwort)
        smtp.send_message(nachricht)

    return empfaenger
