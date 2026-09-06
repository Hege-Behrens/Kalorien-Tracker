#!/usr/bin/env python3
"""Inventur- und Lagerverwaltung fuer die Verkaufsautomaten.

Beispiele:
    ./inventur.py anfangsbestand Lagerbestand.xlsx
    ./inventur.py einkauf beispiele/rechnung_selgros.csv --quelle selgros
    ./inventur.py verkauf beispiele/verkaeufe_automat.csv
    ./inventur.py bestand
    ./inventur.py warnungen
    ./inventur.py bericht --mail
"""

import argparse
import os
import sys
from datetime import date

from lager import bericht, daten, importe, versand
from lager.zuordnung import alias_lernen

BERICHTE = os.path.join(daten.BASIS, "berichte")


def _speichern(lager):
    daten.speichern(lager)
    daten.alias_speichern(lager)
    daten.sammelregeln_speichern(lager)


def _offene_melden(lager, ergebnis):
    offen = importe.offene_aktualisieren(lager, ergebnis["offen"], daten.OFFEN_CSV)
    if offen:
        print(f"\n{len(offen)} Zeile(n) konnten nicht zugeordnet werden.")
        print(f"Sie stehen in {os.path.relpath(daten.OFFEN_CSV, daten.BASIS)} und wurden NICHT gebucht.")
        print("Trage dort in der Spalte 'vorschlag' die passende artikel_id ein und fuehre aus:")
        print("    ./inventur.py zuordnen")


def cmd_anfangsbestand(args):
    lager = daten.laden()
    protokoll = importe.anfangsbestand_aus_excel(lager, args.datei, datum=args.datum, blatt=args.blatt)
    _speichern(lager)
    print(f"Artikel neu angelegt: {protokoll['neu']}, aktualisiert: {protokoll['aktualisiert']}, "
          f"zu Sammelartikeln zusammengefasst: {protokoll['zusammengefasst']}, "
          f"uebersprungen: {protokoll['uebersprungen']}")
    print(f"\n{bericht.als_text(lager)}")


def cmd_einkauf(args):
    lager = daten.laden()
    ergebnis = importe.belege_buchen(lager, args.datei, "EINKAUF",
                                     quelle_standard=args.quelle,
                                     automatisch_anlegen=args.neue_artikel)
    _speichern(lager)
    print(f"{len(ergebnis['gebucht'])} Position(en) als Wareneingang gebucht.")
    if ergebnis["dubletten"]:
        print(f"{ergebnis['dubletten']} Position(en) uebersprungen - Beleg war bereits erfasst.")
    _offene_melden(lager, ergebnis)


def cmd_verkauf(args):
    lager = daten.laden()
    ergebnis = importe.belege_buchen(lager, args.datei, "VERKAUF", quelle_standard="automat")
    _speichern(lager)
    print(f"{len(ergebnis['gebucht'])} Position(en) als Verkauf abgebucht.")
    if ergebnis["dubletten"]:
        print(f"{ergebnis['dubletten']} Position(en) uebersprungen - Beleg war bereits erfasst.")
    _offene_melden(lager, ergebnis)


def cmd_zuordnen(args):
    """Bucht die offenen Zeilen nach, sobald in 'vorschlag' eine artikel_id steht."""
    if not os.path.exists(daten.OFFEN_CSV):
        print("Keine offenen Zuordnungen.")
        return

    lager = daten.laden()
    offene = importe.offene_lesen(daten.OFFEN_CSV)

    rest, gebucht = [], 0
    for zeile in offene:
        artikel_id = zeile.get("vorschlag", "").strip()
        if not artikel_id:
            rest.append(zeile)
            continue
        if artikel_id not in lager.artikel:
            print(f"Unbekannte artikel_id '{artikel_id}' bei '{zeile['bezeichnung']}' - uebersprungen.")
            rest.append(zeile)
            continue

        menge = int(zeile["menge"])
        if zeile.get("einheit", "").startswith("gebinde"):
            menge *= max(1, lager.artikel[artikel_id].stueck_pro_gebinde)

        typ = "VERKAUF" if zeile.get("quelle") == "automat" else "EINKAUF"
        lager.buchen(daten.Bewegung(
            datum=zeile["datum"], typ=typ, artikel_id=artikel_id, menge=menge,
            beleg=zeile.get("beleg", ""), bezeichnung=zeile["bezeichnung"],
            quelle=zeile.get("quelle", ""), notiz="manuell zugeordnet",
        ))
        # Zuordnung merken, damit dieselbe Bezeichnung kuenftig automatisch passt.
        alias_lernen(lager, zeile.get("quelle", ""), zeile["bezeichnung"], artikel_id)
        gebucht += 1

    _speichern(lager)
    rest = importe.offene_aktualisieren(lager, [], daten.OFFEN_CSV)
    print(f"{gebucht} Position(en) nachgebucht, {len(rest)} weiterhin offen.")
    if gebucht:
        print("Die Zuordnungen wurden gelernt und greifen ab sofort automatisch.")


