"""Tageszahlen aus den Vensoft-Verkaufsdaten.

Anders als der Bestand kommt der Umsatz nicht aus dem Bewegungsjournal: dort
stehen nur Mengen. Die Preise liefert die Schnittstelle.
"""

from collections import Counter, defaultdict
from datetime import date, timedelta

from . import vensoft


def _tag(verkauf):
    stempel = (verkauf.get("tstamp") or "")[:10]
    try:
        return date.fromisoformat(stempel)
    except ValueError:
        return None


def euro(betrag):
    """Betrag in deutscher Schreibweise: 1.234,50"""
    return f"{betrag:,.2f}".replace(",", "#").replace(".", ",").replace("#", ".")


def zahl(wert, stellen=1):
    return f"{wert:.{stellen}f}".replace(".", ",")


WOCHENTAGE = ("Montag", "Dienstag", "Mittwoch", "Donnerstag",
              "Freitag", "Samstag", "Sonntag")


def tageszahlen(verkaeufe, tabelle, stichtag, rueckblick=7, artikelname=None):
    """Kennzahlen fuer einen Tag, mit Vergleich zu Vortag und Rueckblick.

    stichtag ist der auszuwertende Tag. Der Rueckblick endet am Vortag, damit
    der Vergleich nicht den Berichtstag selbst enthaelt.

    artikelname uebersetzt die Vensoft-Produktbezeichnung in euren
    Artikelnamen. Ohne diese Uebersetzung stuenden falsch beschriftete
    Schaechte auch im Bericht unter dem falschen Namen.
    """
    benenne = artikelname or (lambda name: name)
    ausgegeben = [v for v in verkaeufe if vensoft.ist_ausgegeben(v, tabelle)]

    def summe(menge):
        return sum(vensoft.betrag(v) for v in menge)

    des_tages = [v for v in ausgegeben if _tag(v) == stichtag]
    vortag = [v for v in ausgegeben if _tag(v) == stichtag - timedelta(days=1)]
    fenster = [v for v in ausgegeben
               if stichtag - timedelta(days=rueckblick) <= (_tag(v) or date.min) < stichtag]

    je_standort = defaultdict(lambda: [0, 0.0])
    for v in des_tages:
        name = tabelle.get("ort_je_automat", {}).get(v.get("parent_id")) \
            or tabelle["automat"].get(v.get("parent_id"), "unbekannt")
        je_standort[name][0] += 1
        je_standort[name][1] += vensoft.betrag(v)

    je_produkt = defaultdict(lambda: [0, 0.0])
    for v in des_tages:
        name = benenne(tabelle["produkt"].get(v.get("product_id"), "unbekannt"))
        je_produkt[name][0] += 1
        je_produkt[name][1] += vensoft.betrag(v)

    # Fehlversuche desselben Tages: leerer Schacht, Stoerung, Abbruch. Sie
    # gehoeren nicht in den Umsatz, sagen aber etwas ueber den Zustand der
    # Automaten - drei Stoerungen an einem Tag sind ein Hinweis.
    stoerungen = Counter()
    for v in verkaeufe:
        if _tag(v) == stichtag and not vensoft.ist_ausgegeben(v, tabelle):
            art = tabelle["status"].get(v.get("sale_status_id"), "?")
            stoerungen[art.replace("sale_status_", "")] += 1

    return {
        "datum": stichtag,
        "verkaeufe": len(des_tages),
        "umsatz": summe(des_tages),
        "pfand": sum(float(v.get("pledge") or 0) for v in des_tages),
        "vortag_verkaeufe": len(vortag),
        "vortag_umsatz": summe(vortag),
        "schnitt_verkaeufe": len(fenster) / rueckblick if fenster else 0.0,
        "schnitt_umsatz": summe(fenster) / rueckblick if fenster else 0.0,
        "rueckblick": rueckblick,
        "je_standort": sorted(((n, z[0], z[1]) for n, z in je_standort.items()),
                              key=lambda x: -x[2]),
        "je_produkt": sorted(((n, z[0], z[1]) for n, z in je_produkt.items()),
                             key=lambda x: (-x[1], -x[2])),
        "stoerungen": dict(stoerungen),
    }


def als_text(zahlen):
    d = zahlen

    def pfeil(jetzt, vorher):
        if not vorher:
            return ""
        anteil = (jetzt - vorher) / vorher * 100
        if abs(anteil) < 0.5:
            return "  (unveraendert zum Vortag)"
        return f"  ({anteil:+.0f} % zum Vortag)"

    zeilen = [
        f"ProVend Tagesbericht - {WOCHENTAGE[d['datum'].weekday()]}, "
        f"{d['datum'].strftime('%d.%m.%Y')}",
        "",
        f"Umsatz          {euro(d['umsatz']):>8} EUR{pfeil(d['umsatz'], d['vortag_umsatz'])}",
        f"Verkaeufe       {d['verkaeufe']:>8}{pfeil(d['verkaeufe'], d['vortag_verkaeufe'])}",
    ]
    if d["verkaeufe"]:
        zeilen.append(f"je Verkauf      {euro(d['umsatz'] / d['verkaeufe']):>8} EUR")
    if d["pfand"]:
        zeilen.append(f"davon Pfand     {euro(d['pfand']):>8} EUR")
    zeilen += [
        "",
        f"{d['rueckblick']}-Tage-Schnitt  {euro(d['schnitt_umsatz']):>8} EUR  "
        f"({zahl(d['schnitt_verkaeufe'])} Verkaeufe/Tag)",
    ]

    if d["je_standort"]:
        zeilen += ["", "Nach Standort"]
        for name, anzahl, umsatz in d["je_standort"]:
            zeilen.append(f"  {name[:34]:<36}{anzahl:>4}{umsatz:>9.2f} EUR")

    if d["je_produkt"]:
        zeilen += ["", "Meistverkauft"]
        for name, anzahl, umsatz in d["je_produkt"][:8]:
            zeilen.append(f"  {name[:34]:<36}{anzahl:>4}{euro(umsatz):>9} EUR")

    if d["stoerungen"]:
        art = ", ".join(f"{n}x {k}" for k, n in sorted(d["stoerungen"].items()))
        zeilen += ["", f"Fehlversuche ohne Warenausgabe: {art}"]

    return "\n".join(zeilen)
