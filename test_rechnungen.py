#!/usr/bin/env python3
"""Tests für die Erkennungs- und Zuordnungsregeln.

Aufruf:  python3 test_rechnungen.py
"""

import sys
from datetime import datetime

from pathlib import Path

from rechnungen_sortieren import (
    build_draft,
    classify,
    is_rechnung,
    ist_provend,
    target_dir,
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
    ("Rechnung Wallbox", "a@b.de", "", "geschaeftlich"),
    ("Rechnung", "no-reply@netflix.com", "", "privat"),
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
    draft = build_draft(rechnungen, 2026, 8, "hegebehrens.rechnung@gmail.com")
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

    gesamt = len(KLASSIFIZIERUNG) + len(ERKENNUNG) + len(PROVEND) + 6
    if fehler:
        print(f"\n{fehler} von {gesamt} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"Alle {gesamt} Tests bestanden.")


if __name__ == "__main__":
    main()
