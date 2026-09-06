#!/usr/bin/env python3
"""Selbsttest: spielt den kompletten Ablauf auf einer Kopie der Beispieldaten durch.

Aufruf:  python3 tests/test_ablauf.py
"""

import os
import shutil
import subprocess
import sys
import tempfile

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def lauf(arbeitsverzeichnis, *argumente):
    ergebnis = subprocess.run(
        [sys.executable, os.path.join(arbeitsverzeichnis, "inventur.py"), *argumente],
        capture_output=True, text=True, cwd=arbeitsverzeichnis,
    )
    if ergebnis.returncode != 0:
        raise AssertionError(f"Befehl fehlgeschlagen: {argumente}\n{ergebnis.stderr}")
    return ergebnis.stdout


def bestand_von(arbeitsverzeichnis, artikel_id):
    sys.path.insert(0, arbeitsverzeichnis)
    for modul in [m for m in list(sys.modules) if m.startswith("lager")]:
        del sys.modules[modul]
    from lager import daten
    wert = daten.laden().bestand().get(artikel_id, 0)
    sys.path.remove(arbeitsverzeichnis)
    return wert


def main():
    with tempfile.TemporaryDirectory() as tmp:
        arbeit = os.path.join(tmp, "lagerprojekt")
        shutil.copytree(BASIS, arbeit, ignore=shutil.ignore_patterns(".git", "__pycache__", "berichte"))
        for datei in ("artikel.csv", "bewegungen.csv", "aliase.csv", "offene_zuordnungen.csv"):
            pfad = os.path.join(arbeit, "data", datei)
            if os.path.exists(pfad):
                os.remove(pfad)

        lauf(arbeit, "anfangsbestand", "beispiele/Lagerbestand_beispiel.xlsx", "--datum", "2026-09-01")
        assert bestand_von(arbeit, "coca-cola-033l-dose") == 240, "Anfangsbestand nicht uebernommen"

        # Rechnung: 5 Gebinde a 24 = 120 Stueck dazu.
        ausgabe = lauf(arbeit, "einkauf", "beispiele/rechnung_selgros.csv", "--quelle", "selgros")
        assert "3 Position(en)" in ausgabe, ausgabe
        assert bestand_von(arbeit, "coca-cola-033l-dose") == 360, "Wareneingang falsch verrechnet"

        # Dieselbe Rechnung darf nicht doppelt buchen.
        ausgabe = lauf(arbeit, "einkauf", "beispiele/rechnung_selgros.csv", "--quelle", "selgros")
        assert "0 Position(en) als Wareneingang" in ausgabe, ausgabe
        assert bestand_von(arbeit, "coca-cola-033l-dose") == 360, "Dublette wurde gebucht"

        # Verkaeufe der Automaten mindern den Bestand.
        lauf(arbeit, "verkauf", "beispiele/verkaeufe_automat.csv")
        assert bestand_von(arbeit, "coca-cola-033l-dose") == 276, "Verkauf nicht abgebucht"

        # Zaehlkorrektur.
        lauf(arbeit, "korrektur", "coca-cola-033l-dose", "270")
        assert bestand_von(arbeit, "coca-cola-033l-dose") == 270, "Korrektur nicht wirksam"

        ausgabe = lauf(arbeit, "warnungen")
        assert "Kinder Riegel 21g" in ausgabe, "Leerer Artikel fehlt in den Warnungen"

        lauf(arbeit, "bericht")
        berichte = os.listdir(os.path.join(arbeit, "berichte"))
        assert any(d.endswith(".xlsx") for d in berichte), "Kein Excel-Bericht erzeugt"

    print("Alle Pruefungen bestanden.")


if __name__ == "__main__":
    main()
