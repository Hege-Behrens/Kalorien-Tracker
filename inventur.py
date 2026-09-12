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
from datetime import date, timedelta

from lager import bericht, daten, importe, versand
from lager import zeit as zeitmodul
from lager.zuordnung import alias_lernen, zuordnen

BERICHTE = os.path.join(daten.BASIS, "berichte")


def _env_dateien():
    """Mögliche Orte der Zugangsdaten, wichtigster zuerst.

    Liegt das Projekt in einem synchronisierten OneDrive-Ordner, würde eine
    .env darin samt Passwörtern in die Cloud wandern. Deshalb wird zuerst
    ausserhalb gesucht: PROVEND_ENV zeigt auf eine beliebige Datei, sonst gilt
    .provend.env im Benutzerprofil. Die .env im Projekt bleibt als bequemer
    Weg bestehen, wenn das Projekt nicht synchronisiert wird.
    """
    orte = []
    if os.environ.get("PROVEND_ENV"):
        orte.append(os.environ["PROVEND_ENV"])
    heim = os.path.expanduser("~")
    if heim and heim != "~":
        # Vier Schreibweisen, weil Windows an dieser Stelle vier Fallen stellt:
        # der Editor haengt ein .txt an, auch wenn "Alle Dateien" gewaehlt ist;
        # der Explorer blendet die Endung aus, sodass es richtig aussieht; und
        # Namen mit fuehrendem Punkt lassen sich im Explorer nur umstaendlich
        # anlegen. An keiner dieser Huerden soll die Einrichtung scheitern.
        for name in (".provend.env", ".provend.env.txt",
                     "provend.env", "provend.env.txt"):
            orte.append(os.path.join(heim, name))
    orte.append(os.path.join(daten.BASIS, ".env"))
    orte.append(os.path.join(daten.BASIS, ".env.txt"))
    return orte


def _umgebung_laden():
    """Liest die Zugangsdaten aus der ersten gefundenen Datei.

    Unter Linux setzt man sie mit `export`, unter Windows ist das umstaendlich
    und in der Aufgabenplanung gar nicht vorgesehen. Eine Datei funktioniert
    auf beiden Systemen gleich. Bereits gesetzte Umgebungsvariablen haben
    Vorrang, und eine frueher gelesene Datei schlaegt eine spaetere.
    """
    for pfad in _env_dateien():
        if not os.path.exists(pfad):
            continue
        with open(pfad, encoding="utf-8-sig") as f:
            for zeile in f:
                zeile = zeile.strip()
                if not zeile or zeile.startswith("#") or "=" not in zeile:
                    continue
                schluessel, _, wert = zeile.partition("=")
                schluessel = schluessel.strip()
                if schluessel.startswith("export "):
                    schluessel = schluessel[7:].strip()
                os.environ.setdefault(schluessel, wert.strip().strip('"').strip("'"))


_umgebung_laden()


def _speichern(lager):
    daten.speichern(lager)
    daten.alias_speichern(lager)
    daten.sammelregeln_speichern(lager)
    daten.einstellungen_speichern(lager)


def _offene_melden(lager, ergebnis):
    offen = importe.offene_aktualisieren(lager, ergebnis["offen"], daten.OFFEN_CSV)
    if offen:
        print(f"\n{len(offen)} Zeile(n) wurden NICHT gebucht - sie stehen in "
              f"{os.path.relpath(daten.OFFEN_CSV, daten.BASIS)}:")
        for zeile in offen:
            print(f"  - {zeile['bezeichnung']}: {zeile['hinweis']}")
        print("Fehlende Zuordnung: artikel_id in die Spalte 'vorschlag' eintragen.")
        print("Danach:  ./inventur.py zuordnen")


def cmd_anfangsbestand(args):
    lager = daten.laden()
    protokoll = importe.anfangsbestand_aus_excel(
        lager, args.datei, datum=args.datum, blatt=args.blatt, mengenspalte=args.mengenspalte)
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
    stichtag = lager.einstellungen.get("verkauf_ab", "")
    ergebnis = importe.belege_buchen(lager, args.datei, "VERKAUF", quelle_standard="automat")
    _speichern(lager)

    print(f"{len(ergebnis['gebucht'])} Position(en) als Verkauf abgebucht.")
    if ergebnis["vor_stichtag"]:
        print(f"{ergebnis['vor_stichtag']} Position(en) vor dem Stichtag {stichtag} "
              f"uebersprungen - sie stecken bereits im Anfangsbestand.")
    if ergebnis["dubletten"]:
        print(f"{ergebnis['dubletten']} Position(en) uebersprungen - bereits gebucht.")
    if ergebnis["ohne_zeit"]:
        print(f"\n{len(ergebnis['ohne_zeit'])} Position(en) ohne verwertbare Uhrzeit am "
              f"Stichtag - NICHT gebucht, weil unklar ist, ob sie vor oder nach "
              f"{stichtag} liegen:")
        for name in ergebnis["ohne_zeit"][:10]:
            print(f"  - {name}")
        if len(ergebnis["ohne_zeit"]) > 10:
            print(f"  ... und {len(ergebnis['ohne_zeit']) - 10} weitere")
    _offene_melden(lager, ergebnis)


