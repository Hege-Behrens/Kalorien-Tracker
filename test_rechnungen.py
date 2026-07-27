#!/usr/bin/env python3
"""Tests für die Erkennungs- und Zuordnungsregeln.

Aufruf:  python3 test_rechnungen.py
"""

import sys
from datetime import datetime

from pathlib import Path

from rechnungen_sortieren import (
    MAX_ANHANG_BYTES,
    MAX_MAIL_BYTES,
    anhang_groesse,
    build_draft,
    classify,
    is_rechnung,
    ist_provend,
    target_dir,
    teile_nach_groesse,
)


ANHANG = [("beleg.pdf", b"%PDF-1.4")]

# (Betreff, Absender, Body, erwartete Kategorie)
KLASSIFIZIERUNG = [
    ("Rechnung", "no-reply@immobilienscout24.de", "", "geschaeftlich"),
    ("Rechnung", "kundenservice@is24.de", "", "geschaeftlich"),
    ("Honorarrechnung", "m.weitzel@kanzlei.de", "Meike Weitzel", "geschaeftlich"),
    ("Rechnung", "meike.weitzel@buero.de", "", "geschaeftlich"),
    ("Ladestromabrechnung Juli", "service@enbw-mobility.de", "", "geschaeftlich"),
    ("Rechnung", "billing@ionity.eu", "", "geschaeftlich"),
    ("Rechnung Ladevorgang", "abrechnung@ewe-go.de", "", "geschaeftlich"),
    ("Rechnung", "info@shell-recharge.com", "", "geschaeftlich"),
    # Ladesäulenbetreiber ohne Ladestrom-Stichwort im Text
    ("Qwello Invoice", "support@qwello.de", "Quittung", "geschaeftlich"),
    ("Ihre Rechnung", "noreply-sw-suedholstein@ladecloud.de", "", "geschaeftlich"),
    ("Rechnung Wallbox", "a@b.de", "", "geschaeftlich"),
    ("Rechnung", "no-reply@netflix.com", "", "privat"),
    ("Rechnung und Versand zu deiner Bestellung", "bestellung@christ.de", "", "privat"),
    ("Condor Reisebestätigung", "no-answer@condor.com", "Rechnung", "privat"),
    ("Rechnung zu Ihrer Bestellung", "service-shop@deutschepost.de", "", "geschaeftlich"),
    ("Rechnung", "info@deutsche-post.de", "", "geschaeftlich"),
    # "christ" darf nicht in Vornamen anspringen.
    ("Rechnung", "christian.mueller@unbekannt.de", "", None),
    ("Rechnung", "christoph@fremdfirma.de", "", None),
    # Darf nicht auf "elli" in "voellig" bzw. "mer" in "kommerziell" anspringen.
    ("Rechnung", "info@voellig-unbekannt.de", "", None),
    ("Rechnung", "kontakt@kommerziell-gmbh.de", "", None),
]

# (Betreff, ob Anhang vorhanden, erwartetes Ergebnis)
ERKENNUNG = [
    ("Honorarrechnung", True, True),
    ("Schlussrechnung Nr. 5", True, True),
    ("Ihre Rechnungen", True, True),
    ("Rechnung", False, False),      # Stichwort ohne Beleg zählt nicht
    ("Newsletter August", True, False),
]

# (Absender, Empfänger, ob es ProVend-Post ist)
PROVEND = [
    # von ProVend
    ("info@provenddeutschland.de", "", True),
    # an ProVend – hier steht die Adresse im Empfängerfeld
    ("hegebehrens.rechnung@gmail.com", "buchhaltung@provenddeutschland.de", True),
    ("billing@ionity.eu", "", False),
    ("no-reply@immobilienscout24.de", "", False),
]


def rechnung(tag, mb_groesse, provend=False, kategorie="geschaeftlich"):
    """Testrechnung mit einem Anhang der gewünschten Größe."""
    return {
        "kategorie": kategorie, "provend": provend,
        "datum": datetime(2026, 6, tag), "absender": f"a{tag}@b.de",
        "betreff": f"Rechnung {tag}",
        "attachments": [(f"beleg{tag}.pdf", b"x" * int(mb_groesse * 1024 * 1024))],
    }


