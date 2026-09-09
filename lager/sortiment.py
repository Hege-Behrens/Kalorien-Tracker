"""Sortimentsauswertung: welche Artikel tragen, welche binden nur Platz.

Die Frage ist nicht allein "was verkauft sich oft". Ein Automat hat eine feste
Zahl Schaechte; jeder Schacht, der nichts bringt, kostet den Umsatz, den ein
anderer Artikel dort gemacht haette. Deshalb wird hier neben dem Umsatz auch
die Leistung je Schacht gerechnet - und aufgefuehrt, was ohne Schacht im Lager
liegt und deshalb gar nicht verkauft werden kann.
"""

from collections import defaultdict
from datetime import date, timedelta

from . import vensoft
from .umsatz import _tag, euro, zahl  # noqa: F401  (euro/zahl fuer die Ausgabe)

# Standardfenster. Kurz genug, um das aktuelle Sortiment abzubilden, lang
# genug, dass ein Artikel mit zwei Verkaeufen pro Monat nicht als Ausreisser
# erscheint.
FENSTER_TAGE = 90

# Ab wie vielen Verkaeufen im Fenster ein Artikel nicht mehr als Schwachdreher
# gilt. Darunter traegt er den Schacht nicht.
SCHWACH_GRENZE = 7


def zahlen(verkaeufe, tabelle, lager, artikel_id_zu, tage=FENSTER_TAGE, bis=None):
    """Auswertung aller Produkte ueber ein Zeitfenster.

    artikel_id_zu bildet eine Vensoft-Produktbezeichnung auf eine artikel_id
    ab (oder None). Ohne diese Uebersetzung stuenden falsch beschriftete
    Schaechte unter dem falschen Namen in der Auswertung.
    """
    bis = bis or date.today()
    von = bis - timedelta(days=tage - 1)

    bestand = lager.bestand()
    ausgegeben = [v for v in verkaeufe if vensoft.ist_ausgegeben(v, tabelle)]
    im_fenster = [v for v in ausgegeben if von <= (_tag(v) or date.min) <= bis]

    # Alles wird ueber die artikel_id verdichtet: die Elfbar-Sorten sind bei
    # uns ein Posten, in Vensoft acht Produkte.
    class Posten:
        def __init__(self, name):
            self.name = name
            self.anzahl = 0
            self.umsatz = 0.0
            self.schaechte = 0
            self.automaten = set()
            self.automatenbestand = 0
            self.lagerbestand = 0
            self.letzter = None
            self.kategorie = ""
            self.aktiv = True

    posten = {}

    def hole(produkt_id, bezeichnung):
        artikel_id = artikel_id_zu(bezeichnung) if bezeichnung else None
        artikel = lager.artikel.get(artikel_id) if artikel_id else None
        schluessel = artikel_id or f"vensoft:{bezeichnung or produkt_id}"
        if schluessel not in posten:
            p = Posten(artikel.name if artikel else (bezeichnung or "unbekannt"))
            if artikel:
                p.kategorie = artikel.kategorie
                p.aktiv = artikel.aktiv
                p.lagerbestand = bestand.get(artikel_id, 0)
            posten[schluessel] = p
        return posten[schluessel]

    # Erst die Schaechte: so erscheinen auch Produkte, die im Fenster nichts
    # verkauft haben, aber Platz belegen.
    for produkt_id, schacht in tabelle.get("schaechte", {}).items():
        p = hole(produkt_id, tabelle["produkt"].get(produkt_id))
        p.schaechte += schacht["anzahl"]
        p.automaten |= schacht["automaten"]
        p.automatenbestand += schacht["bestand"]

    # Dann alle Artikel unseres Lagers, damit Bestand ohne Schacht sichtbar wird.
    for a in lager.artikel.values():
        if not a.aktiv:
            continue
        if a.artikel_id not in posten:
            p = Posten(a.name)
            p.kategorie = a.kategorie
            p.lagerbestand = bestand.get(a.artikel_id, 0)
            posten[a.artikel_id] = p

    for v in im_fenster:
        p = hole(v.get("product_id"), tabelle["produkt"].get(v.get("product_id")))
        p.anzahl += 1
        p.umsatz += vensoft.betrag(v)

    # Der letzte Verkauf zaehlt ueber die ganze Historie, nicht nur im Fenster:
    # "seit 140 Tagen nichts" ist die aussagekraeftigere Zahl.
    for v in ausgegeben:
        p = hole(v.get("product_id"), tabelle["produkt"].get(v.get("product_id")))
        d = _tag(v)
        if d and (p.letzter is None or d > p.letzter):
            p.letzter = d

    gesamt = sum(p.umsatz for p in posten.values())
    wochen = tage / 7

    reihen = []
    for p in posten.values():
        reihen.append({
            "name": p.name,
            "kategorie": p.kategorie,
            "anzahl": p.anzahl,
            "umsatz": round(p.umsatz, 2),
            "anteil": (p.umsatz / gesamt * 100) if gesamt else 0.0,
            "schaechte": p.schaechte,
            "automaten": len(p.automaten),
            "automatenbestand": p.automatenbestand,
            "lagerbestand": p.lagerbestand,
            "gesamtbestand": p.automatenbestand + p.lagerbestand,
            "je_schacht": (p.umsatz / p.schaechte) if p.schaechte else None,
            "pro_woche": p.anzahl / wochen,
            "letzter_verkauf": p.letzter,
            "tage_ohne_verkauf": (bis - p.letzter).days if p.letzter else None,
        })

    reihen.sort(key=lambda r: (-r["umsatz"], -r["anzahl"], r["name"]))

    schaechte_gesamt = sum(r["schaechte"] for r in reihen)
    mit_schacht = [r for r in reihen if r["schaechte"]]

    return {
        "von": von,
        "bis": bis,
        "tage": tage,
        "umsatz": round(gesamt, 2),
        "verkaeufe": len(im_fenster),
        "artikel": reihen,
        "verkauft": [r for r in reihen if r["anzahl"]],
        "schaechte_gesamt": schaechte_gesamt,
        "schnitt_je_schacht": (gesamt / schaechte_gesamt) if schaechte_gesamt else 0.0,
        # Schacht belegt, im Fenster kein einziger Verkauf.
        "nullsteller": sorted((r for r in mit_schacht if not r["anzahl"]),
                              key=lambda r: (-r["schaechte"], -r["gesamtbestand"])),
        # Schacht belegt, aber zu wenig Verkauf, um ihn zu tragen.
        "schwachdreher": sorted((r for r in mit_schacht
                                 if 0 < r["anzahl"] < SCHWACH_GRENZE),
                                key=lambda r: (r["je_schacht"], -r["gesamtbestand"])),
        # Ware im Lager, aber kein Schacht - kann nicht verkauft werden.
        "ohne_schacht": sorted((r for r in reihen
                                if not r["schaechte"] and r["lagerbestand"] > 0),
                               key=lambda r: -r["lagerbestand"]),
        "gebundene_stueck": sum(r["gesamtbestand"] for r in reihen
                                if r["schaechte"] and not r["anzahl"]),
    }


