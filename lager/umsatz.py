"""Tageszahlen aus den Vensoft-Verkaufsdaten.

Anders als der Bestand kommt der Umsatz nicht aus dem Bewegungsjournal: dort
stehen nur Mengen. Die Preise liefert die Schnittstelle.

Gemeldet wird der Bruttopreis, also inklusive Mehrwertsteuer. Das Pfand ist im
ausgezeichneten Preis bereits enthalten und wird deshalb nur nachrichtlich
ausgewiesen, nicht aufgeschlagen. Aus den Daten allein ist das nicht
erkennbar - die Zahlungsfelder der Schnittstelle sind leer -, es ist von
ProVend bestaetigt.
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

MONATE = ("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
          "August", "September", "Oktober", "November", "Dezember")


def _aggregat(menge, tabelle, benenne):
    """Verdichtet eine Menge Verkaeufe zu Summen, Standorten und Produkten."""
    je_standort = defaultdict(lambda: [0, 0.0])
    je_produkt = defaultdict(lambda: [0, 0.0])
    for v in menge:
        ort = (tabelle.get("ort_je_automat", {}).get(v.get("parent_id"))
               or tabelle["automat"].get(v.get("parent_id"), "unbekannt"))
        je_standort[ort][0] += 1
        je_standort[ort][1] += vensoft.betrag(v)

        name = benenne(tabelle["produkt"].get(v.get("product_id"), "unbekannt"))
        je_produkt[name][0] += 1
        je_produkt[name][1] += vensoft.betrag(v)

    return {
        "verkaeufe": len(menge),
        "umsatz": sum(vensoft.betrag(v) for v in menge),
        "pfand": sum(float(v.get("pledge") or 0) for v in menge),
        "je_standort": sorted(((n, z[0], z[1]) for n, z in je_standort.items()),
                              key=lambda x: -x[2]),
        "je_produkt": sorted(((n, z[0], z[1]) for n, z in je_produkt.items()),
                             key=lambda x: (-x[1], -x[2])),
    }


def _stoerungen(verkaeufe, tabelle, von, bis):
    """Fehlversuche im Zeitraum: leerer Schacht, Stoerung, Abbruch.

    Sie gehoeren nicht in den Umsatz, sagen aber etwas ueber den Zustand der
    Automaten - mehrere an einem Tag sind ein Hinweis.
    """
    gezaehlt = Counter()
    for v in verkaeufe:
        tag = _tag(v)
        if tag and von <= tag <= bis and not vensoft.ist_ausgegeben(v, tabelle):
            art = tabelle["status"].get(v.get("sale_status_id"), "?")
            gezaehlt[art.replace("sale_status_", "")] += 1
    return dict(gezaehlt)


def monatszahlen(verkaeufe, tabelle, jahr, monat, artikelname=None):
    """Kennzahlen eines Kalendermonats mit Vergleich zum Vormonat."""
    benenne = artikelname or (lambda name: name)
    ausgegeben = [v for v in verkaeufe if vensoft.ist_ausgegeben(v, tabelle)]

    erster = date(jahr, monat, 1)
    letzter = date(jahr + (monat == 12), monat % 12 + 1, 1) - timedelta(days=1)
    vor_erster = (erster - timedelta(days=1)).replace(day=1)
    vor_letzter = erster - timedelta(days=1)

    im_monat = [v for v in ausgegeben if erster <= (_tag(v) or date.min) <= letzter]
    im_vormonat = [v for v in ausgegeben if vor_erster <= (_tag(v) or date.min) <= vor_letzter]

    zahlen = _aggregat(im_monat, tabelle, benenne)
    vergleich = _aggregat(im_vormonat, tabelle, benenne)

    # Verkaufsstaerkster und -schwaechster Tag: nur Tage mit Verkauf, ein Tag
    # ohne jeden Verkauf ist meist ein Ausfall und keine Kennzahl.
    je_tag = defaultdict(lambda: [0, 0.0])
    for v in im_monat:
        tag = _tag(v)
        je_tag[tag][0] += 1
        je_tag[tag][1] += vensoft.betrag(v)
    tage = sorted(((t, z[0], z[1]) for t, z in je_tag.items()), key=lambda x: -x[2])

    zahlen.update({
        "von": erster,
        "bis": letzter,
        "tage_im_monat": (letzter - erster).days + 1,
        "tage_mit_verkauf": len(je_tag),
        "vormonat": vergleich,
        "vormonat_name": MONATE[vor_erster.month - 1],
        "monat_name": MONATE[monat - 1],
        "jahr": jahr,
        "bester_tag": tage[0] if tage else None,
        "schwaechster_tag": tage[-1] if tage else None,
        "stoerungen": _stoerungen(verkaeufe, tabelle, erster, letzter),
    })
    return zahlen


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
        # Ein Tag ohne Verkauf sagt fuer sich genommen nichts. Erst zusammen
        # mit dem Funkkontakt laesst sich sagen, ob wenig gekauft wurde oder
        # ob der Automat gar nicht gemeldet hat.
        "verbindung": vensoft.verbindungsstand(tabelle),
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
            zeilen.append(f"  {name[:34]:<36}{anzahl:>4}{euro(umsatz):>9} EUR")

    if d["je_produkt"]:
        zeilen += ["", "Meistverkauft"]
        for name, anzahl, umsatz in d["je_produkt"][:8]:
            zeilen.append(f"  {name[:34]:<36}{anzahl:>4}{euro(umsatz):>9} EUR")

    if d["stoerungen"]:
        art = ", ".join(f"{n}x {k}" for k, n in sorted(d["stoerungen"].items()))
        zeilen += ["", f"Fehlversuche ohne Warenausgabe: {art}"]

    zeilen += verbindungszeilen(d.get("verbindung", []), d["verkaeufe"])
    return "\n".join(zeilen)


def verbindungszeilen(stand, verkaeufe):
    """Meldet die Verbindung - laut, wenn sie fehlt, leise, wenn sie steht.

    Ein Automat meldet sich stuendlich, auch ohne Verkauf. Deshalb wird nur
    dann gewarnt, wenn der Kontakt tatsaechlich ausbleibt. An einem Tag ganz
    ohne Verkauf wird der Kontakt zusaetzlich bestaetigt - sonst bleibt offen,
    ob der Automat stand oder nur niemand gekauft hat.
    """
    if not stand:
        return []

    stille = [e for e in stand if e["still"]]
    if stille:
        zeilen = ["", "ACHTUNG - Automat meldet sich nicht"]
        for e in stille:
            wann = (e["letzter_kontakt"].strftime("%d.%m.%Y, %H:%M Uhr")
                    if e["letzter_kontakt"] else "nie")
            seit = f" (vor {zahl(e['stunden_her'], 0)} Stunden)" if e["stunden_her"] else ""
            zeilen.append(f"  {e['automat'][:34]:<36}letzter Kontakt {wann}{seit}")
        zeilen.append("  Erwartet wird ein Kontakt pro Stunde. Bitte pruefen.")
        return zeilen

    if verkaeufe == 0:
        return ["", "Kein Verkauf an diesem Tag. Beide Automaten sind verbunden "
                    "(Kontakt im Stundentakt) - es wurde also nichts gekauft."]
    return []


def als_text_monat(zahlen):
    """Monatsauswertung als Text - die Rueckfallebene der E-Mail."""
    d = zahlen
    vor = d["vormonat"]

    def veraenderung(jetzt, vorher):
        if not vorher:
            return ""
        return f"  ({(jetzt - vorher) / vorher * 100:+.0f} % zum Vormonat)"

    zeilen = [
        f"ProVend Monatsauswertung - {d['monat_name']} {d['jahr']}",
        "",
        f"Umsatz          {euro(d['umsatz']):>9} EUR{veraenderung(d['umsatz'], vor['umsatz'])}",
        f"Verkaeufe       {d['verkaeufe']:>9}{veraenderung(d['verkaeufe'], vor['verkaeufe'])}",
    ]
    if d["verkaeufe"]:
        zeilen += [
            f"je Verkauf      {euro(d['umsatz'] / d['verkaeufe']):>9} EUR",
            f"je Tag          {euro(d['umsatz'] / d['tage_im_monat']):>9} EUR  "
            f"({zahl(d['verkaeufe'] / d['tage_im_monat'])} Verkaeufe)",
        ]
    if d["pfand"]:
        zeilen.append(f"davon Pfand     {euro(d['pfand']):>9} EUR")

    zeilen += ["", f"Vormonat {d['vormonat_name']}: {euro(vor['umsatz'])} EUR "
                   f"aus {vor['verkaeufe']} Verkaeufen"]

    if d["bester_tag"]:
        tag, anzahl, betrag = d["bester_tag"]
        zeilen.append(f"Bester Tag: {tag.strftime('%d.%m.')} mit {euro(betrag)} EUR "
                      f"aus {anzahl} Verkaeufen")
        zeilen.append(f"Verkaufstage: {d['tage_mit_verkauf']} von {d['tage_im_monat']}")

    if d["je_standort"]:
        zeilen += ["", "Nach Standort"]
        for name, anzahl, betrag in d["je_standort"]:
            anteil = betrag / d["umsatz"] * 100 if d["umsatz"] else 0
            zeilen.append(f"  {name[:32]:<34}{anzahl:>5}{euro(betrag):>10} EUR"
                          f"{zahl(anteil, 0):>5} %")

    if d["je_produkt"]:
        zeilen += ["", f"Meistverkauft (von {len(d['je_produkt'])} Artikeln)"]
        for name, anzahl, betrag in d["je_produkt"][:15]:
            zeilen.append(f"  {name[:32]:<34}{anzahl:>5}{euro(betrag):>10} EUR")

    if d["stoerungen"]:
        art = ", ".join(f"{n}x {k}" for k, n in sorted(d["stoerungen"].items()))
        zeilen += ["", f"Fehlversuche ohne Warenausgabe: {art}"]

    return "\n".join(zeilen)