def cmd_vensoft(args):
    """Holt die Verkaeufe aus der Vensoft-Schnittstelle und bucht sie ab.

    Gebucht wird nur, was den Automaten tatsaechlich verlassen hat und nach
    dem Stichtag liegt. Als Belegnummer dient die Verkaufs-ID von Vensoft -
    damit ist eine Doppelbuchung ausgeschlossen, auch wenn derselbe Zeitraum
    mehrfach abgerufen wird.
    """
    from lager import vensoft

    lager = daten.laden()

    stamm, verkaeufe = _vensoft_daten(args.aus_datei)

    tabelle = vensoft.uebersetzungstabelle(stamm)
    stichtag, _ = zeitmodul.lesen(lager.einstellungen.get("verkauf_ab", ""))
    bekannt = lager.positionen()

    gebucht, umsatz = 0, 0.0
    verworfen, vor_stichtag, dubletten = 0, 0, 0
    offen = []

    for verkauf in sorted(verkaeufe, key=lambda v: v.get("tstamp") or ""):
        if not vensoft.ist_ausgegeben(verkauf, tabelle):
            verworfen += 1
            continue

        zeitpunkt, _ = zeitmodul.lesen((verkauf.get("tstamp") or "")[:19])
        if stichtag and zeitpunkt and zeitpunkt < stichtag:
            vor_stichtag += 1
            continue

        bezeichnung = tabelle["produkt"].get(verkauf.get("product_id"), "")
        if not bezeichnung or bezeichnung == "Unbekannt":
            verworfen += 1
            continue

        beleg = f"vensoft:{verkauf['id']}"
        if (beleg, daten.normalisieren(bezeichnung)) in bekannt:
            dubletten += 1
            continue

        artikel_id, guete, methode = zuordnen(lager, "vensoft", bezeichnung)
        if artikel_id is None:
            offen.append({
                "datum": zeitpunkt.date().isoformat() if zeitpunkt else daten.heute(),
                "quelle": "vensoft", "bezeichnung": bezeichnung, "menge": 1,
                "einheit": "stueck", "beleg": beleg, "ean": "", "vorschlag": "",
                "guete": f"{guete:.2f}", "hinweis": "kein passender Lagerartikel",
            })
            continue

        lager.buchen(daten.Bewegung(
            datum=zeitpunkt.date().isoformat() if zeitpunkt else daten.heute(),
            typ="VERKAUF", artikel_id=artikel_id, menge=1, beleg=beleg,
            bezeichnung=bezeichnung,
            quelle=tabelle["automat"].get(verkauf.get("parent_id"), "automat"),
            notiz=methode,
        ))
        # Zuordnung merken, damit sie beim naechsten Mal sofort greift.
        alias_lernen(lager, "vensoft", bezeichnung, artikel_id)
        gebucht += 1
        umsatz += vensoft.betrag(verkauf)

    _speichern(lager)

    print(f"{gebucht} Verkauf/Verkaeufe gebucht, Umsatz {umsatz:.2f} EUR")
    if vor_stichtag:
        print(f"{vor_stichtag} vor dem Stichtag uebersprungen")
    if dubletten:
        print(f"{dubletten} bereits gebucht")
    if verworfen:
        print(f"{verworfen} ohne Warenausgabe (Stoerung, Abbruch, leerer Schacht) "
              f"oder ohne Produktzuordnung")
    _offene_melden(lager, {"offen": offen})


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

        artikel = lager.artikel[artikel_id]
        menge = int(zeile["menge"])
        if zeile.get("einheit", "").startswith("gebinde"):
            if artikel.stueck_pro_gebinde <= 1:
                print(f"'{artikel.name}': Gebindegroesse fehlt weiterhin - uebersprungen.")
                rest.append(zeile)
                continue
            menge *= artikel.stueck_pro_gebinde

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


def cmd_empfaenger(args):
    """Zeigt oder setzt die Empfaenger der woechentlichen Bestandsliste."""
    lager = daten.laden()
    if not args.adressen:
        aktuell = versand.empfaenger_liste(lager)
        if aktuell:
            print("Die Bestandsliste geht an:")
            for adresse in aktuell:
                print(f"  - {adresse}")
        else:
            print("Keine Empfaenger gesetzt.")
        return

    adressen = []
    for eintrag in args.adressen:
        for adresse in versand.zerlegen(eintrag):
            if "@" not in adresse or "." not in adresse.split("@")[-1]:
                sys.exit(f"Das sieht nicht nach einer E-Mail-Adresse aus: {adresse}")
            if adresse not in adressen:
                adressen.append(adresse)

    lager.einstellungen["empfaenger"] = ",".join(adressen)
    _speichern(lager)
    print(f"{len(adressen)} Empfaenger gespeichert:")
    for adresse in adressen:
        print(f"  - {adresse}")


