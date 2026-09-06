"""Datenhaltung: Artikelstamm, Bewegungsjournal, Aliase.

Alles liegt als CSV im Ordner data/. Damit ist jede Aenderung ueber Git
nachvollziehbar und die Dateien lassen sich zur Not auch in Excel oeffnen.
"""

import csv
import os
import re
from dataclasses import dataclass, field
from datetime import date

BASIS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(BASIS, "data")

ARTIKEL_CSV = os.path.join(DATA, "artikel.csv")
BEWEGUNGEN_CSV = os.path.join(DATA, "bewegungen.csv")
ALIASE_CSV = os.path.join(DATA, "aliase.csv")
SAMMELREGELN_CSV = os.path.join(DATA, "sammelregeln.csv")
OFFEN_CSV = os.path.join(DATA, "offene_zuordnungen.csv")

ARTIKEL_FELDER = [
    "artikel_id",
    "nummer",
    "selektor",
    "name",
    "kategorie",
    "stueck_pro_gebinde",
    "mindestbestand",
    "lieferant",
    "ean",
    "aktiv",
]

BEWEGUNGS_FELDER = [
    "datum",
    "typ",
    "artikel_id",
    "menge",
    "beleg",
    "bezeichnung",
    "quelle",
    "notiz",
]

ALIAS_FELDER = ["quelle", "fremdbezeichnung", "artikel_id"]

SAMMELREGEL_FELDER = ["muster", "artikel_id", "name"]

# Bewegungsarten. Das Vorzeichen sagt, in welche Richtung der Bestand laeuft.
TYPEN = {
    "ANFANGSBESTAND": +1,
    "EINKAUF": +1,
    "VERKAUF": -1,
    "KORREKTUR": +1,   # Menge kann negativ sein
    "SCHWUND": -1,
}


@dataclass
class Sammelregel:
    """Fasst alle Belegzeilen, die ein Muster enthalten, zu einem Artikel zusammen.

    Gedacht fuer Sortimente mit staendig wechselnden Sorten, die im Automaten
    ohnehin nur einen Platz belegen - z.B. Elf Bar Pots. Jede Bezeichnung, die
    "ELF BAR" enthaelt, wird auf denselben Artikel gebucht, egal welche Sorte.
    """
    muster: str          # normalisierter Text, der in der Bezeichnung vorkommen muss
    artikel_id: str
    name: str = ""       # Anzeigename, falls der Artikel neu angelegt werden muss


@dataclass
class Artikel:
    artikel_id: str
    name: str
    nummer: str = ""     # eure interne Artikelnummer aus der Lagerliste
    selektor: str = ""   # Schachtnummer im Automaten Glueckstadt
    kategorie: str = ""
    stueck_pro_gebinde: int = 1
    mindestbestand: int = 0
    lieferant: str = ""
    ean: str = ""
    aktiv: bool = True


@dataclass
class Bewegung:
    datum: str
    typ: str
    artikel_id: str
    menge: int            # immer in Stueck, immer positiv ausser bei KORREKTUR
    beleg: str = ""       # Rechnungs-/Belegnummer
    bezeichnung: str = "" # Originaltext vom Beleg, zusammen mit beleg die Positionskennung
    quelle: str = ""      # z.B. selgros, rewe, automat
    notiz: str = ""


@dataclass
class Lager:
    artikel: dict = field(default_factory=dict)
    bewegungen: list = field(default_factory=list)
    aliase: dict = field(default_factory=dict)   # (quelle, normbezeichnung) -> artikel_id
    sammelregeln: list = field(default_factory=list)

    # ---------- Bestand ----------

    def bestand(self):
        """Aktueller Bestand je Artikel in Stueck."""
        werte = {aid: 0 for aid in self.artikel}
        for b in self.bewegungen:
            vz = TYPEN.get(b.typ, 0)
            werte[b.artikel_id] = werte.get(b.artikel_id, 0) + vz * b.menge
        return werte

    def positionen(self):
        """Bereits verbuchte Belegpositionen als (Beleg, normierte Bezeichnung).

        Die Pruefung laeuft bewusst auf Positions- und nicht auf Belegebene:
        Wird eine Rechnung erneut eingelesen, weil eine Zeile beim ersten Mal
        nicht zugeordnet werden konnte, sollen die uebrigen Zeilen als Dublette
        erkannt werden - die offene Zeile aber durchlaufen.
        """
        return {
            (b.beleg, normalisieren(b.bezeichnung))
            for b in self.bewegungen if b.beleg
        }

    def buchen(self, bewegung):
        if bewegung.typ not in TYPEN:
            raise ValueError(f"Unbekannte Bewegungsart: {bewegung.typ}")
        if bewegung.artikel_id not in self.artikel:
            raise ValueError(f"Unbekannter Artikel: {bewegung.artikel_id}")
        self.bewegungen.append(bewegung)

    def naechste_artikel_id(self, name):
        """Erzeugt eine sprechende, eindeutige ID aus dem Artikelnamen."""
        basis = normalisieren(name).lower().replace(" ", "-")
        basis = re.sub(r"[^a-z0-9-]", "", basis)[:32].strip("-") or "artikel"
        kandidat = basis
        n = 2
        while kandidat in self.artikel:
            kandidat = f"{basis}-{n}"
            n += 1
        return kandidat


