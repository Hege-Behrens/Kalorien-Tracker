"""Importe: Anfangsbestand aus Excel, Einkaeufe aus Rechnungen, Verkaeufe aus dem Automatensystem."""

import csv
import os

from . import zeit as zeitmodul
from .daten import Artikel, Bewegung, heute, normalisieren
from .zuordnung import alias_lernen, sammelregel_treffer, zuordnen

# Kopfzeilen sind in der Praxis nie einheitlich benannt. Deshalb suchen wir
# nach Stichworten statt nach exakten Spaltennamen.
SPALTEN_SCHLUESSEL = {
    "name": ["artikel", "bezeichnung", "produkt", "ware", "name"],
    "bestand": ["bestand", "menge", "anzahl", "stueck", "stück", "ist"],
    "gesamt": ["gesamt", "summe", "total"],
    "lager": ["menge lager", "lager"],
    "nummer": ["nr.", "nr ", "nummer", "artikelnr"],
    "selektor": ["selektor", "schacht", "slot"],
    "mindestbestand": ["mindest", "meldebestand", "soll", "minimum"],
    "gebinde": ["gebinde", "vpe", "verpackung", "karton", "kiste"],
    "kategorie": ["kategorie", "gruppe", "warengruppe"],
    "lieferant": ["lieferant", "quelle", "händler", "haendler"],
    "ean": ["ean", "barcode", "gtin"],
}


# Ein Spaltenkopf ist kurz. Laengere Zellen sind Ueberschriften oder
# Erklaertexte - die duerfen nicht als Kopfzeile durchgehen, sonst wird eine
# Zeile wie "Produkte ohne Selektor sind nicht im Automaten" zur Kopfzeile.
MAX_KOPF_LAENGE = 40


def _spalte_finden(kopf, schluesselwoerter):
    for i, zelle in enumerate(kopf):
        text = str(zelle or "").strip().lower()
        if not text or len(text) > MAX_KOPF_LAENGE:
            continue
        for wort in schluesselwoerter:
            if wort in text:
                return i
    return None


def _ist_kopfzeile(zeile):
    """Eine Kopfzeile hat eine Artikelspalte und mehrere kurze Beschriftungen."""
    if _spalte_finden(zeile, SPALTEN_SCHLUESSEL["name"]) is None:
        return False
    kurze = [z for z in zeile
             if z is not None and 0 < len(str(z).strip()) <= MAX_KOPF_LAENGE]
    return len(kurze) >= 2


def _zahl(wert, standard=0):
    if wert is None or str(wert).strip() == "":
        return standard
    try:
        return int(round(float(str(wert).replace(",", ".").strip())))
    except ValueError:
        return standard