def cmd_stichtag(args):
    """Setzt oder zeigt den Zeitpunkt, ab dem Verkaeufe gebucht werden."""
    lager = daten.laden()
    if not args.zeitpunkt:
        aktuell = lager.einstellungen.get("verkauf_ab")
        print(f"Verkaeufe werden gebucht ab: {aktuell}" if aktuell
              else "Kein Stichtag gesetzt - alle Verkaufszeilen werden gebucht.")
        return

    zeitpunkt, hat_uhrzeit = zeitmodul.lesen(args.zeitpunkt)
    if zeitpunkt is None:
        sys.exit(f"Zeitpunkt nicht lesbar: {args.zeitpunkt} (z.B. 2026-09-06T15:00)")
    if not hat_uhrzeit:
        print("Hinweis: ohne Uhrzeit gilt 00:00 Uhr.")
    lager.einstellungen["verkauf_ab"] = zeitpunkt.isoformat()
    _speichern(lager)
    print(f"Stichtag gesetzt: Verkaeufe ab {zeitpunkt.isoformat()} werden gebucht, "
          f"alles davor gilt als im Anfangsbestand enthalten.")


def _verbrauch_aus_vensoft(lager, aus_datei, tage):
    """Taeglicher Verbrauch je Artikel aus der Vensoft-Historie.

    Nicht aus dem Bewegungsjournal: dort stehen nur Verkaeufe ab dem Stichtag.
    Die Historie reicht weiter zurueck und ist die bessere Grundlage - aber nur
    ihr juengerer Teil, weil das Geschaeft waechst und aeltere Monate die
    Schwellen zu niedrig ansetzen wuerden.
    """
    import json as _json
    from collections import Counter
    from datetime import timedelta

    from lager import vensoft

    if aus_datei:
        with open(aus_datei, encoding="utf-8") as f:
            gespeichert = _json.load(f)
        stamm, verkaeufe = gespeichert["core"], gespeichert["sales"]
    else:
        stamm = vensoft.stammdaten()
        verkaeufe, _ = vensoft.alle_verkaeufe_ab(0)

    tabelle = vensoft.uebersetzungstabelle(stamm)
    grenze = date.today() - timedelta(days=tage)

    gezaehlt, zeitpunkte = Counter(), []
    for verkauf in verkaeufe:
        if not vensoft.ist_ausgegeben(verkauf, tabelle):
            continue
        zeitpunkt, _ = zeitmodul.lesen((verkauf.get("tstamp") or "")[:19])
        if not zeitpunkt or zeitpunkt.date() < grenze:
            continue
        bezeichnung = tabelle["produkt"].get(verkauf.get("product_id"), "")
        if not bezeichnung or bezeichnung == "Unbekannt":
            continue
        artikel_id, _, _ = zuordnen(lager, "vensoft", bezeichnung)
        if artikel_id:
            gezaehlt[artikel_id] += 1
            zeitpunkte.append(zeitpunkt.date())

    if not zeitpunkte:
        sys.exit("Im gewaehlten Zeitraum keine verwertbaren Verkaeufe gefunden.")

    return ({aid: n / tage for aid, n in gezaehlt.items()},
            (min(zeitpunkte).isoformat(), max(zeitpunkte).isoformat()))


def cmd_mindestbestaende(args):
    """Zeigt Vorschlaege aus dem gemessenen Verbrauch, optional gleich uebernehmen."""
    lager = daten.laden()

    if args.pauschal is not None:
        # Uebergangsloesung, solange kein Verbrauch gemessen wurde: eine
        # einheitliche Schwelle ist grob, aber besser als gar keine Warnung.
        for a in lager.artikel.values():
            if a.aktiv:
                a.mindestbestand = args.pauschal
        _speichern(lager)
        anzahl = len([a for a in lager.artikel.values() if a.aktiv])
        print(f"Mindestbestand fuer {anzahl} Artikel auf {args.pauschal} gesetzt.")
        print("Sobald Verkaufsdaten vorliegen, mit  ./inventur.py mindestbestaende  "
              "aus dem gemessenen Verbrauch ableiten.\n")
        print(bericht.als_text(lager, nur_warnungen=True))
        return

    verbrauch = None
    if args.aus_vensoft or args.aus_datei:
        verbrauch, zeitraum = _verbrauch_aus_vensoft(lager, args.aus_datei, args.tage)
        print(f"Grundlage: Vensoft-Verkaeufe der letzten {args.tage} Tage "
              f"({zeitraum[0]} bis {zeitraum[1]})\n")

    vorschlaege = bericht.mindestbestand_vorschlaege(
        lager, puffer_tage=args.puffer, verbrauch=verbrauch)
    if not vorschlaege:
        print("Noch keine Verkaufsdaten - ohne gemessenen Verbrauch gibt es nichts "
              "abzuleiten. Erst ein paar Wochen Verkaufszahlen einlesen.")
        return

    kopf = f"{'Artikel':<38}{'Verbr./Tag':>11}{'bisher':>8}{'Vorschlag':>11}"
    print(kopf)
    print("-" * len(kopf))
    for v in vorschlaege:
        print(f"{v['name'][:37]:<38}{v['verbrauch_pro_tag']:>11}"
              f"{v['bisher']:>8}{v['vorschlag']:>11}")

    if args.uebernehmen:
        for v in vorschlaege:
            lager.artikel[v["artikel_id"]].mindestbestand = v["vorschlag"]
        _speichern(lager)
        print(f"\n{len(vorschlaege)} Mindestbestaende uebernommen.")
    else:
        print(f"\nDeckt {args.puffer} Tage Verbrauch ab. Uebernehmen mit:")
        print(f"    ./inventur.py mindestbestaende --puffer {args.puffer} --uebernehmen")


