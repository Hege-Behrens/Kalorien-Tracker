"""Importe: Anfangsbestand aus Excel, Einkaeufe aus Rechnungen, Verkaeufe aus dem Automatensystem."""

import csv
import os

from .daten import Artikel, Bewegung, heute, normalisieren
from .zuordnung import alias_lernen, sammelregel_treffer, zuordnen

# Kopfzeilen sind in der Praxis nie einheitlich benannt. Deshalb suchen wir
# nach Stichworten statt nach exakten Spaltennamen.
SPALTEN_SCHLUESSEL = {
    "name": ["artikel", "bezeichnung", "produkt", "ware", "name"],
    "bestand": ["bestand", "menge", "anzahl", "stueck", "stück", "ist"],
    "mindestbestand": ["mindest", "meldebestand", "soll", "minimum"],
    "gebinde": ["gebinde", "vpe", "verpackung", "karton", "kiste"],
    "kategorie": ["kategorie", "gruppe", "warengruppe"],
    "lieferant": ["lieferant", "quelle", "händler", "haendler"],
    "ean": ["ean", "barcode", "gtin"],
}


def _spalte_finden(kopf, schluesselwoerter):
    for i, zelle in enumerate(kopf):
        text = str(zelle or "").strip().lower()
        for wort in schluesselwoerter:
            if wort in text:
                return i
    return None


def _zahl(wert, standard=0):
    if wert is None or str(wert).strip() == "":
        return standard
    try:
        return int(round(float(str(wert).replace(",", ".").strip())))
    except ValueError:
        return standard


def anfangsbestand_aus_excel(lager, pfad, datum=None, blatt=None):
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
        if _spalte_finden(zeile, SPALTEN_SCHLUESSEL["name"]) is not None:
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

    protokoll = {"neu": 0, "aktualisiert": 0, "zusammengefasst": 0, "uebersprungen": 0}

    for zeile in zeilen[kopf_index + 1:]:
        def hole(feld):
            i = idx.get(feld)
            return zeile[i] if i is not None and i < len(zeile) else None

        name = str(hole("name") or "").strip()
        if not name:
            protokoll["uebersprungen"] += 1
            continue

        menge = _zahl(hole("bestand"))
        gebinde = _zahl(hole("gebinde"), 1) or 1
        mindest = _zahl(hole("mindestbestand"))
        kategorie = str(hole("kategorie") or "").strip()
        lieferant = str(hole("lieferant") or "").strip()
        ean = str(hole("ean") or "").strip()

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
                protokoll["aktualisiert"] += 1

        if vorhanden:
            artikel_id = vorhanden.artikel_id
        else:
            artikel_id = lager.naechste_artikel_id(name)
            lager.artikel[artikel_id] = Artikel(
                artikel_id=artikel_id,
                name=name,
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


def belege_buchen(lager, pfad, typ, quelle_standard="", automatisch_anlegen=False):
    """Bucht Rechnungs- oder Verkaufszeilen aus einer CSV.

    Erwartete Spalten (Reihenfolge egal, Benennung tolerant):
      datum, bezeichnung, menge, einheit (stueck|gebinde), beleg, quelle, ean

    Zeilen, deren Artikel nicht sicher zugeordnet werden kann, werden NICHT
    gebucht, sondern in data/offene_zuordnungen.csv gesammelt.
    """
    gebucht, offen, dubletten = [], [], 0
    bekannte_positionen = lager.positionen()

    for zeile in _belegzeilen_lesen(pfad):
        bezeichnung = _feld(zeile, "bezeichnung", "artikel", "produkt", "name")
        if not bezeichnung:
            continue

        menge = _zahl(_feld(zeile, "menge", "anzahl", "stueck", "stück"))
        if menge <= 0:
            continue

        datum = _feld(zeile, "datum") or heute()
        beleg = _feld(zeile, "beleg", "rechnung", "bon", "nummer")
        quelle = (_feld(zeile, "quelle", "lieferant", "markt") or quelle_standard).lower()
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
                })
                continue

        # Einkauf kann in Gebinden geliefert werden - Bestand fuehren wir in Stueck.
        stueck = menge
        artikel = lager.artikel[artikel_id]
        if einheit.startswith("gebinde") or einheit in ("kiste", "karton", "vpe"):
            stueck = menge * max(1, artikel.stueck_pro_gebinde)

        lager.buchen(Bewegung(
            datum=datum, typ=typ, artikel_id=artikel_id, menge=stueck,
            beleg=beleg, bezeichnung=bezeichnung, quelle=quelle, notiz=methode,
        ))
        gebucht.append((artikel.name, stueck))

    return {"gebucht": gebucht, "offen": offen, "dubletten": dubletten}


OFFEN_FELDER = ["datum", "quelle", "bezeichnung", "menge", "einheit",
                "beleg", "ean", "vorschlag", "guete"]


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
