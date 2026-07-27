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

# ProVend läuft getrennt: eigener Ordner, nichts davon wird übermittelt.
LABEL_PROVEND = "ProVend Deutschland"
LABEL_PROVEND_RECHNUNGEN = "ProVend Deutschland/Rechnungen an ProVend"

# Gmail nennt den Entwurfsordner je nach Spracheinstellung anders.
DRAFTS_CANDIDATES = ["[Gmail]/Entwürfe", "[Gmail]/Drafts", "[Google Mail]/Entwürfe"]

# Durchsuchte Ordner. Das iCloud-Archiv ist ein Unterlabel von INBOX und wird
# von einer reinen INBOX-Suche nicht erfasst.
STANDARD_ORDNER = ["INBOX", "INBOX/Icloud Archiv"]

# Anhänge, die als Rechnungsbeleg in Frage kommen. XML deckt ZUGFeRD/XRechnung ab.
BELEG_SUFFIXE = {".pdf", ".xml", ".jpg", ".jpeg", ".png", ".heic"}

# Stichwörter, die eine Mail überhaupt erst zur Rechnung machen.
RECHNUNG_KEYWORDS = [
    "rechnung", "invoice", "beleg", "quittung", "zahlungsbestätigung",
    "rechnungsnummer", "faktura", "gutschrift", "kassenbon",
]

# Ladestrom fürs Auto zählt geschäftlich — Anbieter und Stichwörter.
LADESTROM_MUSTER = [
    "ladestrom", "ladevorgang", "ladekarte", "ladesäule", "wallbox",
    "charging", "charge point", "chargepoint", "supercharger",
    "enbw mobility", "ionity", "ewe go", "shell recharge", "aral pulse",
    "allego", "plugsurfing", "elli.eu", "we charge", "mer germany", "eon drive",
    "maingau", "lichtblick", "tesla", "qwello", "ladecloud", "ladenetz",
]

# Absender/Stichwörter, die eine Rechnung als geschäftlich kennzeichnen.
# Diese Liste ist der Stellhebel — hier trägst du deine Lieferanten ein.
GESCHAEFTLICH_MUSTER = [
    "datev", "telekom.de", "vodafone", "1und1", "ionos", "strato",
    "aws", "amazon web services", "google cloud", "microsoft", "adobe",
    "immoscout", "is24", "immobilienscout", "immowelt", "immowerbung",
    "sprengnetter", "haufe", "apcoa",
    "meike weitzel", "weitzel",
    "steuerberater", "kanzlei", "notar", "ihk", "berufsgenossenschaft",
    "bürobedarf", "makler",
    "deutsche post", "deutschepost",
] + LADESTROM_MUSTER

# ProVend-Post wird nur weggeräumt: kein Steuerordner, kein Entwurf, kein Versand.
# Wird gegen Absender UND Empfänger geprüft, damit auch Rechnungen erfasst
# werden, die an ProVend gehen statt von dort zu kommen.
PROVEND_MUSTER = [
    "provend",
    # Selgros-Einkäufe laufen über ProVend, egal ob sie weitergeleitet
    # wurden oder direkt kommen.
    "selgros",
]