def _bericht_erzeugen(lager):
    """Erzeugt die Excel-Datei und liefert Pfad, Mailtext und Datum."""
    os.makedirs(BERICHTE, exist_ok=True)
    stand = date.today()
    pfad = os.path.join(BERICHTE, f"bestandsliste_{stand.isoformat()}.xlsx")
    bericht.als_excel(lager, pfad)

    offene = bericht.warnungen(lager)
    text = (
        f"Bestandsliste vom {stand.strftime('%d.%m.%Y')}\n\n"
        f"{len(offene)} von {len(lager.artikel)} Artikeln brauchen Aufmerksamkeit:\n\n"
        f"{bericht.als_text(lager, nur_warnungen=True)}\n\n"
        "Die vollstaendige Liste haengt als Excel-Datei an.\n"
    )
    return pfad, text, stand


def cmd_mailpaket(args):
    """Schnuert das fertige Versandpaket als JSON.

    Gedacht fuer den Versand aus einer Claude-Routine heraus: die Routine
    muss den Inhalt nicht selbst zusammenbauen, sondern reicht die Felder
    dieser Datei unveraendert an den Gmail-Versand weiter. Die Feldnamen
    entsprechen denen des Gmail-Werkzeugs.
    """
    import base64
    import json

    from lager import marke

    lager = daten.laden()
    pfad, text, stand = _bericht_erzeugen(lager)

    empfaenger = versand.empfaenger_liste(lager)
    if not empfaenger:
        sys.exit("Keine Empfaenger gesetzt. Setzen mit:  ./inventur.py empfaenger a@b.de")

    def kodieren(dateipfad):
        with open(dateipfad, "rb") as f:
            return base64.b64encode(f.read()).decode()

    # Das Logo wird als eingebetteter Anhang mitgeschickt; im HTML verweist
    # cid:logo.png darauf. Der Dateiname bildet die Kennung.
    # CSV statt Excel: der Anhang wird beim automatischen Versand als Text
    # durchgereicht: je kleiner, desto zuverlaessiger kommt er unverfaelscht an.
    # Die formatierte Fassung steht im Mailtext, die Excel-Datei bleibt im
    # Repository fuer alle, die sie brauchen.
    csv_pfad = os.path.join(BERICHTE, f"bestandsliste_{stand.isoformat()}.csv")
    bericht.als_csv(lager, csv_pfad)
    anhaenge = [{
        "filename": f"ProVend_Bestandsliste_{stand.isoformat()}.csv",
        "mimeType": "text/csv",
        "content": kodieren(csv_pfad),
    }]
    logo, _ = marke.logo_fuer_einbettung(240)
    if logo:
        anhaenge.append({
            "filename": "logo.png",
            "mimeType": "image/png",
            "content": kodieren(logo),
            "inline": True,
        })

    paket = {
        "to": empfaenger,
        "subject": f"ProVend Bestandsliste - {stand.strftime('%d.%m.%Y')}",
        "body": text,
        "htmlBody": bericht.als_html(lager, logo_cid="logo.png"),
        "attachments": anhaenge,
    }

    ziel = args.ausgabe or os.path.join(BERICHTE, "versandpaket.json")
    with open(ziel, "w", encoding="utf-8") as f:
        json.dump(paket, f, ensure_ascii=False)

    groesse = os.path.getsize(ziel) / 1024
    print(f"Versandpaket geschrieben: {os.path.relpath(ziel, daten.BASIS)} ({groesse:.0f} KB)")
    print(f"Empfaenger: {', '.join(empfaenger)}")
    print(f"Betreff:    {paket['subject']}")
    print(f"Anhaenge:   {', '.join(a['filename'] for a in anhaenge)}")
    print()
    print(bericht.als_text(lager, nur_warnungen=True))


