"""Auswertung: Bestandsliste, Warnungen, Bestellvorschlag, Excel-Bericht."""

from datetime import date, timedelta

from .daten import TYPEN

# Zeitraum, ueber den der Durchschnittsverbrauch gerechnet wird.
VERBRAUCHSFENSTER_TAGE = 28
# Zeitraum, den eine Bestellung abdecken soll.
ZIELREICHWEITE_TAGE = 21


def _als_datum(text):
    try:
        return date.fromisoformat(text[:10])
    except (ValueError, TypeError):
        return None


def verbrauch_pro_tag(lager, fenster=VERBRAUCHSFENSTER_TAGE):
    """Durchschnittlicher Tagesverbrauch je Artikel aus den Verkaufsbuchungen."""
    grenze = date.today() - timedelta(days=fenster)
    summen = {}
    for b in lager.bewegungen:
        if b.typ != "VERKAUF":
            continue
        d = _als_datum(b.datum)
        if d and d >= grenze:
            summen[b.artikel_id] = summen.get(b.artikel_id, 0) + b.menge
    return {aid: menge / fenster for aid, menge in summen.items()}


def zeilen(lager):
    """Eine ausgewertete Zeile je aktivem Artikel, sortiert nach Dringlichkeit."""
    bestand = lager.bestand()
    verbrauch = verbrauch_pro_tag(lager)
    ergebnis = []

    for a in lager.artikel.values():
        if not a.aktiv:
            continue
        menge = bestand.get(a.artikel_id, 0)
        pro_tag = verbrauch.get(a.artikel_id, 0.0)
        reichweite = (menge / pro_tag) if pro_tag > 0 else None

        if menge <= 0:
            status = "LEER"
        elif a.mindestbestand and menge <= a.mindestbestand:
            status = "NACHBESTELLEN"
        elif reichweite is not None and reichweite < 7:
            status = "KNAPP"
        else:
            status = "OK"

        # Bestellvorschlag: auffuellen bis Mindestbestand plus Zielreichweite,
        # aufgerundet auf volle Gebinde.
        vorschlag_stueck = 0
        if status in ("LEER", "NACHBESTELLEN", "KNAPP"):
            ziel = max(a.mindestbestand, round(pro_tag * ZIELREICHWEITE_TAGE))
            vorschlag_stueck = max(0, ziel - menge)
        gebinde = max(1, a.stueck_pro_gebinde)
        vorschlag_gebinde = -(-vorschlag_stueck // gebinde) if vorschlag_stueck else 0

        ergebnis.append({
            "artikel_id": a.artikel_id,
            "name": a.name,
            "kategorie": a.kategorie,
            "bestand": menge,
            "mindestbestand": a.mindestbestand,
            "status": status,
            "verbrauch_pro_tag": round(pro_tag, 2),
            "reichweite_tage": round(reichweite, 1) if reichweite is not None else "",
            "bestellvorschlag_stueck": vorschlag_gebinde * gebinde,
            "bestellvorschlag_gebinde": vorschlag_gebinde,
            "lieferant": a.lieferant,
        })

    rang = {"LEER": 0, "NACHBESTELLEN": 1, "KNAPP": 2, "OK": 3}
    ergebnis.sort(key=lambda z: (rang[z["status"]], z["name"].lower()))
    return ergebnis


def warnungen(lager):
    return [z for z in zeilen(lager) if z["status"] != "OK"]


def als_text(lager, nur_warnungen=False):
    daten = warnungen(lager) if nur_warnungen else zeilen(lager)
    if not daten:
        return "Keine Artikel unterhalb des Mindestbestands."

    kopf = f"{'Artikel':<34}{'Bestand':>9}{'Min':>6}{'Reichw.':>9}  {'Status':<14}{'Bestellen':>10}"
    linien = [kopf, "-" * len(kopf)]
    for z in daten:
        reich = f"{z['reichweite_tage']} T" if z["reichweite_tage"] != "" else "-"
        bestellen = f"{z['bestellvorschlag_gebinde']} Geb." if z["bestellvorschlag_gebinde"] else "-"
        linien.append(
            f"{z['name'][:33]:<34}{z['bestand']:>9}{z['mindestbestand']:>6}"
            f"{reich:>9}  {z['status']:<14}{bestellen:>10}"
        )
    return "\n".join(linien)


def als_excel(lager, pfad):
    """Schreibt die Bestandsliste als Excel-Datei - das ist der Mailanhang."""
    import openpyxl
    from openpyxl.styles import Alignment, Font, PatternFill

    mappe = openpyxl.Workbook()
    blatt = mappe.active
    blatt.title = "Bestand"

    spalten = [
        ("Artikel", "name", 36),
        ("Kategorie", "kategorie", 16),
        ("Bestand (Stk.)", "bestand", 14),
        ("Mindestbestand", "mindestbestand", 15),
        ("Verbrauch/Tag", "verbrauch_pro_tag", 14),
        ("Reichweite (Tage)", "reichweite_tage", 17),
        ("Status", "status", 15),
        ("Bestellen (Gebinde)", "bestellvorschlag_gebinde", 19),
        ("Lieferant", "lieferant", 16),
    ]

    kopf_stil = Font(bold=True, color="FFFFFF")
    kopf_fuell = PatternFill("solid", fgColor="374151")
    for spalte, (titel, _, breite) in enumerate(spalten, start=1):
        zelle = blatt.cell(row=1, column=spalte, value=titel)
        zelle.font = kopf_stil
        zelle.fill = kopf_fuell
        zelle.alignment = Alignment(vertical="center", wrap_text=True)
        blatt.column_dimensions[zelle.column_letter].width = breite
    blatt.freeze_panes = "A2"

    farben = {
        "LEER": "FCA5A5",
        "NACHBESTELLEN": "FDE68A",
        "KNAPP": "FEF3C7",
        "OK": "FFFFFF",
    }

    for zeilen_nr, z in enumerate(zeilen(lager), start=2):
        for spalte, (_, feld, _) in enumerate(spalten, start=1):
            zelle = blatt.cell(row=zeilen_nr, column=spalte, value=z[feld])
            if z["status"] != "OK":
                zelle.fill = PatternFill("solid", fgColor=farben[z["status"]])

    blatt.auto_filter.ref = f"A1:{blatt.cell(row=1, column=len(spalten)).column_letter}{blatt.max_row}"
    mappe.save(pfad)
    return pfad
