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


def anmeldung_pruefen():
    """Meldet sich beim SMTP-Server an und trennt sofort wieder.

    Ohne diese Probe faellt ein falsches App-Passwort erst beim naechsten
    geplanten Versand auf - also womoeglich erst Tage spaeter, wenn niemand
    hinschaut. Es wird keine Mail verschickt.
    """
    absender, passwort = zugangsdaten()
    if not (absender and passwort):
        raise RuntimeError(
            "MAIL_ABSENDER und MAIL_PASSWORT muessen gesetzt sein. Bei Gmail ist "
            "das Passwort ein App-Passwort aus myaccount.google.com/apppasswords, "
            "nicht das normale Kontopasswort."
        )
    host, port = smtp_zugang(absender)
    with smtplib.SMTP(host, port, timeout=30) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        smtp.login(absender, passwort)
    return absender, host


def senden(betreff, text, anhang_pfad=None, empfaenger=None, lager=None,
           html=None, logo_pfad=None, logo_cid="logo"):
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

    # Die HTML-Fassung als Alternative; der Textteil bleibt als Rueckfallebene
    # fuer Programme, die kein HTML anzeigen.
    if html:
        nachricht.add_alternative(html, subtype="html")
        if logo_pfad and os.path.exists(logo_pfad):
            html_teil = nachricht.get_payload()[-1]
            with open(logo_pfad, "rb") as f:
                html_teil.add_related(
                    f.read(), maintype="image", subtype="png", cid=f"<{logo_cid}>"
                )

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