def _vensoft_daten(aus_datei, still=False):
    """Stammdaten und Verkaeufe - aus einer Datei oder dem Zwischenspeicher.

    Der Zwischenspeicher wird dabei um die neuen Verkaeufe ergaenzt. Ein
    vollstaendiger Abruf der Historie findet nur beim ersten Mal statt.
    """
    import json as _json

    from lager import vensoft

    if aus_datei:
        with open(aus_datei, encoding="utf-8") as f:
            gespeichert = _json.load(f)
        return gespeichert["core"], gespeichert["sales"]

    try:
        stamm, verkaeufe, neue = vensoft.zwischenspeicher_aktualisieren()
    except vensoft.VensoftFehler as fehler:
        sys.exit(f"Abruf fehlgeschlagen: {fehler}")

    if not still:
        print(f"Vensoft: {neue} neue Verkaufsdatensaetze, {len(verkaeufe)} insgesamt")
    return stamm, verkaeufe


def cmd_tagesbericht(args):
    """Taeglicher Umsatzbericht aus den Vensoft-Verkaufsdaten."""
    from datetime import timedelta

    from lager import umsatz, vensoft

    lager = daten.laden()
    stamm, verkaeufe = _vensoft_daten(args.aus_datei)
    tabelle = vensoft.uebersetzungstabelle(stamm)

    if args.datum:
        tag, _ = zeitmodul.lesen(args.datum)
        if tag is None:
            sys.exit(f"Datum nicht lesbar: {args.datum}")
        tag = tag.date()
    else:
        # Standard ist der Vortag: der laufende Tag waere unvollstaendig.
        tag = date.today() - timedelta(days=1)

    def artikelname(bezeichnung):
        artikel_id, _, _ = zuordnen(lager, "vensoft", bezeichnung)
        return lager.artikel[artikel_id].name if artikel_id else bezeichnung

    zahlen = umsatz.tageszahlen(verkaeufe, tabelle, tag, artikelname=artikelname)
    text = umsatz.als_text(zahlen)
    print(text)

    if args.mailpaket:
        import base64
        import json as _json

        empfaenger = versand.empfaenger_liste(lager)
        if not empfaenger:
            sys.exit("Keine Empfaenger gesetzt.")
        logo, _ = marke_logo()
        paket = {
            "to": empfaenger,
            "subject": f"ProVend Tagesbericht - {tag.strftime('%d.%m.%Y')}",
            "body": text,
            "htmlBody": bericht.tagesbericht_html(lager, zahlen),
            "attachments": [],
        }
        if logo:
            with open(logo, "rb") as f:
                paket["attachments"].append({
                    "filename": "logo.png", "mimeType": "image/png", "inline": True,
                    "content": base64.b64encode(f.read()).decode(),
                })
        ziel = args.mailpaket if isinstance(args.mailpaket, str) else os.path.join(
            BERICHTE, "tagespaket.json")
        with open(ziel, "w", encoding="utf-8") as f:
            _json.dump(paket, f, ensure_ascii=False)
        print(f"\nVersandpaket: {os.path.relpath(ziel, daten.BASIS)} "
              f"({os.path.getsize(ziel)/1024:.0f} KB) an {', '.join(empfaenger)}")

    if args.mail:
        _per_smtp(lager, f"ProVend Tagesbericht - {tag.strftime('%d.%m.%Y')}",
                  text, bericht.tagesbericht_html(lager, zahlen))


def _per_smtp(lager, betreff, text, html, anhang=None):
    """Verschickt einen Bericht ueber den hinterlegten Mailzugang.

    Der Weg ueber ein Versandpaket braucht Claude als Boten. Fuer die
    Aufgabenplanung auf dem eigenen Rechner muss das Programm selbst senden
    koennen - sonst laeuft dort nachts niemand, der die Mail abschickt.
    """
    logo, _ = marke_logo()
    try:
        empfaenger = versand.senden(betreff, text, anhang_pfad=anhang, lager=lager,
                                    html=html, logo_pfad=logo, logo_cid="logo.png")
    except Exception as fehler:
        sys.exit(f"Versand fehlgeschlagen: {fehler}")
    print(f"\nE-Mail versendet an: {', '.join(empfaenger)}")


def marke_logo():
    from lager import marke
    return marke.logo_fuer_einbettung(240)


