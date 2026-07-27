#!/usr/bin/env python3
"""Sortiere Rechnungen aus dem Gmail-Posteingang und lege sie in iCloud ab.

Das Skript erledigt in einem Durchlauf:
  1. Gmail-Posteingang nach Rechnungen durchsuchen
  2. jede Rechnung in "privat" oder "geschäftlich" einordnen
  3. die Anhänge in den lokalen iCloud-Steuerordner ablegen
  4. die Mail in Gmail unter Rechnungen/Privat bzw. Rechnungen/Geschäftlich einsortieren
  5. einen Monatsentwurf an den Rechnungseingang im Entwürfe-Ordner erstellen

Muss lokal auf dem Mac laufen, auf dem iCloud Drive eingerichtet ist.
"""

import argparse
import email
import imaplib
import os
import re
import sys
import time
from datetime import datetime, timezone
from email.header import decode_header
from email.message import EmailMessage
from email.utils import parsedate_to_datetime
from pathlib import Path


IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993

# Zieladresse für den Monatsentwurf (DATEV-Upload).
RECHNUNGSEINGANG = "30b48da3-0fb7-42c5-acb2-c52ad2e28f42@uploadmail.datev.de"

LABEL_PRIVAT = "Rechnungen/Privat"
LABEL_GESCHAEFTLICH = "Rechnungen/Geschäftlich"

# Gmail nennt den Entwurfsordner je nach Spracheinstellung anders.
DRAFTS_CANDIDATES = ["[Gmail]/Entwürfe", "[Gmail]/Drafts", "[Google Mail]/Entwürfe"]

# Anhänge, die als Rechnungsbeleg in Frage kommen. XML deckt ZUGFeRD/XRechnung ab.
BELEG_SUFFIXE = {".pdf", ".xml", ".jpg", ".jpeg", ".png", ".heic"}

# Stichwörter, die eine Mail überhaupt erst zur Rechnung machen.
RECHNUNG_KEYWORDS = [
    "rechnung", "invoice", "beleg", "quittung", "zahlungsbestätigung",
    "rechnungsnummer", "faktura", "gutschrift", "kassenbon",
]

# Absender/Stichwörter, die eine Rechnung als geschäftlich kennzeichnen.
# Diese Liste ist der Stellhebel — hier trägst du deine Lieferanten ein.
GESCHAEFTLICH_MUSTER = [
    "datev", "telekom.de", "vodafone", "1und1", "ionos", "strato",
    "aws", "amazon web services", "google cloud", "microsoft", "adobe",
    "immoscout", "is24", "immowelt", "sprengnetter", "haufe",
    "steuerberater", "kanzlei", "notar", "ihk", "berufsgenossenschaft",
    "bürobedarf", "makler", "provend",
]

# Absender/Stichwörter, die eine Rechnung als privat kennzeichnen.
PRIVAT_MUSTER = [
    "netflix", "spotify", "disney", "zalando", "otto.de", "ikea",
    "lieferando", "rewe", "edeka", "dm-drogerie", "apotheke",
    "stadtwerke", "versicherung", "fitnessstudio", "easypark",
]


def decode_header_value(raw):
    """Dekodiere einen MIME-kodierten Header in lesbaren Text."""
    parts = decode_header(raw or "")
    result = []
    for part, charset in parts:
        if isinstance(part, bytes):
            result.append(part.decode(charset or "utf-8", errors="replace"))
        else:
            result.append(part)
    return "".join(result)


def get_body(msg):
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain" and not part.get("Content-Disposition"):
                payload = part.get_payload(decode=True)
                if payload:
                    return payload.decode(part.get_content_charset() or "utf-8", errors="replace")
    else:
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors="replace")
    return ""


def sanitize(value, max_length=60):
    """Mache aus beliebigem Text einen sicheren Dateinamen-Bestandteil."""
    cleaned = re.sub(r"[^\w\s.-]", "", value, flags=re.UNICODE)
    cleaned = re.sub(r"\s+", "_", cleaned).strip("._-")
    return cleaned[:max_length] or "ohne_Betreff"


