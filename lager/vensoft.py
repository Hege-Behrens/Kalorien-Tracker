"""Abruf der Verkaufsdaten aus der Vensoft-Schnittstelle.

Zugangsdaten kommen ausschliesslich aus der Umgebung - sie gehoeren nicht ins
Repository:

    export VENSOFT_USER=...
    export VENSOFT_PASS=...

Die Schnittstelle bietet zwei Wege. Der JSON-Weg ueber /sales arbeitet mit
einem fortlaufenden Lesezeichen: jeder Abruf liefert nur, was seit der zuletzt
gesehenen ID dazugekommen ist. Das passt genau zu unserem Bewegungsjournal -
kein Zeitraum muss geraten werden, und Ueberschneidungen kann es nicht geben.
"""

import base64
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASIS_URL = os.environ.get("VENSOFT_URL", "https://adapter.vensoft.de/100/Dump/")
ZEITLIMIT = 60


class VensoftFehler(RuntimeError):
    pass


def _zugang():
    benutzer = os.environ.get("VENSOFT_USER", "")
    passwort = os.environ.get("VENSOFT_PASS", "")
    if not (benutzer and passwort):
        raise VensoftFehler(
            "VENSOFT_USER und VENSOFT_PASS muessen gesetzt sein. "
            "Die Zugangsdaten stehen bewusst nicht im Repository."
        )
    roh = f"{benutzer}:{passwort}".encode()
    return "Basic " + base64.b64encode(roh).decode()


def abrufen(pfad, felder=None, roh=False):
    """Ruft einen Endpunkt ab. felder werden als Formulardaten gesendet."""
    url = urllib.parse.urljoin(BASIS_URL, pfad.lstrip("/"))
    daten = urllib.parse.urlencode(felder).encode() if felder else None

    anfrage = urllib.request.Request(url, data=daten)
    anfrage.add_header("Authorization", _zugang())
    anfrage.add_header("Accept", "application/json")

    try:
        with urllib.request.urlopen(anfrage, timeout=ZEITLIMIT) as antwort:
            inhalt = antwort.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as fehler:
        raise VensoftFehler(f"{pfad}: HTTP {fehler.code} {fehler.reason}") from fehler
    except urllib.error.URLError as fehler:
        raise VensoftFehler(
            f"{pfad}: keine Verbindung ({fehler.reason}). Ist adapter.vensoft.de "
            f"in der Netzwerkfreigabe dieser Umgebung erlaubt?"
        ) from fehler

    if roh:
        return inhalt
    try:
        return json.loads(inhalt)
    except json.JSONDecodeError as fehler:
        raise VensoftFehler(f"{pfad}: Antwort ist kein JSON: {inhalt[:200]}") from fehler


def stammdaten():
    """Uebersetzungstabelle: Automaten-, Standort- und Produkt-IDs zu Klarnamen."""
    return abrufen("core")


def verkaeufe_ab(letzte_id=0):
    """Ein Paket Verkaufsdaten ab der zuletzt gesehenen ID."""
    return abrufen("sales", {"id": letzte_id})


def alle_verkaeufe_ab(letzte_id=0, hoechstens=50):
    """Blaettert bis zum aktuellen Stand und liefert alle Datensaetze.

    hoechstens begrenzt die Zahl der Pakete, damit ein unerwartetes Verhalten
    der Gegenstelle nicht in eine Endlosschleife laeuft.
    """
    gesammelt = []
    for _ in range(hoechstens):
        antwort = verkaeufe_ab(letzte_id)
        paket = antwort.get("vensoft_sale", []) if isinstance(antwort, dict) else []
        if not paket:
            break
        gesammelt.extend(paket)
        ids = [int(z["id"]) for z in paket if str(z.get("id", "")).isdigit()]
        if not ids or max(ids) <= letzte_id:
            break  # kein Fortschritt - abbrechen statt endlos abzurufen
        letzte_id = max(ids)
    return gesammelt, letzte_id


def verkaeufe_csv(von, bis):
    """Fertige CSV fuer einen Zeitraum (Datum als JJJJ-MM-TT)."""
    return abrufen("salescsv", {"dateFrom": von, "dateTo": bis}, roh=True)


# Nur bei diesen Status hat Ware den Automaten tatsaechlich verlassen. "empty",
# "error" und "cancel" sind Fehlversuche - wer sie mitzaehlt, bucht Ware ab,
# die nie ausgegeben wurde, und der Bestand laeuft unbemerkt ins Minus.
WARE_AUSGEGEBEN = {
    "sale_status_success",
    "sale_status_test",
    "sale_status_free",
    "sale_status_token",
}


def uebersetzungstabelle(stamm):
    """Baut aus den Stammdaten die Zuordnung von IDs zu Klarnamen."""
    def kennzeichen(eintrag):
        return (eintrag.get("name") or "").strip("$")

    orte = {s["id"]: s["name"] for s in stamm.get("vensoft_site", [])}
    return {
        "produkt": {p["id"]: p["name"] for p in stamm.get("vensoft_product", [])},
        "automat": {m["id"]: m["serial_number"] for m in stamm.get("vensoft_machine", [])},
        "standort": orte,
        # Fuer Berichte ist der Standortname aussagekraeftiger als die
        # Seriennummer des Automaten.
        "ort_je_automat": {m["id"]: orte.get(m.get("parent_id"), m["serial_number"])
                           for m in stamm.get("vensoft_machine", [])},
        "status": {s["id"]: kennzeichen(s) for s in stamm.get("vensoft_sale_status", [])},
        # Belegte Schaechte je Produkt. Ein Artikel ohne Schacht kann nichts
        # verkaufen, egal wie viel davon im Lager liegt - und ein Schacht ohne
        # Verkauf ist gebundener Platz.
        "schaechte": _schaechte(stamm),
    }