def cmd_monatsbericht(args):
    """Monatsauswertung: dieselben Zahlen wie taeglich, ueber einen Kalendermonat."""
    import base64
    import csv as _csv
    import json as _json

    from lager import umsatz, vensoft

    lager = daten.laden()
    stamm, verkaeufe = _vensoft_daten(args.aus_datei)
    tabelle = vensoft.uebersetzungstabelle(stamm)

    if args.monat:
        try:
            jahr, monat = (int(teil) for teil in args.monat.split("-"))
        except ValueError:
            sys.exit(f"Monat nicht lesbar: {args.monat} (erwartet JJJJ-MM)")
    else:
        # Standard ist der Vormonat - der laufende Monat waere unvollstaendig.
        erster = date.today().replace(day=1)
        vormonat = erster - timedelta(days=1)
        jahr, monat = vormonat.year, vormonat.month

    def artikelname(bezeichnung):
        artikel_id, _, _ = zuordnen(lager, "vensoft", bezeichnung)
        return lager.artikel[artikel_id].name if artikel_id else bezeichnung

    zahlen = umsatz.monatszahlen(verkaeufe, tabelle, jahr, monat, artikelname=artikelname)
    text = umsatz.als_text_monat(zahlen)
    print(text)

    if args.mail:
        _per_smtp(lager,
                  f"ProVend Monatsauswertung - {zahlen['monat_name']} {jahr}",
                  text, bericht.monatsbericht_html(lager, zahlen))

    if not args.mailpaket:
        return

    empfaenger = versand.empfaenger_liste(lager)
    if not empfaenger:
        sys.exit("Keine Empfaenger gesetzt.")

    # Alle verkauften Artikel als CSV - fuer die Buchhaltung und zum Sortieren.
    os.makedirs(BERICHTE, exist_ok=True)
    csv_pfad = os.path.join(BERICHTE, f"umsatz_{jahr}-{monat:02d}.csv")
    with open(csv_pfad, "w", newline="", encoding="utf-8-sig") as f:
        schreiber = _csv.writer(f, delimiter=";")
        schreiber.writerow(["Artikel", "Verkaeufe", "Umsatz EUR"])
        for name, anzahl, betrag in zahlen["je_produkt"]:
            schreiber.writerow([name, anzahl, f"{betrag:.2f}".replace(".", ",")])
        schreiber.writerow([])
        schreiber.writerow(["Gesamt", zahlen["verkaeufe"],
                            f"{zahlen['umsatz']:.2f}".replace(".", ",")])

    anhaenge = [{
        "filename": f"ProVend_Umsatz_{jahr}-{monat:02d}.csv",
        "mimeType": "text/csv",
        "content": base64.b64encode(open(csv_pfad, "rb").read()).decode(),
    }]
    logo, _ = marke_logo()
    if logo:
        with open(logo, "rb") as f:
            anhaenge.append({"filename": "logo.png", "mimeType": "image/png",
                             "inline": True, "content": base64.b64encode(f.read()).decode()})

    paket = {
        "to": empfaenger,
        "subject": f"ProVend Monatsauswertung - {zahlen['monat_name']} {jahr}",
        "body": text,
        "htmlBody": bericht.monatsbericht_html(lager, zahlen),
        "attachments": anhaenge,
    }
    ziel = args.mailpaket if isinstance(args.mailpaket, str) else os.path.join(
        BERICHTE, "monatspaket.json")
    with open(ziel, "w", encoding="utf-8") as f:
        _json.dump(paket, f, ensure_ascii=False)
    print(f"\nVersandpaket: {os.path.relpath(ziel, daten.BASIS)} "
          f"({os.path.getsize(ziel)/1024:.0f} KB) an {', '.join(empfaenger)}")


def cmd_bericht(args):
    lager = daten.laden()
    pfad, text, _ = _bericht_erzeugen(lager)
    print(f"Bericht geschrieben: {os.path.relpath(pfad, daten.BASIS)}")
    print()
    print(text)

    if args.mail:
        from lager import marke
        logo, _ = marke.logo_fuer_einbettung(240)
        empfaenger = versand.senden(
            f"ProVend Bestandsliste - {date.today().strftime('%d.%m.%Y')}",
            text, pfad, lager=lager,
            html=bericht.als_html(lager), logo_pfad=logo,
        )
        print(f"E-Mail versendet an: {', '.join(empfaenger)}")


def cmd_sortiment(args):
    """Sortimentsauswertung: Renner, Schwachdreher, tote Schaechte."""
    from lager import sortiment as sortiment_modul
    from lager import vensoft

    lager = daten.laden()
    stamm, verkaeufe = _vensoft_daten(args.aus_datei, still=True)
    tabelle = vensoft.uebersetzungstabelle(stamm)

    def artikel_id_zu(bezeichnung):
        artikel_id, _, _ = zuordnen(lager, "vensoft", bezeichnung)
        return artikel_id

    zahlen = sortiment_modul.zahlen(verkaeufe, tabelle, lager, artikel_id_zu,
                                    tage=args.tage)
    print(sortiment_modul.als_text(zahlen))

    if args.csv:
        pfad = args.csv if isinstance(args.csv, str) else "berichte/sortiment.csv"
        os.makedirs(os.path.dirname(pfad) or ".", exist_ok=True)
        with open(pfad, "w", encoding="utf-8-sig", newline="") as f:
            f.write(sortiment_modul.als_csv(zahlen))
        print(f"\nCSV geschrieben: {pfad}")