# Absender/Stichwörter, die eine Rechnung als privat kennzeichnen.
PRIVAT_MUSTER = [
    "netflix", "spotify", "disney", "zalando", "otto.de", "ikea",
    "lieferando", "rewe", "edeka", "dm-drogerie", "apotheke",
    "stadtwerke", "versicherung", "fitnessstudio", "easypark",
    # Bewusst die Domain und nicht "christ": das Muster greift ab Wortanfang
    # und würde sonst auch in "Christian" oder "Christoph" anspringen.
    "christ.de",
    "condor",
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
    # Hier bewusst Substring statt Wortanfang: bei Komposita wie
    # "Honorarrechnung" oder "Schlussrechnung" steht das Stichwort hinten.
    haystack = f"{subject} {sender} {body[:2000]}".lower()
    has_keyword = any(kw in haystack for kw in RECHNUNG_KEYWORDS)
    return has_keyword and bool(attachments)


def matcht(haystack, muster):
    """Suche ein Muster ab Wortanfang.

    Ein reiner Substring-Vergleich wäre zu grob: "elli" steckt sonst in
    "voellig", "mer" in "kommerziell". Bei Steuerunterlagen ist eine falsche
    Zuordnung teurer als eine, die durchrutscht und geprüft werden muss.

    Das Wortende bleibt bewusst offen, sonst fielen deutsche Komposita
    heraus: "Ladestromabrechnung" soll auf "ladestrom" anspringen.

    Leerzeichen im Muster matchen jedes übliche Trennzeichen, denn Firmen
    schreiben sich mal "ewe go", mal "ewe-go.de", mal "ewego".
    """
    teile = [re.escape(t) for t in muster.split()]
    pattern = r"(?<!\w)" + r"[\s._-]*".join(teile)
    return re.search(pattern, haystack) is not None


def matcht_eines(haystack, muster_liste):
    return any(matcht(haystack, m) for m in muster_liste)


def ist_provend(subject, sender, body, empfaenger=""):
    """Prüfe, ob die Mail zu ProVend gehört.

    Der Empfänger zählt mit: eine Rechnung, die an ProVend geht, trägt die
    Adresse im To/Cc, nicht im Absender.
    """
    haystack = f"{subject} {sender} {empfaenger} {body[:2000]}".lower()
    return matcht_eines(haystack, PROVEND_MUSTER)


def classify(subject, sender, body):
    """Ordne eine Rechnung privat/geschäftlich zu.

    Gibt "geschaeftlich", "privat" oder None zurück. None heißt: unklar,
    die Rechnung wandert zur manuellen Prüfung und wird nicht geraten —
    bei Steuerunterlagen ist eine falsche Zuordnung teurer als eine offene.
    """
    haystack = f"{subject} {sender} {body[:2000]}".lower()
    if matcht_eines(haystack, GESCHAEFTLICH_MUSTER):
        return "geschaeftlich"
    if matcht_eines(haystack, PRIVAT_MUSTER):
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


MONATSNAMEN = [
    "Januar", "Februar", "März", "April", "Mai", "Juni",
    "Juli", "August", "September", "Oktober", "November", "Dezember",
]

# Eingangsrechnungen = alles, was an mich geht. Ausgangsrechnungen an ProVend
# werden hier bewusst nicht abgelegt.
EINGANG_ORDNER = "Eingangsrechnungen"

# Ab diesem Jahr wird die Ablage geführt.
STARTJAHR = 2025

# Ältere Rechnungen werden abgelegt und einsortiert, kommen aber nicht mehr in
# den Entwurf an DATEV — die sind dort bereits eingereicht.
STICHTAG = datetime(2026, 6, 1, tzinfo=timezone.utc)

# Übersteigen die Anhänge diese Grenze, wird eine weitere Mail angelegt.
#
# Achtung: Das ist die Rohgröße der Dateien, so wie der Finder sie anzeigt.
# In der Mail werden Anhänge Base64-kodiert und dabei rund ein Drittel größer.
# 19,9 MB Rohdaten ergeben also ca. 26,5 MB Mailgröße — und Gmail nimmt nur
# 25 MB an. MAX_MAIL_BYTES fängt das ab: greift die harte Grenze zuerst, wird
# entsprechend früher geteilt.
MAX_ANHANG_BYTES = int(19.9 * 1024 * 1024)

# Harte Obergrenze für die fertige Mail inklusive Base64-Aufschlag (Gmail: 25 MB).
MAX_MAIL_BYTES = 24 * 1024 * 1024

# Base64 macht aus 3 Byte 4 Zeichen (Faktor 1,333) und bricht zusätzlich alle
# 76 Zeichen um. Gemessen liegt der reale Aufschlag bei rund 1,35; mit 1,37
# bleibt die Schätzung auf der sicheren Seite.
BASE64_FAKTOR = 1.37

KATEGORIE_ORDNER = {
    "geschaeftlich": "Geschäftlich",
    "privat": "Privat",
}
UNKLAR_ORDNER = "_Zu_pruefen"


def monatsordner(monat):
    """"03_März" — die Nummer vorn hält die Ordner chronologisch sortiert."""
    return f"{monat:02d}_{MONATSNAMEN[monat - 1]}"


def target_dir(steuer_dir, kategorie, jahr, monat):
    """Zielordner nach Jahr, Monat und Kategorie."""
    unterordner = KATEGORIE_ORDNER.get(kategorie, UNKLAR_ORDNER)
    return steuer_dir / EINGANG_ORDNER / str(jahr) / monatsordner(monat) / unterordner


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


def anhang_groesse(rechnung):
    return sum(len(payload) for _, payload in rechnung["attachments"])


def teile_nach_groesse(rechnungen):
    """Verteile Rechnungen auf Pakete, die je unter beiden Grenzen bleiben.

    Eine Rechnung wird nie auseinandergerissen — ihre Belege bleiben zusammen
    in einer Mail. Passt eine einzelne Rechnung in kein Paket, bekommt sie
    ihre eigene Mail; das meldet der Aufrufer dann als Warnung.
    """
    pakete = []
    aktuell = []
    roh = 0

    for r in sorted(rechnungen, key=lambda x: x["datum"]):
        groesse = anhang_groesse(r)
        passt_roh = roh + groesse <= MAX_ANHANG_BYTES
        passt_mail = (roh + groesse) * BASE64_FAKTOR <= MAX_MAIL_BYTES

        if aktuell and not (passt_roh and passt_mail):
            pakete.append(aktuell)
            aktuell, roh = [], 0

        aktuell.append(r)
        roh += groesse

    if aktuell:
        pakete.append(aktuell)
    return pakete


def build_draft(rechnungen, absender, titel, teil=1, gesamt=1):
    """Baue eine Übermittlungsmail mit den Belegen dieses Pakets im Anhang.

    ProVend wird hier noch einmal herausgefiltert, obwohl der Aufrufer das
    bereits tut: die Regel "geht nie an DATEV" soll nicht an einer einzigen
    Stelle hängen.
    """
    zu_uebermitteln = [r for r in rechnungen if not r["provend"]]

    msg = EmailMessage()
    msg["To"] = RECHNUNGSEINGANG
    msg["From"] = absender
    betreff = f"Rechnungseingang {titel}"
    if gesamt > 1:
        betreff += f" (Teil {teil} von {gesamt})"
    msg["Subject"] = betreff
    msg["Date"] = email.utils.formatdate(localtime=True)

    geschaeftlich = [r for r in zu_uebermitteln if r["kategorie"] == "geschaeftlich"]
    privat = [r for r in zu_uebermitteln if r["kategorie"] == "privat"]
    offen = [r for r in zu_uebermitteln if r["kategorie"] is None]

    kopf = f"Rechnungen {titel}"
    if gesamt > 1:
        kopf += f" – Teil {teil} von {gesamt}"
    lines = [kopf, ""]

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

    lines.append(f"Gesamt: {len(zu_uebermitteln)} Rechnung(en)")
    msg.set_content("\n".join(lines))

    for r in zu_uebermitteln:
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


def collect_rechnungen(imap, ordner, seit=None, bis=None):
    """Hole alle Rechnungen eines Ordners, optional auf einen Zeitraum begrenzt."""
    status, _ = imap.select(f'"{ordner}"', readonly=True)
    if status != "OK":
        print(f"  Ordner '{ordner}' nicht gefunden – übersprungen.")
        return []

    teile = []
    if seit:
        teile.append(f'SINCE "{seit:%d-%b-%Y}"')
    if bis:
        teile.append(f'BEFORE "{bis:%d-%b-%Y}"')
    criteria = f"({' '.join(teile)})" if teile else "ALL"

    # UID statt Sequenznummer: die bleibt gültig, wenn zwischendurch ein
    # anderer Ordner selektiert wird.
    status, data = imap.uid("SEARCH", None, criteria)
    if status != "OK" or not data[0]:
        return []

    rechnungen = []
    for uid in data[0].split():
        status, msg_data = imap.uid("FETCH", uid, "(RFC822)")
        if status != "OK" or not msg_data or not isinstance(msg_data[0], tuple):
            continue

        msg = email.message_from_bytes(msg_data[0][1])
        subject = decode_header_value(msg.get("Subject", ""))
        sender = decode_header_value(msg.get("From", ""))
        empfaenger = " ".join(
            decode_header_value(msg.get(feld, "")) for feld in ("To", "Cc")
        )
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
            "ordner": ordner,
            "betreff": subject or "(ohne Betreff)",
            "absender": sender,
            "datum": datum,
            "kategorie": classify(subject, sender, body),
            "provend": ist_provend(subject, sender, body, empfaenger),
            "attachments": attachments,
        })

    return rechnungen