def cmd_sammelartikel(args):
    """Legt eine Sammelregel an: alle Bezeichnungen mit dem Muster -> ein Artikel."""
    lager = daten.laden()
    muster = daten.normalisieren(args.muster)
    if not muster:
        sys.exit("Das Muster darf nicht leer sein.")

    artikel_id = args.artikel_id or lager.naechste_artikel_id(args.name or args.muster)
    vorhandene = [r for r in lager.sammelregeln if r.muster == muster]
    if vorhandene:
        print(f"Regel '{muster}' besteht bereits (-> {vorhandene[0].artikel_id}).")
        return

    lager.sammelregeln.append(daten.Sammelregel(
        muster=muster, artikel_id=artikel_id, name=args.name or args.muster))
    if artikel_id not in lager.artikel:
        lager.artikel[artikel_id] = daten.Artikel(
            artikel_id=artikel_id,
            name=args.name or args.muster,
            stueck_pro_gebinde=args.gebinde,
            mindestbestand=args.mindestbestand,
        )

    # Bereits gebuchte Einzelsorten auf den Sammelartikel umziehen, damit der
    # Bestand nicht auf alte Sorten verteilt liegen bleibt.
    umgezogen = 0
    for bewegung in lager.bewegungen:
        if bewegung.artikel_id == artikel_id:
            continue
        text = bewegung.bezeichnung or lager.artikel[bewegung.artikel_id].name
        if muster.replace(" ", "") in daten.normalisieren(text).replace(" ", ""):
            bewegung.artikel_id = artikel_id
            umgezogen += 1

    # Sorten, die dadurch keine Bewegung mehr haben, stilllegen.
    aktive = {b.artikel_id for b in lager.bewegungen}
    stillgelegt = 0
    for a in lager.artikel.values():
        if a.artikel_id != artikel_id and a.aktiv and a.artikel_id not in aktive \
                and muster.replace(" ", "") in daten.normalisieren(a.name).replace(" ", ""):
            a.aktiv = False
            stillgelegt += 1

    _speichern(lager)
    print(f"Sammelartikel '{args.name or args.muster}' angelegt (id: {artikel_id}).")
    print(f"Alles mit '{muster}' in der Bezeichnung wird ab sofort hierauf gebucht.")
    if umgezogen:
        print(f"{umgezogen} bereits gebuchte Bewegung(en) umgezogen, "
              f"{stillgelegt} Einzelsorte(n) stillgelegt.")


def cmd_bestand(args):
    print(bericht.als_text(daten.laden()))


def cmd_warnungen(args):
    print(bericht.als_text(daten.laden(), nur_warnungen=True))


def cmd_korrektur(args):
    """Zaehlbestand einbuchen - die Differenz wird als KORREKTUR verbucht."""
    lager = daten.laden()
    if args.artikel_id not in lager.artikel:
        sys.exit(f"Unbekannter Artikel: {args.artikel_id}")
    ist = lager.bestand().get(args.artikel_id, 0)
    differenz = args.gezaehlt - ist
    if differenz == 0:
        print("Bestand stimmt bereits - keine Buchung noetig.")
        return
    lager.buchen(daten.Bewegung(
        datum=args.datum or daten.heute(), typ="KORREKTUR",
        artikel_id=args.artikel_id, menge=differenz,
        beleg=f"korrektur-{daten.heute()}",
        bezeichnung=lager.artikel[args.artikel_id].name, quelle="inventur",
        notiz=args.notiz or f"gezaehlt {args.gezaehlt}, gebucht {ist}",
    ))
    _speichern(lager)
    print(f"Korrektur gebucht: {differenz:+d} Stueck ({ist} -> {args.gezaehlt}).")


