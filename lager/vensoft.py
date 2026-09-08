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