def pruefe_aufteilung():
    """Anhänge über der Grenze müssen auf mehrere Mails verteilt werden."""
    fehler = 0

    # Drei Rechnungen à 8 MB = 24 MB Rohdaten. Über der 19,9-MB-Grenze,
    # muss also geteilt werden.
    pakete = teile_nach_groesse([rechnung(1, 8), rechnung(2, 8), rechnung(3, 8)])
    if len(pakete) < 2:
        print(f"FEHL  24 MB ergaben {len(pakete)} Paket(e), erwartet mindestens 2")
        fehler += 1

    # Kein Paket darf eine der beiden Grenzen reißen.
    for i, paket in enumerate(pakete, 1):
        roh = sum(anhang_groesse(r) for r in paket)
        if roh > MAX_ANHANG_BYTES and len(paket) > 1:
            print(f"FEHL  Paket {i}: {roh} Byte über der Rohgrenze {MAX_ANHANG_BYTES}")
            fehler += 1
        fertig = len(build_draft(paket, "a@b.de", "Test", i, len(pakete)).as_bytes())
        if fertig > MAX_MAIL_BYTES and len(paket) > 1:
            print(f"FEHL  Paket {i}: Mail {fertig} Byte über {MAX_MAIL_BYTES}")
            fehler += 1

    # Der eigentliche Zweck: keine versandfertige Mail über Gmails 25-MB-Limit.
    GMAIL_LIMIT = 25 * 1024 * 1024
    viele = [rechnung(tag, 7) for tag in range(1, 8)]   # 49 MB Rohdaten
    for i, paket in enumerate(teile_nach_groesse(viele), 1):
        fertig = len(build_draft(paket, "a@b.de", "Test", i, 9).as_bytes())
        if fertig > GMAIL_LIMIT and len(paket) > 1:
            print(f"FEHL  Paket {i} versandfertig {fertig} Byte über Gmail-Limit")
            fehler += 1

    # Keine Rechnung darf verloren gehen oder doppelt auftauchen.
    verteilt = [r["betreff"] for paket in pakete for r in paket]
    if sorted(verteilt) != ["Rechnung 1", "Rechnung 2", "Rechnung 3"]:
        print(f"FEHL  Rechnungen nach Aufteilung: {sorted(verteilt)}")
        fehler += 1

    # Was zusammen unter der Grenze bleibt, gehört in eine einzige Mail.
    klein = teile_nach_groesse([rechnung(4, 0.5), rechnung(5, 0.5)])
    if len(klein) != 1:
        print(f"FEHL  1 MB ergab {len(klein)} Pakete, erwartet 1")
        fehler += 1

    # Teil-Nummerierung im Betreff
    mehrteilig = build_draft([rechnung(6, 0.1)], "a@b.de", "Juni 2026", 2, 3)
    if "Teil 2 von 3" not in mehrteilig["Subject"]:
        print(f"FEHL  Betreff ohne Teilangabe: {mehrteilig['Subject']}")
        fehler += 1
    einteilig = build_draft([rechnung(7, 0.1)], "a@b.de", "Juni 2026", 1, 1)
    if "Teil" in einteilig["Subject"]:
        print(f"FEHL  Einzelmail trägt Teilangabe: {einteilig['Subject']}")
        fehler += 1

    return fehler


def pruefe_ablagepfad():
    """Eingangsrechnungen liegen nach Jahr, Monat und Kategorie."""
    basis = Path("/Steuer")
    faelle = [
        ("geschaeftlich", 2025, 3,
         "/Steuer/Eingangsrechnungen/2025/03_März/Geschäftlich"),
        ("privat", 2026, 12,
         "/Steuer/Eingangsrechnungen/2026/12_Dezember/Privat"),
        # Unklare Zuordnung darf nicht in Privat oder Geschäftlich landen.
        (None, 2025, 1,
         "/Steuer/Eingangsrechnungen/2025/01_Januar/_Zu_pruefen"),
    ]

    fehler = 0
    for kategorie, jahr, monat, erwartet in faelle:
        got = str(target_dir(basis, kategorie, jahr, monat))
        if got != erwartet:
            print(f"FEHL  target_dir({kategorie!r}, {jahr}, {monat})")
            print(f"        = {got}")
            print(f"        erwartet {erwartet}")
            fehler += 1
    return fehler


def pruefe_entwurf():
    """ProVend darf im Entwurf an DATEV nirgends auftauchen."""
    rechnungen = [
        {
            "kategorie": "geschaeftlich", "provend": False,
            "datum": datetime(2026, 8, 4), "absender": "billing@ionity.eu",
            "betreff": "Rechnung Ladestrom",
            "attachments": [("ladestrom.pdf", b"%PDF-1.4")],
        },
        {
            "kategorie": "geschaeftlich", "provend": True,
            "datum": datetime(2026, 8, 9), "absender": "info@provenddeutschland.de",
            "betreff": "Rechnung 88",
            "attachments": [("provend.pdf", b"%PDF-1.4")],
        },
    ]
    draft = build_draft(rechnungen, "hegebehrens.rechnung@gmail.com", "August 2026")
    text = draft.get_body(preferencelist=("plain",)).get_content()
    anhaenge = [p.get_filename() for p in draft.iter_attachments()]

    fehler = 0
    if "provend" in text.lower():
        print("FEHL  Entwurfstext erwähnt ProVend")
        fehler += 1
    if "provend.pdf" in anhaenge:
        print("FEHL  ProVend-Beleg hängt am Entwurf")
        fehler += 1
    if "ladestrom.pdf" not in anhaenge:
        print("FEHL  regulärer Beleg fehlt am Entwurf")
        fehler += 1
    return fehler


def main():
    fehler = 0

    for subject, sender, body, erwartet in KLASSIFIZIERUNG:
        got = classify(subject, sender, body)
        if got != erwartet:
            print(f"FEHL  classify({sender!r}) = {got!r}, erwartet {erwartet!r}")
            fehler += 1

    for subject, mit_anhang, erwartet in ERKENNUNG:
        got = is_rechnung(subject, "a@b.de", "", ANHANG if mit_anhang else [])
        if got != erwartet:
            print(f"FEHL  is_rechnung({subject!r}) = {got}, erwartet {erwartet}")
            fehler += 1

    for sender, empfaenger, erwartet in PROVEND:
        got = ist_provend("Rechnung", sender, "", empfaenger)
        if got != erwartet:
            print(f"FEHL  ist_provend({sender!r}, {empfaenger!r}) = {got}, erwartet {erwartet}")
            fehler += 1

    fehler += pruefe_entwurf()
    fehler += pruefe_ablagepfad()
    fehler += pruefe_aufteilung()

    gesamt = len(KLASSIFIZIERUNG) + len(ERKENNUNG) + len(PROVEND) + 12
    if fehler:
        print(f"\n{fehler} von {gesamt} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"Alle {gesamt} Tests bestanden.")


if __name__ == "__main__":
    main()
