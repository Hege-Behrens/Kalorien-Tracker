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
        # sammelregeln.csv bleibt bewusst erhalten - sie ist Konfiguration, keine Bewegungsdatei.
        for datei in ("artikel.csv", "bewegungen.csv", "aliase.csv", "offene_zuordnungen.csv"):
            pfad = os.path.join(arbeit, "data", datei)
            if os.path.exists(pfad):
                os.remove(pfad)

        lauf(arbeit, "anfangsbestand", "beispiele/Lagerbestand_beispiel.xlsx", "--datum", "2026-09-01")
        assert bestand_von(arbeit, "coca-cola-033l-dose") == 240, "Anfangsbestand nicht uebernommen"
        # Vier Elf-Bar-Sorten (14+9+11+6) landen als ein Posten im Lager.
        assert bestand_von(arbeit, "elf-bar-pots") == 40, "Sortenzeilen nicht zusammengefasst"

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

        # Sammelartikel: 40 aus der Excel, minus 27 Verkaeufe, plus 6 Gebinde
        # a 10 aus der Grosshandelsrechnung - alles auf einem Artikel.
        assert bestand_von(arbeit, "elf-bar-pots") == 13, "Sortenverkauf nicht zusammengefasst"
        lauf(arbeit, "einkauf", "beispiele/rechnung_grosshandel.csv", "--quelle", "grosshandel")
        assert bestand_von(arbeit, "elf-bar-pots") == 73, "Sorten der Rechnung nicht zusammengefasst"

        sys.path.insert(0, arbeit)
        for modul in [m for m in list(sys.modules) if m.startswith("lager")]:
            del sys.modules[modul]
        from lager import daten as d
        sorten = [a for a in d.laden().artikel.values()
                  if "ELF" in a.name.upper() and a.artikel_id != "elf-bar-pots"]
        sys.path.remove(arbeit)
        assert not sorten, f"Einzelsorten angelegt statt zusammengefasst: {sorten}"

        ausgabe = lauf(arbeit, "warnungen")
        assert "Kinder Riegel 21g" in ausgabe, "Leerer Artikel fehlt in den Warnungen"

        lauf(arbeit, "bericht")
        berichte = os.listdir(os.path.join(arbeit, "berichte"))
        assert any(d.endswith(".xlsx") for d in berichte), "Kein Excel-Bericht erzeugt"

    print("Alle Pruefungen bestanden.")


if __name__ == "__main__":
    main()