def find_attachments(msg):
    """Sammle alle Anhänge, die als Beleg taugen."""
    attachments = []
    for part in msg.walk():
        if part.get_content_maintype() == "multipart":
            continue
        filename = decode_header_value(part.get_filename() or "")
        if not filename:
            continue
        if Path(filename).suffix.lower() not in BELEG_SUFFIXE:
            continue
        payload = part.get_payload(decode=True)
        if payload:
            attachments.append((filename, payload))
    return attachments


def is_rechnung(subject, sender, body, attachments):
    """Eine Mail gilt als Rechnung, wenn sie ein Stichwort UND einen Beleg trägt."""
    haystack = f"{subject} {sender} {body[:2000]}".lower()
    has_keyword = any(kw in haystack for kw in RECHNUNG_KEYWORDS)
    return has_keyword and bool(attachments)


def classify(subject, sender, body):
    """Ordne eine Rechnung privat/geschäftlich zu.

    Gibt "geschaeftlich", "privat" oder None zurück. None heißt: unklar,
    die Rechnung wandert zur manuellen Prüfung und wird nicht geraten —
    bei Steuerunterlagen ist eine falsche Zuordnung teurer als eine offene.
    """
    haystack = f"{subject} {sender} {body[:2000]}".lower()
    if any(m in haystack for m in GESCHAEFTLICH_MUSTER):
        return "geschaeftlich"
    if any(m in haystack for m in PRIVAT_MUSTER):
        return "privat"
    return None


def resolve_steuer_dir(override=None):
    """Finde den iCloud-Steuerordner auf diesem Mac."""
    if override:
        return Path(override).expanduser()

    env_dir = os.environ.get("ICLOUD_STEUER_DIR")
    if env_dir:
        return Path(env_dir).expanduser()

    icloud_root = Path.home() / "Library" / "Mobile Documents" / "com~apple~CloudDocs"
    if not icloud_root.exists():
        raise SystemExit(
            f"iCloud Drive nicht gefunden unter {icloud_root}\n"
            "Setze den Pfad explizit:  export ICLOUD_STEUER_DIR='/pfad/zum/Steuer'"
        )

    # Der Ordner heißt je nach Anlage "Steuer" oder "Steuern".
    for name in ("Steuer", "Steuern"):
        candidate = icloud_root / name
        if candidate.exists():
            return candidate
    return icloud_root / "Steuer"


def target_dir(steuer_dir, kategorie, jahr):
    unterordner = {
        "geschaeftlich": "Geschäftlich",
        "privat": "Privat",
    }.get(kategorie, "_Zu_pruefen")
    return steuer_dir / str(jahr) / unterordner


def save_attachment(directory, filename, payload, dry_run=False):
    """Schreibe einen Anhang, ohne eine bestehende Datei zu überschreiben."""
    target = directory / filename
    stem, suffix = target.stem, target.suffix
    counter = 2
    while target.exists():
        target = directory / f"{stem}_{counter}{suffix}"
        counter += 1

    if dry_run:
        return target

    directory.mkdir(parents=True, exist_ok=True)
    target.write_bytes(payload)
    return target


def ensure_label(imap, label):
    """Lege ein Gmail-Label an, falls es noch nicht existiert."""
    status, _ = imap.select(f'"{label}"', readonly=True)
    if status == "OK":
        return
    imap.create(f'"{label}"')
    imap.subscribe(f'"{label}"')


def find_drafts_folder(imap):
    status, folders = imap.list()
    if status != "OK":
        return DRAFTS_CANDIDATES[1]
    listing = b"\n".join(folders).decode("utf-8", errors="replace")
    # \Drafts ist das verlässliche Attribut, der Name ist sprachabhängig.
    for line in listing.splitlines():
        if "\\Drafts" in line:
            match = re.search(r'"([^"]+)"\s*$', line.strip())
            if match:
                return match.group(1)
    for candidate in DRAFTS_CANDIDATES:
        if candidate in listing:
            return candidate
    return DRAFTS_CANDIDATES[1]