def normalisieren(text):
    """Vereinheitlicht Bezeichnungen fuer den Abgleich.

    Kassenbons schreiben denselben Artikel jedes Mal etwas anders
    ("Coca-Cola 0,33l DS" / "COCA COLA 0.33 DS"). Hier wird alles auf eine
    gemeinsame Form gebracht, damit der Abgleich ueberhaupt greifen kann.
    """
    t = (text or "").upper()
    for alt, neu in (("Ä", "AE"), ("Ö", "OE"), ("Ü", "UE"), ("ß", "SS")):
        t = t.replace(alt, neu)
    t = t.replace(",", ".")
    t = re.sub(r"[^A-Z0-9. ]+", " ", t)
    t = re.sub(r"\s+", " ", t)
    return t.strip()


# ---------- Lesen ----------

def _lies_csv(pfad):
    if not os.path.exists(pfad):
        return []
    with open(pfad, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def laden():
    lager = Lager()

    for zeile in _lies_csv(ARTIKEL_CSV):
        a = Artikel(
            artikel_id=zeile["artikel_id"].strip(),
            name=zeile["name"].strip(),
            nummer=zeile.get("nummer", "").strip(),
            selektor=zeile.get("selektor", "").strip(),
            kategorie=zeile.get("kategorie", "").strip(),
            stueck_pro_gebinde=int(zeile.get("stueck_pro_gebinde") or 1),
            mindestbestand=int(zeile.get("mindestbestand") or 0),
            lieferant=zeile.get("lieferant", "").strip(),
            ean=zeile.get("ean", "").strip(),
            aktiv=(zeile.get("aktiv", "ja").strip().lower() in ("ja", "1", "true", "")),
        )
        lager.artikel[a.artikel_id] = a

    for zeile in _lies_csv(BEWEGUNGEN_CSV):
        lager.bewegungen.append(Bewegung(
            datum=zeile["datum"].strip(),
            typ=zeile["typ"].strip().upper(),
            artikel_id=zeile["artikel_id"].strip(),
            menge=int(zeile["menge"]),
            beleg=zeile.get("beleg", "").strip(),
            bezeichnung=zeile.get("bezeichnung", "").strip(),
            quelle=zeile.get("quelle", "").strip(),
            notiz=zeile.get("notiz", "").strip(),
        ))

    for zeile in _lies_csv(SAMMELREGELN_CSV):
        regel = Sammelregel(
            muster=normalisieren(zeile["muster"]),
            artikel_id=zeile["artikel_id"].strip(),
            name=zeile.get("name", "").strip(),
        )
        lager.sammelregeln.append(regel)
        # Der Sammelartikel wird bei Bedarf angelegt, damit eine Regel auch
        # dann greift, wenn die Sorte noch nie im Lager war.
        if regel.artikel_id not in lager.artikel:
            lager.artikel[regel.artikel_id] = Artikel(
                artikel_id=regel.artikel_id,
                name=regel.name or regel.artikel_id,
            )

    for zeile in _lies_csv(ALIASE_CSV):
        schluessel = (zeile["quelle"].strip().lower(),
                      normalisieren(zeile["fremdbezeichnung"]))
        lager.aliase[schluessel] = zeile["artikel_id"].strip()

    return lager


# ---------- Schreiben ----------

def _schreib_csv(pfad, felder, zeilen):
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=felder)
        w.writeheader()
        w.writerows(zeilen)


def speichern(lager):
    _schreib_csv(ARTIKEL_CSV, ARTIKEL_FELDER, [
        {
            "artikel_id": a.artikel_id,
            "nummer": a.nummer,
            "selektor": a.selektor,
            "name": a.name,
            "kategorie": a.kategorie,
            "stueck_pro_gebinde": a.stueck_pro_gebinde,
            "mindestbestand": a.mindestbestand,
            "lieferant": a.lieferant,
            "ean": a.ean,
            "aktiv": "ja" if a.aktiv else "nein",
        }
        for a in sorted(lager.artikel.values(), key=lambda x: x.name.lower())
    ])

    _schreib_csv(BEWEGUNGEN_CSV, BEWEGUNGS_FELDER, [
        {
            "datum": b.datum,
            "typ": b.typ,
            "artikel_id": b.artikel_id,
            "menge": b.menge,
            "beleg": b.beleg,
            "bezeichnung": b.bezeichnung,
            "quelle": b.quelle,
            "notiz": b.notiz,
        }
        for b in sorted(lager.bewegungen, key=lambda x: (x.datum, x.artikel_id))
    ])


def sammelregeln_speichern(lager):
    _schreib_csv(SAMMELREGELN_CSV, SAMMELREGEL_FELDER, [
        {"muster": r.muster, "artikel_id": r.artikel_id, "name": r.name}
        for r in lager.sammelregeln
    ])


def alias_speichern(lager):
    zeilen = []
    for (quelle, fremd), aid in sorted(lager.aliase.items()):
        zeilen.append({"quelle": quelle, "fremdbezeichnung": fremd, "artikel_id": aid})
    _schreib_csv(ALIASE_CSV, ALIAS_FELDER, zeilen)


def heute():
    return date.today().isoformat()