def anfangsbestand_aus_excel(lager, pfad, datum=None, blatt=None, mengenspalte="gesamt"):
    """Liest die Lager-Excel ein und bucht sie als ANFANGSBESTAND.

    Erkennt die Kopfzeile selbst, damit die Datei nicht vorher aufbereitet
    werden muss. Bereits vorhandene Artikel werden aktualisiert, nicht doppelt
    angelegt.
    """
    import openpyxl

    datum = datum or heute()
    mappe = openpyxl.load_workbook(pfad, data_only=True)
    blatt_obj = mappe[blatt] if blatt else mappe.worksheets[0]
    zeilen = [list(r) for r in blatt_obj.iter_rows(values_only=True)]

    # Kopfzeile = erste Zeile, in der eine Artikelspalte erkennbar ist.
    kopf_index = None
    for i, zeile in enumerate(zeilen[:20]):
        if _ist_kopfzeile(zeile):
            kopf_index = i
            break
    if kopf_index is None:
        raise ValueError(
            "In der Datei wurde keine Spalte mit Artikelbezeichnungen gefunden. "
            "Erwartet wird eine Spalte mit 'Artikel', 'Bezeichnung' oder 'Produkt' im Namen."
        )

    kopf = zeilen[kopf_index]
    idx = {feld: _spalte_finden(kopf, worte) for feld, worte in SPALTEN_SCHLUESSEL.items()}
    if idx["name"] is None:
        raise ValueError("Keine Artikelspalte erkannt.")

    # Welche Spalte den Bestand liefert, haengt davon ab, was gefuehrt werden
    # soll: der Gesamtbestand ueber Lager und Automaten, oder nur das Lager.
    if mengenspalte == "gesamt":
        idx["bestand"] = idx["gesamt"] or idx["lager"] or idx["bestand"]
    elif mengenspalte == "lager":
        idx["bestand"] = idx["lager"] or idx["bestand"]
    if idx["bestand"] is None:
        raise ValueError("Keine Mengenspalte erkannt.")

    protokoll = {"neu": 0, "aktualisiert": 0, "zusammengefasst": 0, "uebersprungen": 0}

    for zeile in zeilen[kopf_index + 1:]:
        def hole(feld):
            i = idx.get(feld)
            return zeile[i] if i is not None and i < len(zeile) else None

        name = str(hole("name") or "").strip()
        if not name:
            protokoll["uebersprungen"] += 1
            continue

        # Summenzeilen am Tabellenende sind keine Artikel.
        if normalisieren(name).split(" ")[0] in ("GESAMT", "SUMME", "TOTAL"):
            protokoll["uebersprungen"] += 1
            continue

        menge = _zahl(hole("bestand"))
        gebinde = _zahl(hole("gebinde"), 1) or 1
        mindest = _zahl(hole("mindestbestand"))
        kategorie = str(hole("kategorie") or "").strip()
        lieferant = str(hole("lieferant") or "").strip()
        ean = str(hole("ean") or "").strip()
        nummer = str(hole("nummer") or "").strip().rstrip(".0") if hole("nummer") else ""
        selektor = str(hole("selektor") or "").strip()

        # Faellt die Zeile unter einen Sammelartikel? Dann wird sie dorthin
        # gebucht, statt eine eigene Sorte anzulegen. Mehrere Sortenzeilen
        # addieren sich so zu einem Bestand.
        regel = sammelregel_treffer(lager, name)
        vorhanden = None
        if regel:
            vorhanden = lager.artikel[regel.artikel_id]
            # Beim Sammelartikel gilt der groesste genannte Mindestbestand,
            # sonst wuerde die letzte Sortenzeile die vorigen ueberschreiben.
            vorhanden.mindestbestand = max(vorhanden.mindestbestand, mindest)
            if gebinde > 1:
                vorhanden.stueck_pro_gebinde = gebinde
            if kategorie and not vorhanden.kategorie:
                vorhanden.kategorie = kategorie
            if selektor and not vorhanden.selektor:
                vorhanden.selektor = selektor
            protokoll["zusammengefasst"] += 1
        else:
            norm = normalisieren(name)
            for a in lager.artikel.values():
                if normalisieren(a.name) == norm or (ean and a.ean == ean):
                    vorhanden = a
                    break
            if vorhanden:
                vorhanden.mindestbestand = mindest or vorhanden.mindestbestand
                vorhanden.stueck_pro_gebinde = gebinde or vorhanden.stueck_pro_gebinde
                vorhanden.nummer = nummer or vorhanden.nummer
                vorhanden.selektor = selektor or vorhanden.selektor
                protokoll["aktualisiert"] += 1

        if vorhanden:
            artikel_id = vorhanden.artikel_id
        else:
            artikel_id = lager.naechste_artikel_id(name)
            lager.artikel[artikel_id] = Artikel(
                artikel_id=artikel_id,
                name=name,
                nummer=nummer,
                selektor=selektor,
                kategorie=kategorie,
                stueck_pro_gebinde=gebinde,
                mindestbestand=mindest,
                lieferant=lieferant,
                ean=ean,
            )
            protokoll["neu"] += 1

        if menge:
            lager.buchen(Bewegung(
                datum=datum,
                typ="ANFANGSBESTAND",
                artikel_id=artikel_id,
                menge=menge,
                beleg=f"inventur-{datum}",
                bezeichnung=name,
                quelle="inventur",
                notiz=os.path.basename(pfad),
            ))

    return protokoll


def _belegzeilen_lesen(pfad):
    """Liest eine Beleg-CSV (Rechnung oder Verkaufsexport) ein."""
    with open(pfad, newline="", encoding="utf-8-sig") as f:
        # Trennzeichen automatisch erkennen - Exporte kommen mal mit ; mal mit ,
        probe = f.read(4096)
        f.seek(0)
        try:
            dialekt = csv.Sniffer().sniff(probe, delimiters=";,\t")
        except csv.Error:
            dialekt = csv.excel
            dialekt.delimiter = ";"
        return list(csv.DictReader(f, dialect=dialekt))