def _kurz(text, breite):
    return text if len(text) <= breite else text[:breite - 1] + "…"


def als_text(d):
    z = [
        f"ProVend Sortimentsauswertung - {d['von'].strftime('%d.%m.%Y')} bis "
        f"{d['bis'].strftime('%d.%m.%Y')} ({d['tage']} Tage)",
        "",
        f"Umsatz          {euro(d['umsatz']):>9} EUR aus {d['verkaeufe']} Verkaeufen",
        f"Schaechte       {d['schaechte_gesamt']:>9}, im Schnitt "
        f"{euro(d['schnitt_je_schacht'])} EUR je Schacht",
        "",
        "Rangliste nach Umsatz",
        f"  {'Artikel':<28}{'Stk':>5}{'Umsatz':>10}{'Anteil':>8}"
        f"{'Schacht':>8}{'je Sch.':>9}{'Bestand':>9}",
    ]
    for r in d["verkauft"]:
        z.append(
            f"  {_kurz(r['name'], 27):<28}{r['anzahl']:>5}"
            f"{euro(r['umsatz']):>10}{zahl(r['anteil'], 1) + ' %':>8}"
            f"{(r['schaechte'] or '-'):>8}"
            f"{(euro(r['je_schacht']) if r['je_schacht'] else '-'):>9}"
            f"{r['gesamtbestand']:>9}"
        )

    if d["nullsteller"]:
        z += ["", f"Kein Verkauf im Zeitraum - {len(d['nullsteller'])} Artikel auf "
                  f"{sum(r['schaechte'] for r in d['nullsteller'])} Schaechten, "
                  f"{d['gebundene_stueck']} Stueck gebunden"]
        for r in d["nullsteller"]:
            seit = (f"zuletzt {r['letzter_verkauf'].strftime('%d.%m.%Y')}"
                    if r["letzter_verkauf"] else "noch nie verkauft")
            z.append(f"  {_kurz(r['name'], 30):<32}{r['schaechte']:>3} Schacht "
                     f"{r['gesamtbestand']:>4} Stk   {seit}")

    if d["schwachdreher"]:
        z += ["", f"Schwachdreher (unter {SCHWACH_GRENZE} Verkaeufen im Zeitraum)"]
        for r in d["schwachdreher"]:
            z.append(f"  {_kurz(r['name'], 30):<32}{r['anzahl']:>3} Stk "
                     f"{euro(r['umsatz']):>8} EUR  {r['schaechte']} Schacht  "
                     f"Bestand {r['gesamtbestand']}")

    if d["ohne_schacht"]:
        z += ["", "Bestand ohne Schacht - kann nicht verkauft werden"]
        for r in d["ohne_schacht"]:
            z.append(f"  {_kurz(r['name'], 30):<32}{r['lagerbestand']:>4} Stk")

    return "\n".join(z)


def als_csv(d):
    import csv
    import io

    puffer = io.StringIO()
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(["Artikel", "Kategorie", "Verkaeufe", "Umsatz EUR",
                        "Anteil %", "Schaechte", "Automaten", "Bestand Automat",
                        "Bestand Lager", "Umsatz je Schacht", "Verkaeufe je Woche",
                        "Letzter Verkauf", "Tage ohne Verkauf"])
    for r in d["artikel"]:
        schreiber.writerow([
            r["name"], r["kategorie"], r["anzahl"],
            f"{r['umsatz']:.2f}".replace(".", ","),
            f"{r['anteil']:.1f}".replace(".", ","),
            r["schaechte"], r["automaten"], r["automatenbestand"], r["lagerbestand"],
            f"{r['je_schacht']:.2f}".replace(".", ",") if r["je_schacht"] else "",
            f"{r['pro_woche']:.1f}".replace(".", ","),
            r["letzter_verkauf"].strftime("%d.%m.%Y") if r["letzter_verkauf"] else "",
            r["tage_ohne_verkauf"] if r["tage_ohne_verkauf"] is not None else "",
        ])
    return puffer.getvalue()
