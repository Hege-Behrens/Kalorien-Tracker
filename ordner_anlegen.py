#!/usr/bin/env python3
"""Lege die Ordnerstruktur für Eingangsrechnungen in iCloud an.

Erzeugt unterhalb des Steuerordners:

    Eingangsrechnungen/<Jahr>/<MM_Monat>/Geschäftlich
    Eingangsrechnungen/<Jahr>/<MM_Monat>/Privat

ab 2025 bis zum laufenden Jahr. Bereits vorhandene Ordner bleiben unberührt,
das Skript kann also gefahrlos mehrfach laufen.

Muss lokal auf dem Mac laufen, auf dem iCloud Drive eingerichtet ist.
"""

import argparse
from datetime import datetime

from rechnungen_sortieren import (
    EINGANG_ORDNER,
    KATEGORIE_ORDNER,
    STARTJAHR,
    monatsordner,
    resolve_steuer_dir,
)


def anlegen(steuer_dir, von_jahr, bis_jahr, dry_run=False):
    basis = steuer_dir / EINGANG_ORDNER
    neu = 0
    vorhanden = 0

    for jahr in range(von_jahr, bis_jahr + 1):
        print(f"{jahr}")
        for monat in range(1, 13):
            monat_dir = basis / str(jahr) / monatsordner(monat)
            markierungen = []

            for ordner in KATEGORIE_ORDNER.values():
                ziel = monat_dir / ordner
                if ziel.exists():
                    vorhanden += 1
                    markierungen.append(f"{ordner} (vorhanden)")
                else:
                    if not dry_run:
                        ziel.mkdir(parents=True, exist_ok=True)
                    neu += 1
                    markierungen.append(f"{ordner} (neu)")

            print(f"  {monatsordner(monat):14} {'  '.join(markierungen)}")
        print()

    verb = "wären angelegt worden" if dry_run else "angelegt"
    print(f"{neu} Ordner {verb}, {vorhanden} waren schon da.")
    print(f"Basis: {basis}")


def main():
    heute = datetime.now()
    parser = argparse.ArgumentParser(
        description="Ordnerstruktur für Eingangsrechnungen anlegen.",
    )
    parser.add_argument("--von", type=int, default=STARTJAHR, help=f"Startjahr (Standard: {STARTJAHR})")
    parser.add_argument("--bis", type=int, default=heute.year, help="Endjahr (Standard: laufendes Jahr)")
    parser.add_argument("--steuer-dir", help="Pfad zum iCloud-Steuerordner")
    parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen, nichts anlegen")
    args = parser.parse_args()

    if args.bis < args.von:
        parser.error("--bis darf nicht vor --von liegen")

    steuer_dir = resolve_steuer_dir(args.steuer_dir)
    print(f"Steuerordner: {steuer_dir}\n")
    anlegen(steuer_dir, args.von, args.bis, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