def build_draft(rechnungen, jahr, monat, absender):
    """Baue die Monats-Übersichtsmail mit allen Belegen als Anhang."""
    monatsnamen = [
        "Januar", "Februar", "März", "April", "Mai", "Juni",
        "Juli", "August", "September", "Oktober", "November", "Dezember",
    ]
    monatsname = monatsnamen[monat - 1]

    msg = EmailMessage()
    msg["To"] = RECHNUNGSEINGANG
    msg["From"] = absender
    msg["Subject"] = f"Rechnungseingang {monatsname} {jahr}"
    msg["Date"] = email.utils.formatdate(localtime=True)

    geschaeftlich = [r for r in rechnungen if r["kategorie"] == "geschaeftlich"]
    privat = [r for r in rechnungen if r["kategorie"] == "privat"]
    offen = [r for r in rechnungen if r["kategorie"] is None]

    lines = [f"Rechnungen {monatsname} {jahr}", ""]

    def block(titel, eintraege):
        lines.append(f"{titel} ({len(eintraege)})")
        if not eintraege:
            lines.append("  – keine –")
        for r in eintraege:
            lines.append(f"  • {r['datum']:%d.%m.%Y}  {r['absender']}  –  {r['betreff']}")
            for name, _ in r["attachments"]:
                lines.append(f"      Anhang: {name}")
        lines.append("")

    block("GESCHÄFTLICH", geschaeftlich)
    block("PRIVAT", privat)
    if offen:
        block("NOCH ZU PRÜFEN", offen)

    lines.append(f"Gesamt: {len(rechnungen)} Rechnung(en)")
    msg.set_content("\n".join(lines))

    for r in rechnungen:
        for name, payload in r["attachments"]:
            suffix = Path(name).suffix.lower()
            maintype, subtype = {
                ".pdf": ("application", "pdf"),
                ".xml": ("application", "xml"),
                ".png": ("image", "png"),
                ".heic": ("image", "heic"),
            }.get(suffix, ("image", "jpeg"))
            msg.add_attachment(payload, maintype=maintype, subtype=subtype, filename=name)

    return msg


def collect_rechnungen(imap, jahr, monat):
    """Hole alle Rechnungen des angegebenen Monats aus dem Posteingang."""
    imap.select("INBOX")

    # IMAP SINCE/BEFORE arbeitet tagesgenau, daher Monatsgrenzen aufspannen.
    start = datetime(jahr, monat, 1)
    end = datetime(jahr + (monat == 12), (monat % 12) + 1, 1)
    criteria = f'(SINCE "{start:%d-%b-%Y}" BEFORE "{end:%d-%b-%Y}")'

    status, data = imap.search(None, criteria)
    if status != "OK" or not data[0]:
        return []

    rechnungen = []
    for uid in data[0].split():
        status, msg_data = imap.fetch(uid, "(RFC822)")
        if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            continue

        msg = email.message_from_bytes(msg_data[0][1])
        subject = decode_header_value(msg.get("Subject", ""))
        sender = decode_header_value(msg.get("From", ""))
        body = get_body(msg)
        attachments = find_attachments(msg)

        if not is_rechnung(subject, sender, body, attachments):
            continue

        try:
            datum = parsedate_to_datetime(msg.get("Date", ""))
        except (TypeError, ValueError):
            datum = datetime.now(timezone.utc)

        rechnungen.append({
            "uid": uid,
            "betreff": subject or "(ohne Betreff)",
            "absender": sender,
            "datum": datum,
            "kategorie": classify(subject, sender, body),
            "attachments": attachments,
        })

    return rechnungen


