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

        # Verkaeufe: nur ab dem Stichtag, alles davor steckt im Anfangsbestand.
        lauf(arbeit, "stichtag", "2026-09-06T15:00")
        ausgabe = lauf(arbeit, "verkauf", "beispiele/verkaeufe_automat.csv")
        assert "2 Position(en) vor dem Stichtag" in ausgabe, ausgabe
        assert bestand_von(arbeit, "sprite-033l") == 34 + 5 * 24 - 3 - 7, \
            "Verkaeufe vor dem Stichtag wurden mitgerechnet"

        # Ueberlappender Folgeexport: die alten Zeilen duerfen nicht erneut
        # abgebucht werden, nur die beiden neuen.
        ausgabe = lauf(arbeit, "verkauf", "beispiele/verkaeufe_automat_folgewoche.csv")
        assert "2 Position(en) als Verkauf abgebucht" in ausgabe, ausgabe
        assert "5 Position(en) uebersprungen - bereits gebucht" in ausgabe, ausgabe
        assert bestand_von(arbeit, "sprite-033l") == 34 + 5 * 24 - 3 - 7 - 4, \
            "Ueberlappung wurde doppelt gebucht"

        # Derselbe Export ein drittes Mal aendert gar nichts mehr.
        vorher = bestand_von(arbeit, "sprite-033l")
        lauf(arbeit, "verkauf", "beispiele/verkaeufe_automat_folgewoche.csv")
        assert bestand_von(arbeit, "sprite-033l") == vorher, "Wiederholter Import hat gebucht"

        # Zaehlkorrektur.
        lauf(arbeit, "korrektur", "sprite-033l", "140")
        assert bestand_von(arbeit, "sprite-033l") == 140, "Korrektur nicht wirksam"

        # Zeilen ohne Uhrzeit am Stichtag selbst werden vorgelegt, nicht geraten.
        unklar = os.path.join(arbeit, "nur_datum.csv")
        with open(unklar, "w", encoding="utf-8") as f:
            f.write("Datum;Automat;Artikel;Menge\n06.09.2026;Glückstadt;Sprite 0,33l;5\n")
        ausgabe = lauf(arbeit, "verkauf", unklar)
        assert "ohne verwertbare Uhrzeit" in ausgabe, ausgabe
        assert bestand_von(arbeit, "sprite-033l") == 140, "Unklare Zeile wurde gebucht"

        # Sammelartikel: 14 aus der Excel, minus Verkaeufe zweier Sorten, plus
        # 6 Stueck aus der Grosshandelsrechnung - alles auf einem Artikel.
        assert bestand_von(arbeit, "elfbar-pods") == 14 - 1 - 2, "Sortenverkauf nicht zusammengefasst"
        lauf(arbeit, "einkauf", "beispiele/rechnung_grosshandel.csv", "--quelle", "grosshandel")
        assert bestand_von(arbeit, "elfbar-pods") == 14 - 1 - 2 + 6, \
            "Sorten der Rechnung nicht zusammengefasst"
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

    pruefe_ohne_zeitzonen()
    print("Alle Pruefungen bestanden.")


def pruefe_ohne_zeitzonen():
    """Der Verbindungsstand darf ohne Zeitzonendatenbank nicht abstuerzen.

    Windows bringt keine mit. Ein Anzeigekomfort - der Kontaktzeitpunkt in
    deutscher Zeit - hat dort einmal den ganzen Tagesbericht zum Absturz
    gebracht. Er muss auch ohne die Datenbank durchlaufen.
    """
    import zoneinfo
    from datetime import datetime, timedelta, timezone

    # Die vorherigen Pruefungen haben lager aus einem Temporaerverzeichnis
    # geladen, das inzwischen geloescht ist. Hier ist das echte Projekt gemeint.
    for modul in [m for m in list(sys.modules) if m.startswith("lager")]:
        del sys.modules[modul]
    sys.path.insert(0, BASIS)
    from lager import vensoft

    vorher = list(zoneinfo.TZPATH)
    try:
        zoneinfo.reset_tzpath([])
        try:
            zoneinfo.ZoneInfo("Europe/Berlin")
            return  # tzdata ist installiert, die Probe waere ohne Aussage
        except zoneinfo.ZoneInfoNotFoundError:
            pass

        jetzt = datetime.now(timezone.utc)
        tabelle = {
            "kontakt_je_automat": {"a1": (jetzt - timedelta(hours=1)).strftime(
                "%Y-%m-%d %H:%M:%S+00")},
            "ort_je_automat": {"a1": "Teststandort"},
        }
        stand = vensoft.verbindungsstand(tabelle, jetzt=jetzt)
        assert len(stand) == 1, "Verbindungsstand ohne Zeitzonendatenbank leer"
        assert stand[0]["letzter_kontakt"] is not None, "Zeitpunkt verloren"
        assert not stand[0]["still"], "Kontakt vor einer Stunde gilt als still"
    finally:
        zoneinfo.reset_tzpath(vorher)
        if BASIS in sys.path:
            sys.path.remove(BASIS)


if __name__ == "__main__":
    main()
