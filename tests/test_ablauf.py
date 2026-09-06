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


def gebinde_setzen(arbeitsverzeichnis, artikel_id, groesse):
    """Traegt eine Gebindegroesse im Artikelstamm nach."""
    import csv
    pfad = os.path.join(arbeitsverzeichnis, "data", "artikel.csv")
    with open(pfad, newline="", encoding="utf-8") as f:
        zeilen = list(csv.DictReader(f))
        felder = zeilen[0].keys()
    for zeile in zeilen:
        if zeile["artikel_id"] == artikel_id:
            zeile["stueck_pro_gebinde"] = str(groesse)
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)


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
        assert bestand_von(arbeit, "sprite-033l") == 34, "Anfangsbestand nicht uebernommen"
        # Vier Pod-Sorten (6+1+5+2) landen als ein Posten - das Basisgeraet
        # ist kein Pod und muss ein eigener Artikel bleiben.
        assert bestand_von(arbeit, "elfbar-pods") == 14, "Sortenzeilen nicht zusammengefasst"
        assert bestand_von(arbeit, "elfbar-basisgeraet") == 9, "Basisgeraet faelschlich eingesammelt"

        # Rechnung: Stueck-Positionen laufen durch, Gebinde-Positionen ohne
        # hinterlegte Gebindegroesse werden zurueckgestellt statt falsch gebucht.
        ausgabe = lauf(arbeit, "einkauf", "beispiele/rechnung_selgros.csv", "--quelle", "selgros")
        assert "1 Position(en)" in ausgabe, ausgabe
        assert "Gebindegroesse fehlt" in ausgabe, ausgabe
        assert bestand_von(arbeit, "sprite-033l") == 34, "Gebinde ohne Groesse wurde gebucht"

        # Dieselbe Rechnung darf nicht doppelt buchen.
        ausgabe = lauf(arbeit, "einkauf", "beispiele/rechnung_selgros.csv", "--quelle", "selgros")
        assert "0 Position(en) als Wareneingang" in ausgabe, ausgabe

        # Gebindegroesse nachtragen, dann greift die Nachbuchung.
        gebinde_setzen(arbeit, "sprite-033l", 24)
        lauf(arbeit, "zuordnen")
        assert bestand_von(arbeit, "sprite-033l") == 34 + 5 * 24, "Nachbuchung falsch verrechnet"

        # Verkaeufe der Automaten mindern den Bestand.
        lauf(arbeit, "verkauf", "beispiele/verkaeufe_automat.csv")
        assert bestand_von(arbeit, "sprite-033l") == 34 + 5 * 24 - 12, "Verkauf nicht abgebucht"

        # Zaehlkorrektur.
        lauf(arbeit, "korrektur", "sprite-033l", "140")
        assert bestand_von(arbeit, "sprite-033l") == 140, "Korrektur nicht wirksam"

        # Sammelartikel: 14 aus der Excel, minus 4 Verkaeufe, plus 6 Stueck
        # aus der Grosshandelsrechnung - alles auf einem Artikel.
        assert bestand_von(arbeit, "elfbar-pods") == 10, "Sortenverkauf nicht zusammengefasst"
        lauf(arbeit, "einkauf", "beispiele/rechnung_grosshandel.csv", "--quelle", "grosshandel")
        assert bestand_von(arbeit, "elfbar-pods") == 16, "Sorten der Rechnung nicht zusammengefasst"
        assert bestand_von(arbeit, "elfbar-basisgeraet") == 13, "Basisgeraet nicht separat gebucht"

        sys.path.insert(0, arbeit)
        for modul in [m for m in list(sys.modules) if m.startswith("lager")]:
            del sys.modules[modul]
        from lager import daten as d
        sorten = [a.name for a in d.laden().artikel.values()
                  if "POD" in a.name.upper() and a.artikel_id != "elfbar-pods"]
        sys.path.remove(arbeit)
        assert not sorten, f"Einzelsorten angelegt statt zusammengefasst: {sorten}"

        ausgabe = lauf(arbeit, "warnungen")
        assert "Schwipp Schwapp" in ausgabe, "Leerer Artikel fehlt in den Warnungen"

        lauf(arbeit, "bericht")
        berichte = os.listdir(os.path.join(arbeit, "berichte"))
        assert any(d.endswith(".xlsx") for d in berichte), "Kein Excel-Bericht erzeugt"

    print("Alle Pruefungen bestanden.")


if __name__ == "__main__":
    main()
