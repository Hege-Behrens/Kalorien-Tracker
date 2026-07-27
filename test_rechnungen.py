#!/usr/bin/env python3
"""Tests für die Erkennungs- und Zuordnungsregeln.

Aufruf:  python3 test_rechnungen.py
"""

import sys

from rechnungen_sortieren import classify, is_rechnung, nur_sortieren


ANHANG = [("beleg.pdf", b"%PDF-1.4")]

# (Betreff, Absender, Body, erwartete Kategorie)
KLASSIFIZIERUNG = [
    ("Rechnung", "no-reply@immobilienscout24.de", "", "geschaeftlich"),
    ("Rechnung", "kundenservice@is24.de", "", "geschaeftlich"),
    ("Honorarrechnung", "m.weitzel@kanzlei.de", "Meike Weitzel", "geschaeftlich"),
    ("Rechnung", "meike.weitzel@buero.de", "", "geschaeftlich"),
    ("Rechnung", "info@provenddeutschland.de", "", "geschaeftlich"),
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

# (Absender, ob vom Upload ausgenommen)
AUSSCHLUSS = [
    ("info@provenddeutschland.de", True),
    ("billing@ionity.eu", False),
    ("no-reply@immobilienscout24.de", False),
]


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

    for sender, erwartet in AUSSCHLUSS:
        got = nur_sortieren("Rechnung", sender, "")
        if got != erwartet:
            print(f"FEHL  nur_sortieren({sender!r}) = {got}, erwartet {erwartet}")
            fehler += 1

    gesamt = len(KLASSIFIZIERUNG) + len(ERKENNUNG) + len(AUSSCHLUSS)
    if fehler:
        print(f"\n{fehler} von {gesamt} Tests fehlgeschlagen.")
        sys.exit(1)
    print(f"Alle {gesamt} Tests bestanden.")


if __name__ == "__main__":
    main()