def cmd_bericht(args):
    lager = daten.laden()
    os.makedirs(BERICHTE, exist_ok=True)
    stand = date.today().isoformat()
    pfad = os.path.join(BERICHTE, f"bestandsliste_{stand}.xlsx")
    bericht.als_excel(lager, pfad)
    print(f"Bericht geschrieben: {os.path.relpath(pfad, daten.BASIS)}")

    offene = bericht.warnungen(lager)
    text = (
        f"Bestandsliste vom {stand}\n\n"
        f"{len(offene)} von {len(lager.artikel)} Artikeln brauchen Aufmerksamkeit:\n\n"
        f"{bericht.als_text(lager, nur_warnungen=True)}\n\n"
        "Die vollstaendige Liste haengt als Excel-Datei an.\n"
    )
    print()
    print(text)

    if args.mail:
        empfaenger = versand.senden(f"Bestandsliste Automaten - {stand}", text, pfad)
        print(f"E-Mail versendet an: {', '.join(empfaenger)}")


def main():
    p = argparse.ArgumentParser(description="Lagerverwaltung Verkaufsautomaten")
    unter = p.add_subparsers(dest="befehl", required=True)

    a = unter.add_parser("anfangsbestand", help="Lager-Excel einlesen und als Anfangsbestand buchen")
    a.add_argument("datei")
    a.add_argument("--datum", help="Stichtag der Inventur (Standard: heute)")
    a.add_argument("--blatt", help="Name des Tabellenblatts")
    a.set_defaults(func=cmd_anfangsbestand)

    e = unter.add_parser("einkauf", help="Rechnungspositionen als Wareneingang buchen")
    e.add_argument("datei")
    e.add_argument("--quelle", default="", help="Lieferant, z.B. selgros oder rewe")
    e.add_argument("--neue-artikel", action="store_true",
                   help="Unbekannte Positionen als neuen Artikel anlegen statt zurueckzustellen")
    e.set_defaults(func=cmd_einkauf)

    v = unter.add_parser("verkauf", help="Verkaufszahlen der Automaten abbuchen")
    v.add_argument("datei")
    v.set_defaults(func=cmd_verkauf)

    z = unter.add_parser("zuordnen", help="Offene Zuordnungen nachbuchen")
    z.set_defaults(func=cmd_zuordnen)

    sa = unter.add_parser("sammelartikel",
                          help="Sorten unter einem Artikel zusammenfassen (z.B. Elf Bar Pots)")
    sa.add_argument("muster", help="Text, der in der Bezeichnung vorkommen muss, z.B. 'Elf Bar'")
    sa.add_argument("--name", help="Anzeigename des Sammelartikels")
    sa.add_argument("--artikel-id", dest="artikel_id", help="feste ID (Standard: aus dem Namen)")
    sa.add_argument("--mindestbestand", type=int, default=0)
    sa.add_argument("--gebinde", type=int, default=1, help="Stueck pro Gebinde")
    sa.set_defaults(func=cmd_sammelartikel)

    unter.add_parser("bestand", help="Aktuelle Bestandsliste anzeigen").set_defaults(func=cmd_bestand)
    unter.add_parser("warnungen", help="Nur Artikel unter Mindestbestand").set_defaults(func=cmd_warnungen)

    k = unter.add_parser("korrektur", help="Gezaehlten Bestand einbuchen")
    k.add_argument("artikel_id")
    k.add_argument("gezaehlt", type=int)
    k.add_argument("--datum")
    k.add_argument("--notiz")
    k.set_defaults(func=cmd_korrektur)

    b = unter.add_parser("bericht", help="Excel-Bestandsliste erzeugen, optional per Mail")
    b.add_argument("--mail", action="store_true", help="Bericht an die hinterlegten Empfaenger senden")
    b.set_defaults(func=cmd_bericht)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