def _feld(zeile, *namen):
    for name in namen:
        for schluessel, wert in zeile.items():
            if schluessel and name in schluessel.strip().lower():
                return str(wert or "").strip()
    return ""


def _stichtag(lager, typ):
    """Zeitpunkt, ab dem Verkaeufe gebucht werden duerfen.

    Alles davor steckt bereits im Anfangsbestand und wuerde doppelt abgezogen.
    """
    if typ != "VERKAUF":
        return None
    zeitpunkt, _ = zeitmodul.lesen(lager.einstellungen.get("verkauf_ab", ""))
    return zeitpunkt


def _positionskennung(zeile, quelle, bezeichnung, zeitpunkt, zaehler):
    """Stabile Kennung einer Verkaufszeile, wenn der Export keine Belegnummer hat.

    Verkaufsexporte tragen selten eine Belegnummer, ueberlappen sich aber
    haeufig (der Export der zweiten Woche enthaelt oft noch die erste). Ohne
    Kennung wuerde jede Ueberlappung doppelt abgebucht. Die Kennung aus
    Zeitpunkt, Quelle und Automat ist bei erneutem Export identisch - dieselbe
    Zeile wird also wiedererkannt.
    """
    transaktion = _feld(zeile, "transaktion", "vorgang", "transaction")
    if transaktion:
        return f"verkauf:{transaktion}"

    automat = _feld(zeile, "automat", "geraet", "gerät", "maschine", "standort")

    stempel = zeitpunkt.isoformat() if zeitpunkt else "ohne-zeit"
    basis = f"verkauf:{quelle}:{automat}:{stempel}:{normalisieren(bezeichnung)}"
    # Mehrere gleiche Zeilen in derselben Datei bekommen eine laufende Nummer,
    # damit sie sich nicht gegenseitig als Dublette ausloeschen.
    zaehler[basis] = zaehler.get(basis, 0) + 1
    return f"{basis}#{zaehler[basis]}"