def cmd_prospekte(args):
    """Ordner mit dem aktuellen Ordersatz anzeigen oder setzen."""
    lager = daten.laden()
    if not args.pfad:
        pfad = lager.einstellungen.get("prospekte_ordner", "")
        if not pfad:
            print("Kein Prospektordner hinterlegt.")
            print('Setzen mit: inventur.py prospekte "C:\\Users\\...\\OneDrive\\60_Prospekte"')
        else:
            print(pfad)
            # Der Ordner liegt in OneDrive und kann auf einem anderen Rechner
            # fehlen - das soll auffallen, bevor die Montagsroutine daran
            # scheitert.
            if not os.path.isdir(pfad):
                print("ACHTUNG: Dieser Ordner ist von hier aus nicht erreichbar.")
        return

    pfad = args.pfad.rstrip("\\/")
    if not os.path.isdir(pfad):
        sys.exit(f"Kein Ordner: {pfad}")
    lager.einstellungen["prospekte_ordner"] = pfad
    daten.einstellungen_speichern(lager)
    dateien = sorted(os.listdir(pfad))
    print(f"Prospektordner gesetzt: {pfad}")
    print(f"{len(dateien)} Datei(en) darin"
          + (": " + ", ".join(dateien[:6]) if dateien else ""))


def cmd_zugang(args):
    """Zeigt, woher die Zugangsdaten kommen - ohne sie preiszugeben."""
    gefunden = [p for p in _env_dateien() if os.path.exists(p)]
    if gefunden:
        print("Gelesene Datei(en), wichtigste zuerst:")
        for pfad in gefunden:
            hinweis = "   <- heisst .txt, funktioniert trotzdem" \
                if pfad.endswith(".txt") else ""
            print(f"  {pfad}{hinweis}")
    else:
        print("Keine Zugangsdatei gefunden. Gesucht wurde in:")
        for pfad in _env_dateien():
            print(f"  {pfad}")

    print()
    for schluessel, zweck in (("VENSOFT_USER", "Vensoft-Benutzer"),
                              ("VENSOFT_PASS", "Vensoft-Passwort"),
                              ("MAIL_ABSENDER", "Absender der Berichte"),
                              ("MAIL_PASSWORT", "App-Passwort fuer den Versand")):
        wert = os.environ.get(schluessel, "")
        if not wert:
            stand = "FEHLT"
        elif "PASS" in schluessel or "PASSWORT" in schluessel:
            # Nur Laenge zeigen: genug, um einen Tippfehler zu bemerken,
            # zu wenig, um das Passwort zu verraten.
            stand = f"gesetzt ({len(wert)} Zeichen)"
        else:
            stand = wert
        # Lange Werte wie die Absenderadresse liefen sonst in die Spalte
        # daneben, und die Ausgabe klebte zusammen.
        if len(stand) > 30:
            stand = stand[:29] + "\u2026"
        print(f"  {schluessel:<16}{stand:<32}{zweck}")

    fehlt = [k for k in ("VENSOFT_USER", "VENSOFT_PASS") if not os.environ.get(k)]
    if fehlt:
        print("\nOhne VENSOFT_USER und VENSOFT_PASS koennen keine Verkaufsdaten "
              "abgerufen werden.")

    if not args.mailtest:
        return
    print("\nMelde mich beim Mailserver an (es wird nichts verschickt) ...")
    try:
        absender, host = versand.anmeldung_pruefen()
    except Exception as fehler:
        text = str(fehler)
        print(f"Anmeldung fehlgeschlagen: {text}")
        if "535" in text or "Username and Password not accepted" in text:
            print("Das ist die uebliche Meldung bei einem falschen App-Passwort.")
            print("Bei Gmail: 16 Zeichen, keine Leerzeichen, aus")
            print("https://myaccount.google.com/apppasswords")
        sys.exit(1)
    print(f"Anmeldung erfolgreich: {absender} bei {host}")