def run(username, password, jahr, monat, steuer_dir, dry_run, skip_draft):
    prefix = "[Testlauf] " if dry_run else ""
    print(f"{prefix}Verbinde mit {IMAP_HOST} als {username} …")

    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(username, password)
        print("Login erfolgreich.\n")

        if not dry_run:
            ensure_label(imap, LABEL_PRIVAT)
            ensure_label(imap, LABEL_GESCHAEFTLICH)

        rechnungen = collect_rechnungen(imap, jahr, monat)
        print(f"{len(rechnungen)} Rechnung(en) für {monat:02d}/{jahr} gefunden.\n")

        if not rechnungen:
            print("Nichts zu sortieren.")
            if not skip_draft:
                print("Erstelle trotzdem einen leeren Monatsentwurf.")
            else:
                return

        for r in rechnungen:
            kategorie = r["kategorie"]
            directory = target_dir(steuer_dir, kategorie, r["datum"].year)
            label = {
                "geschaeftlich": LABEL_GESCHAEFTLICH,
                "privat": LABEL_PRIVAT,
            }.get(kategorie)

            beschriftung = kategorie or "unklar → _Zu_pruefen"
            print(f"  {r['datum']:%d.%m.%Y}  {r['betreff'][:50]}")
            print(f"      Absender:  {r['absender'][:60]}")
            print(f"      Kategorie: {beschriftung}")

            for name, payload in r["attachments"]:
                dateiname = f"{r['datum']:%Y-%m-%d}_{sanitize(r['absender'], 30)}_{sanitize(Path(name).stem)}{Path(name).suffix}"
                pfad = save_attachment(directory, dateiname, payload, dry_run=dry_run)
                print(f"      Abgelegt:  {pfad}")

            if label:
                if not dry_run:
                    imap.copy(r["uid"], f'"{label}"')
                print(f"      Gmail:     {label}")
            else:
                print("      Gmail:     kein Label (Kategorie unklar)")
            print()

        if skip_draft:
            return

        draft = build_draft(rechnungen, jahr, monat, username)
        if dry_run:
            print(f"[Testlauf] Entwurf wäre erstellt: {draft['Subject']} → {RECHNUNGSEINGANG}")
            return

        drafts_folder = find_drafts_folder(imap)
        imap.append(
            f'"{drafts_folder}"',
            r"\Draft",
            imaplib.Time2Internaldate(time.time()),
            draft.as_bytes(),
        )
        print(f"Entwurf erstellt in '{drafts_folder}': {draft['Subject']}")
        print(f"Empfänger: {RECHNUNGSEINGANG}")


def main():
    heute = datetime.now()
    parser = argparse.ArgumentParser(
        description="Rechnungen aus Gmail sortieren und in iCloud ablegen.",
    )
    parser.add_argument("--jahr", type=int, default=heute.year, help="Jahr (Standard: aktuelles)")
    parser.add_argument("--monat", type=int, default=heute.month, help="Monat 1-12 (Standard: aktueller)")
    parser.add_argument("--steuer-dir", help="Pfad zum iCloud-Steuerordner")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts schreiben")
    parser.add_argument("--kein-entwurf", action="store_true", help="Monatsentwurf überspringen")
    args = parser.parse_args()

    if not 1 <= args.monat <= 12:
        parser.error("--monat muss zwischen 1 und 12 liegen")

    username = os.environ.get("GMAIL_EMAIL", "hegebehrens.rechnung@gmail.com")
    password = os.environ.get("GMAIL_APP_PASSWORD", "")

    if not password:
        print(
            "Fehler: GMAIL_APP_PASSWORD ist nicht gesetzt.\n"
            "\n"
            "Gmail braucht für IMAP ein App-Passwort:\n"
            "  1. https://myaccount.google.com/apppasswords öffnen\n"
            "  2. Mit hegebehrens.rechnung@gmail.com anmelden\n"
            "  3. App-Passwort erzeugen (16 Zeichen)\n"
            "  4. export GMAIL_APP_PASSWORD='xxxxxxxxxxxxxxxx'\n"
            "  5. Skript erneut starten.\n"
        )
        sys.exit(1)

    steuer_dir = resolve_steuer_dir(args.steuer_dir)
    print(f"Steuerordner: {steuer_dir}\n")

    run(
        username=username,
        password=password,
        jahr=args.jahr,
        monat=args.monat,
        steuer_dir=steuer_dir,
        dry_run=args.dry_run,
        skip_draft=args.kein_entwurf,
    )


if __name__ == "__main__":
    main()
