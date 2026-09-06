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

        if menge < 0:
            # Rechnerisch unmoeglich - es wurde mehr verkauft als eingekauft.
            # Praktisch heisst das: eine Rechnung fehlt noch.
            status = "MINUS"
        elif menge == 0:
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
        if status != "OK":
            ziel = max(a.mindestbestand, round(pro_tag * ZIELREICHWEITE_TAGE))
            vorschlag_stueck = max(0, ziel - menge)
        gebinde = max(1, a.stueck_pro_gebinde)
        vorschlag_gebinde = -(-vorschlag_stueck // gebinde) if vorschlag_stueck else 0
        # Wer genau auf dem Mindestbestand steht, braucht rechnerisch nichts -
        # praktisch aber schon. Mindestens ein Gebinde, sobald der Status kippt.
        if status != "OK" and vorschlag_gebinde == 0:
            vorschlag_gebinde = 1

        ergebnis.append({
            "artikel_id": a.artikel_id,
            "name": a.name,
            "nummer": a.nummer,
            "selektor": a.selektor,
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

    rang = {"MINUS": 0, "LEER": 1, "NACHBESTELLEN": 2, "KNAPP": 3, "OK": 4}
    ergebnis.sort(key=lambda z: (rang[z["status"]], z["name"].lower()))
    return ergebnis


def warnungen(lager):
    return [z for z in zeilen(lager) if z["status"] != "OK"]


def mindestbestand_vorschlaege(lager, fenster=VERBRAUCHSFENSTER_TAGE, puffer_tage=14):
    """Schlaegt je Artikel einen Mindestbestand aus dem gemessenen Verbrauch vor.

    Die Schwelle soll den Zeitraum abdecken, der zwischen Warnung und
    Nachschub vergeht - Einkauf inklusive. Artikel ohne Verkaeufe im Fenster
    bekommen keinen Vorschlag: dort fehlt schlicht die Grundlage.
    """
    verbrauch = verbrauch_pro_tag(lager, fenster)
    vorschlaege = []
    for a in lager.artikel.values():
        if not a.aktiv:
            continue
        pro_tag = verbrauch.get(a.artikel_id, 0.0)
        if pro_tag <= 0:
            continue
        vorschlaege.append({
            "artikel_id": a.artikel_id,
            "name": a.name,
            "verbrauch_pro_tag": round(pro_tag, 2),
            "bisher": a.mindestbestand,
            "vorschlag": max(1, round(pro_tag * puffer_tage)),
        })
    vorschlaege.sort(key=lambda v: -v["verbrauch_pro_tag"])
    return vorschlaege


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


def kennzahlen(lager):
    """Die drei Zahlen, die oben auf dem Bericht stehen."""
    daten = zeilen(lager)
    return {
        "artikel": len(daten),
        "handlungsbedarf": len([z for z in daten if z["status"] != "OK"]),
        "stueck": sum(z["bestand"] for z in daten),
    }


def als_excel(lager, pfad):
    """Schreibt die Bestandsliste als Excel-Datei - das ist der Mailanhang.

    Aufbau: Briefkopf mit Logo und Kennzahlen, darunter die Tabelle. Die
    Farben stammen aus dem Logo, die Ampelfarben der Statusspalte bleiben
    davon unberuehrt.
    """
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.utils import get_column_letter

    from . import marke

    farben = marke.palette(lager)
    primaer, akzent, hell = farben["primaer"], farben["akzent"], farben["hell"]

    mappe = openpyxl.Workbook()
    blatt = mappe.active
    blatt.title = "Bestand"
    blatt.sheet_view.showGridLines = False

    # Nr. und Selektor bleiben bewusst draussen: fuer den Einkauf sind sie
    # ohne Bedeutung. Beide Felder stehen weiterhin in data/artikel.csv.
    spalten = [
        ("Artikel", "name", 42, "links"),
        ("Bestand", "bestand", 12, "zahl"),
        ("Mindest-\nbestand", "mindestbestand", 13, "zahl"),
        ("Verbrauch\npro Tag", "verbrauch_pro_tag", 13, "komma"),
        ("Reichweite\n(Tage)", "reichweite_tage", 13, "komma"),
        ("Status", "status", 17, "mitte"),
        ("Bestellen\n(Gebinde)", "bestellvorschlag_gebinde", 13, "zahl"),
        ("Lieferant", "lieferant", 18, "links"),
    ]
    letzte_spalte = get_column_letter(len(spalten))

    for nummer, (_, _, breite, _) in enumerate(spalten, start=1):
        blatt.column_dimensions[get_column_letter(nummer)].width = breite

    # ---------- Briefkopf ----------
    KOPFZEILEN = 6
    TABELLENKOPF = KOPFZEILEN + 2

    for zeilen_nr in range(1, KOPFZEILEN + 1):
        blatt.row_dimensions[zeilen_nr].height = 22
        for nummer in range(1, len(spalten) + 1):
            blatt.cell(row=zeilen_nr, column=nummer).fill = PatternFill("solid", fgColor="FFFFFF")

    logo, groesse = marke.logo_fuer_einbettung(240)
    if logo:
        bild = openpyxl.drawing.image.Image(logo)
        # Auf eine Hoehe skalieren, die in den Briefkopf passt.
        zielhoehe = 96
        bild.height = zielhoehe
        bild.width = round(groesse[0] * zielhoehe / groesse[1]) if groesse[1] else 110
        bild.anchor = "A1"
        blatt.add_image(bild)

    stand = date.today().strftime("%d.%m.%Y")
    titel = blatt.cell(row=2, column=3, value="Bestandsliste")
    titel.font = Font(bold=True, size=20, color=primaer)
    titel.alignment = Alignment(vertical="center")
    blatt.merge_cells(start_row=2, start_column=3, end_row=2, end_column=6)

    unterzeile = blatt.cell(row=3, column=3, value=f"Stand {stand}")
    unterzeile.font = Font(size=10, color="6B7280")
    blatt.merge_cells(start_row=3, start_column=3, end_row=3, end_column=6)

    werte = kennzahlen(lager)
    kacheln = [
        ("Artikel", werte["artikel"], primaer),
        ("Handlungsbedarf", werte["handlungsbedarf"], akzent),
        ("Stück im Bestand", werte["stueck"], primaer),
    ]
    for versatz, (beschriftung, wert, farbe) in enumerate(kacheln):
        spalte = 7 + versatz
        if spalte > len(spalten):
            break
        kopf = blatt.cell(row=2, column=spalte, value=wert)
        kopf.font = Font(bold=True, size=16, color=farbe)
        kopf.alignment = Alignment(horizontal="center", vertical="center")
        fuss = blatt.cell(row=3, column=spalte, value=beschriftung)
        fuss.font = Font(size=9, color="6B7280")
        fuss.alignment = Alignment(horizontal="center", vertical="top")

    # Goldene Trennlinie zwischen Briefkopf und Tabelle.
    blatt.row_dimensions[KOPFZEILEN + 1].height = 5
    for nummer in range(1, len(spalten) + 1):
        blatt.cell(row=KOPFZEILEN + 1, column=nummer).fill = PatternFill("solid", fgColor=akzent)

    # ---------- Tabellenkopf ----------
    blatt.row_dimensions[TABELLENKOPF].height = 32
    kopf_text = marke.textfarbe_auf(primaer)
    for nummer, (beschriftung, _, _, _) in enumerate(spalten, start=1):
        zelle = blatt.cell(row=TABELLENKOPF, column=nummer, value=beschriftung)
        zelle.font = Font(bold=True, size=10, color=kopf_text)
        zelle.fill = PatternFill("solid", fgColor=primaer)
        zelle.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)

    # ---------- Datenzeilen ----------
    rahmen = Side(style="thin", color="E5E7EB")
    ausrichtung = {
        "links": Alignment(horizontal="left", vertical="center"),
        "mitte": Alignment(horizontal="center", vertical="center"),
        "zahl": Alignment(horizontal="right", vertical="center"),
        "komma": Alignment(horizontal="right", vertical="center"),
    }
    zahlenformat = {"zahl": "0", "komma": "0.0"}

    daten = zeilen(lager)
    for versatz, z in enumerate(daten):
        zeilen_nr = TABELLENKOPF + 1 + versatz
        blatt.row_dimensions[zeilen_nr].height = 20
        streifen = hell if versatz % 2 else "FFFFFF"

        for nummer, (_, feld, _, art) in enumerate(spalten, start=1):
            wert = z[feld]
            zelle = blatt.cell(row=zeilen_nr, column=nummer, value=wert)
            zelle.alignment = ausrichtung[art]
            zelle.border = Border(bottom=rahmen)
            zelle.fill = PatternFill("solid", fgColor=streifen)
            if art in zahlenformat and isinstance(wert, (int, float)):
                zelle.number_format = zahlenformat[art]
            if feld == "name":
                zelle.font = Font(size=11, bold=z["status"] in ("MINUS", "LEER"))

            if feld == "status":
                farbe = marke.STATUS_FARBEN[wert]
                zelle.fill = PatternFill("solid", fgColor=farbe)
                zelle.font = Font(bold=True, size=9, color=marke.textfarbe_auf(farbe))

    blatt.freeze_panes = f"A{TABELLENKOPF + 1}"
    blatt.auto_filter.ref = f"A{TABELLENKOPF}:{letzte_spalte}{TABELLENKOPF + len(daten)}"
    blatt.page_setup.orientation = "landscape"
    blatt.page_setup.fitToWidth = 1
    blatt.sheet_properties.pageSetUpPr.fitToPage = True
    blatt.print_title_rows = f"{TABELLENKOPF}:{TABELLENKOPF}"

    mappe.save(pfad)
    return pfad


def als_html(lager, logo_cid="logo"):
    """Bestandsliste als E-Mail im Erscheinungsbild der Marke.

    Bewusst tabellenbasiert und mit Stilangaben direkt an den Elementen:
    E-Mail-Programme ignorieren Stylesheets im Kopf und moderne Layouts.
    """
    from . import marke

    farben = marke.palette(lager)
    primaer, akzent, hell = farben["primaer"], farben["akzent"], farben["hell"]
    werte = kennzahlen(lager)
    offene = warnungen(lager)
    stand = date.today().strftime("%d.%m.%Y")

    def kachel(wert, beschriftung, farbe):
        return (
            f'<td align="center" style="padding:14px 8px;background:{"#" + hell};'
            f'border-radius:6px;">'
            f'<div style="font:700 26px/1.1 Helvetica,Arial,sans-serif;color:#{farbe};">{wert}</div>'
            f'<div style="font:400 11px/1.4 Helvetica,Arial,sans-serif;color:#6B7280;'
            f'text-transform:uppercase;letter-spacing:.06em;padding-top:4px;">{beschriftung}</div>'
            f'</td>'
        )

    def statusfeld(status):
        farbe = marke.STATUS_FARBEN[status]
        return (
            f'<span style="display:inline-block;padding:3px 9px;border-radius:10px;'
            f'background:#{farbe};color:#{marke.textfarbe_auf(farbe)};'
            f'font:700 10px/1.4 Helvetica,Arial,sans-serif;letter-spacing:.04em;">{status}</span>'
        )

    if offene:
        kopfzeile = "".join(
            f'<th align="{ausrichtung}" style="padding:9px 10px;background:#{primaer};'
            f'color:#{marke.textfarbe_auf(primaer)};font:700 11px/1.3 Helvetica,Arial,sans-serif;'
            f'text-transform:uppercase;letter-spacing:.05em;">{titel}</th>'
            for titel, ausrichtung in (
                ("Artikel", "left"), ("Bestand", "right"), ("Reichweite", "right"),
                ("Status", "center"), ("Bestellen", "right"))
        )
        zeilen_html = []
        for nummer, z in enumerate(offene):
            hintergrund = hell if nummer % 2 else "FFFFFF"
            reichweite = f'{z["reichweite_tage"]} Tage' if z["reichweite_tage"] != "" else "–"
            bestellen = f'{z["bestellvorschlag_gebinde"]} Geb.' if z["bestellvorschlag_gebinde"] else "–"
            felder = (
                f'<td style="padding:9px 10px;background:#{hintergrund};'
                f'font:600 13px/1.4 Helvetica,Arial,sans-serif;color:#{primaer};">{z["name"]}</td>'
                f'<td align="right" style="padding:9px 10px;background:#{hintergrund};'
                f'font:400 13px/1.4 Helvetica,Arial,sans-serif;color:#374151;">{z["bestand"]}</td>'
                f'<td align="right" style="padding:9px 10px;background:#{hintergrund};'
                f'font:400 13px/1.4 Helvetica,Arial,sans-serif;color:#374151;">{reichweite}</td>'
                f'<td align="center" style="padding:9px 10px;background:#{hintergrund};">'
                f'{statusfeld(z["status"])}</td>'
                f'<td align="right" style="padding:9px 10px;background:#{hintergrund};'
                f'font:700 13px/1.4 Helvetica,Arial,sans-serif;color:#{akzent};">{bestellen}</td>'
            )
            zeilen_html.append(f"<tr>{felder}</tr>")
        tabelle = (
            f'<table width="100%" cellpadding="0" cellspacing="0" role="presentation" '
            f'style="border-collapse:collapse;"><tr>{kopfzeile}</tr>{"".join(zeilen_html)}</table>'
        )
        einleitung = (
            f'<strong style="color:#{primaer};">{len(offene)}</strong> von '
            f'{werte["artikel"]} Artikeln brauchen Aufmerksamkeit.'
        )
    else:
        tabelle = (
            f'<div style="padding:22px;background:#{hell};border-radius:6px;text-align:center;'
            f'font:400 14px/1.5 Helvetica,Arial,sans-serif;color:#374151;">'
            f'Alle Artikel sind ausreichend bevorratet.</div>'
        )
        einleitung = "Kein Artikel liegt unter dem Mindestbestand."

    logo_block = (
        f'<img src="cid:{logo_cid}" width="150" alt="ProVend" style="display:block;border:0;">'
        if marke.logo_pfad() else
        f'<div style="font:700 22px/1 Helvetica,Arial,sans-serif;color:#{primaer};">Bestandsliste</div>'
    )

    return f"""<!doctype html>
<html lang="de"><body style="margin:0;padding:24px 12px;background:#F4F4F5;">
<table align="center" width="640" cellpadding="0" cellspacing="0" role="presentation"
       style="max-width:640px;background:#FFFFFF;border-radius:10px;overflow:hidden;
              box-shadow:0 1px 3px rgba(0,0,0,.08);">
  <tr><td style="padding:28px 28px 20px;">
    <table width="100%" cellpadding="0" cellspacing="0" role="presentation"><tr>
      <td align="left" valign="middle">{logo_block}</td>
      <td align="right" valign="middle">
        <div style="font:700 20px/1.2 Helvetica,Arial,sans-serif;color:#{primaer};">Bestandsliste</div>
        <div style="font:400 12px/1.5 Helvetica,Arial,sans-serif;color:#6B7280;">Stand {stand}</div>
      </td>
    </tr></table>
  </td></tr>

  <tr><td style="height:4px;background:#{akzent};font-size:0;line-height:0;">&nbsp;</td></tr>

  <tr><td style="padding:24px 28px 8px;">
    <table width="100%" cellpadding="0" cellspacing="8" role="presentation"><tr>
      {kachel(werte["artikel"], "Artikel", primaer)}
      {kachel(werte["handlungsbedarf"], "Handlungsbedarf", akzent)}
      {kachel(werte["stueck"], "Stück im Bestand", primaer)}
    </tr></table>
  </td></tr>

  <tr><td style="padding:16px 28px 4px;font:400 14px/1.6 Helvetica,Arial,sans-serif;color:#374151;">
    {einleitung}
  </td></tr>

  <tr><td style="padding:12px 28px 24px;">{tabelle}</td></tr>

  <tr><td style="padding:0 28px 28px;font:400 12px/1.6 Helvetica,Arial,sans-serif;color:#6B7280;">
    Die vollständige Liste aller {werte["artikel"]} Artikel liegt als Excel-Datei im Anhang.
  </td></tr>

  <tr><td style="padding:16px 28px;background:#{primaer};
                 font:400 11px/1.5 Helvetica,Arial,sans-serif;color:rgba(255,255,255,.7);">
    ProVend Deutschland GbR · Automatisch erzeugt am {stand}
  </td></tr>
</table>
</body></html>"""