def mb(anzahl_bytes):
    return f"{anzahl_bytes / 1024 / 1024:.1f} MB"


def run(username, password, ordner_liste, seit, bis, stichtag,
        steuer_dir, dry_run, skip_draft, titel):
    prefix = "[Testlauf] " if dry_run else ""
    print(f"{prefix}Verbinde mit {IMAP_HOST} als {username} …")

    with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
        imap.login(username, password)
        print("Login erfolgreich.\n")

        if not dry_run:
            ensure_label(imap, LABEL_PRIVAT)
            ensure_label(imap, LABEL_GESCHAEFTLICH)
            ensure_label(imap, LABEL_PROVEND)
            ensure_label(imap, LABEL_PROVEND_RECHNUNGEN)

        rechnungen = []
        for ordner in ordner_liste:
            gefunden = collect_rechnungen(imap, ordner, seit, bis)
            print(f"  {ordner}: {len(gefunden)} Rechnung(en)")
            rechnungen.extend(gefunden)

        rechnungen.sort(key=lambda r: r["datum"])
        print(f"\n{len(rechnungen)} Rechnung(en) insgesamt.\n")

        if not rechnungen:
            print("Nichts zu sortieren.")
            return

        for r in rechnungen:
            kategorie = r["kategorie"]
            directory = target_dir(
                steuer_dir, kategorie, r["datum"].year, r["datum"].month
            )

            if r["provend"]:
                label = LABEL_PROVEND_RECHNUNGEN
                beschriftung = "ProVend – nur wegsortieren"
            else:
                label = {
                    "geschaeftlich": LABEL_GESCHAEFTLICH,
                    "privat": LABEL_PRIVAT,
                }.get(kategorie)
                beschriftung = kategorie or "unklar → _Zu_pruefen"

            print(f"  {r['datum']:%d.%m.%Y}  {r['betreff'][:50]}")
            print(f"      Absender:  {r['absender'][:60]}")
            print(f"      Kategorie: {beschriftung}")

            if r["provend"]:
                print("      Ablage:    keine (nicht in den Steuerordner)")
            else:
                for name, payload in r["attachments"]:
                    dateiname = f"{r['datum']:%Y-%m-%d}_{sanitize(r['absender'], 30)}_{sanitize(Path(name).stem)}{Path(name).suffix}"
                    pfad = save_attachment(directory, dateiname, payload, dry_run=dry_run)
                    print(f"      Abgelegt:  {pfad}")

            if label:
                if not dry_run:
                    # Kopieren geht nur aus dem Ordner, in dem die Mail liegt.
                    imap.select(f'"{r["ordner"]}"')
                    imap.uid("COPY", r["uid"], f'"{label}"')
                print(f"      Gmail:     {label}")
            else:
                print("      Gmail:     kein Label (Kategorie unklar)")
            print()

        provend = [r for r in rechnungen if r["provend"]]
        if provend:
            print(
                f"{len(provend)} ProVend-Rechnung(en) nur einsortiert "
                f"unter '{LABEL_PROVEND_RECHNUNGEN}' – nicht im Entwurf."
            )

        if skip_draft:
            return

        # ProVend geht nie raus, und alles vor dem Stichtag ist bereits
        # eingereicht – beides wird abgelegt, aber nicht übermittelt.
        uebermitteln = [
            r for r in rechnungen
            if not r["provend"] and r["datum"] >= stichtag
        ]
        alt = [
            r for r in rechnungen
            if not r["provend"] and r["datum"] < stichtag
        ]
        if alt:
            print(
                f"{len(alt)} Rechnung(en) vor {stichtag:%d.%m.%Y} nur abgelegt "
                f"und einsortiert – nicht im Entwurf."
            )
        print()

        if not uebermitteln:
            print(f"Keine Rechnungen ab {stichtag:%d.%m.%Y} – kein Entwurf nötig.")
            return

        pakete = teile_nach_groesse(uebermitteln)
        gesamt_bytes = sum(anhang_groesse(r) for r in uebermitteln)
        print(
            f"{len(uebermitteln)} Rechnung(en) ab {stichtag:%d.%m.%Y}, "
            f"{mb(gesamt_bytes)} Anhänge → {len(pakete)} Mail(s)."
        )

        drafts_folder = None if dry_run else find_drafts_folder(imap)

        for nummer, paket in enumerate(pakete, 1):
            draft = build_draft(paket, username, titel, nummer, len(pakete))
            roh = sum(anhang_groesse(r) for r in paket)
            fertig = len(draft.as_bytes())

            print(f"\n  Teil {nummer}/{len(pakete)}: {len(paket)} Rechnung(en), "
                  f"{mb(roh)} Anhänge, {mb(fertig)} Mailgröße")

            if fertig > MAX_MAIL_BYTES:
                print(f"  WARNUNG: überschreitet {mb(MAX_MAIL_BYTES)} – "
                      f"Gmail lehnt den Versand womöglich ab.")

            if dry_run:
                print(f"  [Testlauf] Entwurf wäre: {draft['Subject']}")
                continue

            imap.append(
                f'"{drafts_folder}"',
                r"\Draft",
                imaplib.Time2Internaldate(time.time()),
                draft.as_bytes(),
            )
            print(f"  Entwurf erstellt: {draft['Subject']}")

        if not dry_run:
            print(f"\n{len(pakete)} Entwurf/Entwürfe in '{drafts_folder}' "
                  f"an {RECHNUNGSEINGANG}")