def main():
    p = argparse.ArgumentParser(description="Lagerverwaltung Verkaufsautomaten")
    unter = p.add_subparsers(dest="befehl", required=True)

    a = unter.add_parser("anfangsbestand", help="Lager-Excel einlesen und als Anfangsbestand buchen")
    a.add_argument("datei")
    a.add_argument("--datum", help="Stichtag der Inventur (Standard: heute)")
    a.add_argument("--blatt", help="Name des Tabellenblatts")
    a.add_argument("--mengenspalte", choices=("gesamt", "lager"), default="gesamt",
                   help="gesamt = Lager plus Automaten (Standard), lager = nur das Lager")
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

    vs = unter.add_parser("vensoft", help="Verkaeufe aus der Vensoft-Schnittstelle abrufen und buchen")
    vs.add_argument("--aus-datei", dest="aus_datei",
                    help="Statt abzurufen aus einer gespeicherten JSON-Datei lesen "
                         "(Schluessel 'core' und 'sales')")
    vs.set_defaults(func=cmd_vensoft)

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

    em = unter.add_parser("empfaenger",
                          help="Empfaenger der Bestandsliste anzeigen oder setzen")
    em.add_argument("adressen", nargs="*", help="E-Mail-Adressen; ohne Angabe wird angezeigt")
    em.set_defaults(func=cmd_empfaenger)

    st = unter.add_parser("stichtag",
                          help="Zeitpunkt setzen, ab dem Verkaeufe gebucht werden")
    st.add_argument("zeitpunkt", nargs="?", help="z.B. 2026-09-06T15:00; ohne Angabe wird angezeigt")
    st.set_defaults(func=cmd_stichtag)

    m = unter.add_parser("mindestbestaende",
                         help="Mindestbestaende aus dem gemessenen Verbrauch vorschlagen")
    m.add_argument("--puffer", type=int, default=14,
                   help="Wie viele Tage Verbrauch die Schwelle abdecken soll (Standard 14)")
    m.add_argument("--uebernehmen", action="store_true", help="Vorschlaege in den Artikelstamm schreiben")
    m.add_argument("--aus-vensoft", dest="aus_vensoft", action="store_true",
                   help="Verbrauch aus der Vensoft-Historie statt aus dem Journal")
    m.add_argument("--aus-datei", dest="aus_datei",
                   help="Vensoft-Daten aus einer gespeicherten JSON-Datei lesen")
    m.add_argument("--tage", type=int, default=60,
                   help="Wie weit die Verbrauchsmessung zurueckreicht (Standard 60)")
    m.add_argument("--pauschal", type=int, metavar="N",
                   help="Uebergangsweise fuer alle Artikel dieselbe Schwelle setzen")
    m.set_defaults(func=cmd_mindestbestaende)

    mp = unter.add_parser("mailpaket",
                          help="Versandfertiges JSON erzeugen (fuer den Versand aus einer Routine)")
    mp.add_argument("--ausgabe", help="Zieldatei (Standard: berichte/versandpaket.json)")
    mp.set_defaults(func=cmd_mailpaket)

    tb = unter.add_parser("tagesbericht", help="Taeglicher Umsatzbericht aus den Verkaufsdaten")
    tb.add_argument("--datum", help="Auszuwertender Tag (Standard: gestern)")
    tb.add_argument("--aus-datei", dest="aus_datei", help="Vensoft-Daten aus einer JSON-Datei")
    tb.add_argument("--mailpaket", nargs="?", const=True, default=False,
                    help="Versandfertiges JSON schreiben (optional mit Pfad)")
    tb.add_argument("--mail", action="store_true",
                    help="Bericht selbst per SMTP versenden (fuer die Aufgabenplanung)")
    tb.set_defaults(func=cmd_tagesbericht)

    mb = unter.add_parser("monatsbericht", help="Monatsauswertung des Vormonats")
    mb.add_argument("--monat", help="Auszuwertender Monat als JJJJ-MM (Standard: Vormonat)")
    mb.add_argument("--aus-datei", dest="aus_datei", help="Vensoft-Daten aus einer JSON-Datei")
    mb.add_argument("--mailpaket", nargs="?", const=True, default=False,
                    help="Versandfertiges JSON schreiben (optional mit Pfad)")
    mb.add_argument("--mail", action="store_true",
                    help="Bericht selbst per SMTP versenden (fuer die Aufgabenplanung)")
    mb.set_defaults(func=cmd_monatsbericht)

    so = unter.add_parser("sortiment",
                          help="Renner und Ladenhueter je Artikel und je Schacht")
    so.add_argument("--tage", type=int, default=90, help="Zeitfenster in Tagen (Standard: 90)")
    so.add_argument("--aus-datei", dest="aus_datei", help="Vensoft-Daten aus einer JSON-Datei")
    so.add_argument("--csv", nargs="?", const=True, default=False,
                    help="Auswertung als CSV schreiben (optional mit Pfad)")
    so.set_defaults(func=cmd_sortiment)

    pr = unter.add_parser("prospekte",
                          help="Ordner mit dem aktuellen Ordersatz anzeigen oder setzen")
    pr.add_argument("pfad", nargs="?",
                    help="Pfad zum Prospektordner; ohne Angabe wird der hinterlegte gezeigt")
    pr.set_defaults(func=cmd_prospekte)

    zg = unter.add_parser("zugang",
                          help="Pruefen, ob die Zugangsdaten gefunden werden")
    zg.add_argument("--mailtest", action="store_true",
                    help="zusaetzlich beim Mailserver anmelden, ohne etwas zu senden")
    zg.set_defaults(func=cmd_zugang)

    b = unter.add_parser("bericht", help="Excel-Bestandsliste erzeugen, optional per Mail")
    b.add_argument("--mail", action="store_true", help="Bericht an die hinterlegten Empfaenger senden")
    b.set_defaults(func=cmd_bericht)

    args = p.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