def belege_buchen(lager, pfad, typ, quelle_standard="", automatisch_anlegen=False):
    """Bucht Rechnungs- oder Verkaufszeilen aus einer CSV.

    Erwartete Spalten (Reihenfolge egal, Benennung tolerant):
      datum, uhrzeit, bezeichnung, menge, einheit (stueck|gebinde), beleg,
      quelle, ean, automat, transaktion

    Zeilen, deren Artikel nicht sicher zugeordnet werden kann, werden NICHT
    gebucht, sondern in data/offene_zuordnungen.csv gesammelt.
    """
    gebucht, offen, dubletten = [], [], 0
    vor_stichtag, ohne_zeit = 0, []
    bekannte_positionen = lager.positionen()
    stichtag = _stichtag(lager, typ)
    zaehler = {}

    for zeile in _belegzeilen_lesen(pfad):
        bezeichnung = _feld(zeile, "bezeichnung", "artikel", "produkt", "name")
        if not bezeichnung:
            continue

        menge = _zahl(_feld(zeile, "menge", "anzahl", "stueck", "stück",
                            "verkauf", "verkäuf", "absatz"))
        if menge <= 0:
            continue

        zeitpunkt, hat_uhrzeit = zeitmodul.zusammensetzen(
            _feld(zeile, "datum", "zeitpunkt", "zeitstempel", "timestamp"),
            _feld(zeile, "uhrzeit", "zeit"),
        )
        datum = zeitpunkt.date().isoformat() if zeitpunkt else (_feld(zeile, "datum") or heute())

        if stichtag:
            if zeitpunkt is None:
                # Ohne Datum laesst sich der Stichtag nicht anwenden.
                ohne_zeit.append(bezeichnung)
                continue
            if hat_uhrzeit:
                if zeitpunkt < stichtag:
                    vor_stichtag += 1
                    continue
            elif zeitpunkt.date() < stichtag.date():
                vor_stichtag += 1
                continue
            elif zeitpunkt.date() == stichtag.date():
                # Tagesgenaue Zeile am Stichtag selbst: ein Teil davon liegt vor
                # 15 Uhr und steckt schon im Bestand. Nicht raten - vorlegen.
                ohne_zeit.append(bezeichnung)
                continue

        quelle = (_feld(zeile, "quelle", "lieferant", "markt") or quelle_standard).lower()
        beleg = _feld(zeile, "beleg", "rechnung", "bon", "belegnummer")
        if not beleg and typ == "VERKAUF":
            beleg = _positionskennung(zeile, quelle, bezeichnung, zeitpunkt, zaehler)
        ean = _feld(zeile, "ean", "barcode", "gtin")
        einheit = _feld(zeile, "einheit", "vpe").lower()

        if beleg and (beleg, normalisieren(bezeichnung)) in bekannte_positionen:
            dubletten += 1
            continue

        artikel_id, guete, methode = zuordnen(lager, quelle, bezeichnung, ean)

        if artikel_id is None:
            if automatisch_anlegen:
                artikel_id = lager.naechste_artikel_id(bezeichnung)
                lager.artikel[artikel_id] = Artikel(artikel_id=artikel_id, name=bezeichnung, ean=ean)
                alias_lernen(lager, quelle, bezeichnung, artikel_id)
                methode = "neu angelegt"
            else:
                offen.append({
                    "datum": datum, "quelle": quelle, "bezeichnung": bezeichnung,
                    "menge": menge, "einheit": einheit or "stueck", "beleg": beleg,
                    "ean": ean, "vorschlag": "", "guete": f"{guete:.2f}",
                    "hinweis": "kein passender Artikel gefunden",
                })
                continue

        # Einkauf kann in Gebinden geliefert werden - Bestand fuehren wir in Stueck.
        stueck = menge
        artikel = lager.artikel[artikel_id]
        in_gebinden = einheit.startswith("gebinde") or einheit in ("kiste", "karton", "vpe")
        if in_gebinden:
            if artikel.stueck_pro_gebinde <= 1:
                # Ohne Gebindegroesse waeren "5 Kisten" faelschlich 5 Stueck.
                # Lieber zurueckstellen als den Bestand um Faktor 24 verfehlen.
                offen.append({
                    "datum": datum, "quelle": quelle, "bezeichnung": bezeichnung,
                    "menge": menge, "einheit": einheit, "beleg": beleg, "ean": ean,
                    "vorschlag": artikel_id, "guete": "1.00",
                    "hinweis": f"Gebindegroesse fehlt - stueck_pro_gebinde fuer "
                               f"'{artikel.name}' in data/artikel.csv eintragen",
                })
                continue
            stueck = menge * artikel.stueck_pro_gebinde

        lager.buchen(Bewegung(
            datum=datum, typ=typ, artikel_id=artikel_id, menge=stueck,
            beleg=beleg, bezeichnung=bezeichnung, quelle=quelle, notiz=methode,
        ))
        gebucht.append((artikel.name, stueck))

    return {"gebucht": gebucht, "offen": offen, "dubletten": dubletten,
            "vor_stichtag": vor_stichtag, "ohne_zeit": ohne_zeit}


OFFEN_FELDER = ["datum", "quelle", "bezeichnung", "menge", "einheit",
                "beleg", "ean", "vorschlag", "guete", "hinweis"]


def offene_schreiben(offen, pfad):
    if not offen:
        if os.path.exists(pfad):
            os.remove(pfad)
        return
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=OFFEN_FELDER)
        w.writeheader()
        w.writerows(offen)


def offene_lesen(pfad):
    if not os.path.exists(pfad):
        return []
    with open(pfad, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def offene_aktualisieren(lager, neue_offene, pfad):
    """Schreibt die Offen-Liste neu: alte Eintraege, die inzwischen gebucht
    wurden, fallen raus; neue kommen dazu, ohne Dubletten.

    Ohne diesen Abgleich blieben Positionen stehen, die laengst im Journal
    stehen - etwa weil sie beim zweiten Lauf als neuer Artikel angelegt wurden.
    """
    gebuchte = lager.positionen()

    def kennung(z):
        return (z.get("beleg", ""), normalisieren(z.get("bezeichnung", "")))

    ergebnis, gesehen = [], set()
    for zeile in offene_lesen(pfad) + list(neue_offene):
        k = kennung(zeile)
        if k in gebuchte or k in gesehen:
            continue
        gesehen.add(k)
        ergebnis.append({feld: zeile.get(feld, "") for feld in OFFEN_FELDER})

    offene_schreiben(ergebnis, pfad)
    return ergebnis