def _schaechte(stamm):
    """Je Produkt: Zahl der Schaechte und der darin stehende Bestand."""
    gezaehlt = {}
    for schacht in stamm.get("vensoft_machine_product", []):
        eintrag = gezaehlt.setdefault(schacht.get("product_id"),
                                      {"anzahl": 0, "bestand": 0, "automaten": set()})
        eintrag["anzahl"] += 1
        eintrag["automaten"].add(schacht.get("parent_id"))
        try:
            eintrag["bestand"] += int(schacht.get("actual_amount") or 0)
        except (TypeError, ValueError):
            pass
    return gezaehlt


def ist_ausgegeben(verkauf, tabelle):
    return tabelle["status"].get(verkauf.get("sale_status_id")) in WARE_AUSGEGEBEN


def betrag(verkauf):
    """Bruttopreis in Euro. Die Schnittstelle liefert bereits Euro, nicht Cent."""
    try:
        return float(verkauf.get("price_gross") or 0)
    except (TypeError, ValueError):
        return 0.0


# ---------- Zwischenspeicher ----------
#
# Die Berichte brauchen nicht nur die neuen Verkaeufe, sondern auch die
# Vortage fuer den Vergleich. Ohne Zwischenspeicher muesste dafuer jedes Mal
# die gesamte Historie abgerufen werden - sieben Pakete, mehrere Minuten, und
# das mehrfach am Tag. Gespeichert wird deshalb lokal und nur ergaenzt.

SPEICHER = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "data", "vensoft")
VERKAEUFE_DATEI = os.path.join(SPEICHER, "verkaeufe.jsonl")
STAMM_DATEI = os.path.join(SPEICHER, "stammdaten.json")

# Nur die Felder, die ausgewertet werden. Der Rest der Schnittstelle ist fuer
# uns ohne Belang und wuerde die Datei um ein Vielfaches aufblaehen.
VERKAUFSFELDER = ("id", "tstamp", "parent_id", "product_id", "sale_status_id",
                  "price_gross", "pledge")

# Die Stammdaten aendern sich selten; diese Tabellen werden ausgewertet.
STAMMTABELLEN = ("vensoft_product", "vensoft_machine", "vensoft_site",
                 "vensoft_sale_status", "vensoft_machine_product")


def _schlank(verkauf):
    return {feld: verkauf.get(feld) for feld in VERKAUFSFELDER}


def gespeicherte_verkaeufe():
    if not os.path.exists(VERKAEUFE_DATEI):
        return []
    with open(VERKAEUFE_DATEI, encoding="utf-8") as f:
        return [json.loads(zeile) for zeile in f if zeile.strip()]


def _hoechste_id(verkaeufe):
    ids = [int(v["id"]) for v in verkaeufe if str(v.get("id", "")).isdigit()]
    return max(ids) if ids else 0


def gespeicherte_stammdaten():
    if not os.path.exists(STAMM_DATEI):
        return None
    with open(STAMM_DATEI, encoding="utf-8") as f:
        return json.load(f)


def stammdaten_auffrischen():
    """Holt die Stammdaten neu und legt sie schlank ab."""
    voll = stammdaten()
    schlank = {tabelle: voll.get(tabelle, []) for tabelle in STAMMTABELLEN}
    os.makedirs(SPEICHER, exist_ok=True)
    with open(STAMM_DATEI, "w", encoding="utf-8") as f:
        json.dump(schlank, f, ensure_ascii=False, indent=1)
    return schlank


def zwischenspeicher_aktualisieren(stamm_auffrischen=False):
    """Ergaenzt den Zwischenspeicher um die neuen Verkaeufe.

    Liefert (Stammdaten, alle Verkaeufe, Zahl der neu hinzugekommenen).
    """
    stamm = None if stamm_auffrischen else gespeicherte_stammdaten()
    if stamm is None:
        stamm = stammdaten_auffrischen()

    vorhanden = gespeicherte_verkaeufe()
    bekannt = {str(v["id"]) for v in vorhanden}
    neue, _ = alle_verkaeufe_ab(_hoechste_id(vorhanden))

    # Auf Nummer sicher: die Gegenstelle koennte einen Datensatz erneut
    # liefern, dann darf er nicht ein zweites Mal in der Datei landen.
    frisch = [_schlank(v) for v in neue if str(v.get("id")) not in bekannt]

    if frisch:
        os.makedirs(SPEICHER, exist_ok=True)
        with open(VERKAEUFE_DATEI, "a", encoding="utf-8") as f:
            for verkauf in sorted(frisch, key=lambda v: int(v["id"])):
                f.write(json.dumps(verkauf, ensure_ascii=False) + "\n")

    return stamm, vorhanden + frisch, len(frisch)