def main():
    heute = datetime.now()
    parser = argparse.ArgumentParser(
        description="Rechnungen aus Gmail sortieren und in iCloud ablegen.",
    )
    parser.add_argument("--jahr", type=int, help="Nur diesen Monat verarbeiten (mit --monat)")
    parser.add_argument("--monat", type=int, help="Monat 1-12, zusammen mit --jahr")
    parser.add_argument("--ordner", action="append", help="Zu durchsuchender Ordner (mehrfach möglich)")
    parser.add_argument("--stichtag", help="Ab diesem Datum wird übermittelt, Format TT.MM.JJJJ")
    parser.add_argument("--steuer-dir", help="Pfad zum iCloud-Steuerordner")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts schreiben")
    parser.add_argument("--kein-entwurf", action="store_true", help="Entwürfe überspringen")
    args = parser.parse_args()

    if (args.monat is None) != (args.jahr is None):
        parser.error("--monat und --jahr nur gemeinsam verwenden")
    if args.monat is not None and not 1 <= args.monat <= 12:
        parser.error("--monat muss zwischen 1 und 12 liegen")

    stichtag = STICHTAG
    if args.stichtag:
        try:
            stichtag = datetime.strptime(args.stichtag, "%d.%m.%Y").replace(tzinfo=timezone.utc)
        except ValueError:
            parser.error("--stichtag im Format TT.MM.JJJJ angeben, z. B. 01.06.2026")

    # Ohne --monat läuft das Skript über den gesamten Bestand: alles wird
    # abgelegt und einsortiert, übermittelt wird nur ab Stichtag.
    if args.monat is None:
        seit = bis = None
        titel = f"ab {stichtag:%B %Y}"
    else:
        seit = datetime(args.jahr, args.monat, 1)
        bis = datetime(args.jahr + (args.monat == 12), (args.monat % 12) + 1, 1)
        titel = f"{MONATSNAMEN[args.monat - 1]} {args.jahr}"

    ordner_liste = args.ordner or STANDARD_ORDNER

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
        ordner_liste=ordner_liste,
        seit=seit,
        bis=bis,
        stichtag=stichtag,
        steuer_dir=steuer_dir,
        dry_run=args.dry_run,
        skip_draft=args.kein_entwurf,
        titel=titel,
    )


if __name__ == "__main__":
    main()
