"""Zuordnung fremder Bezeichnungen (Kassenbon, Rechnung, Automat) zu Artikeln.

Das ist das Herzstueck beim Einlesen von Supermarkt-Belegen: Auf dem Bon steht
"COCA COLA 0,33 DS", im Artikelstamm heisst es "Coca-Cola 0,33l Dose". Der
Abgleich laeuft in drei Stufen und lernt dabei dazu.
"""

import difflib

from .daten import normalisieren

# Ab diesem Aehnlichkeitswert gilt ein Treffer als sicher genug, um ihn
# vorzuschlagen. Darunter landet die Zeile in den offenen Zuordnungen.
SCHWELLE = 0.82


def zuordnen(lager, quelle, fremdbezeichnung, ean=""):
    """Liefert (artikel_id, guete, methode).

    guete ist 1.0 bei einem eindeutigen Treffer, sonst der Aehnlichkeitswert.
    artikel_id ist None, wenn nichts Passendes gefunden wurde.
    """
    quelle = (quelle or "").strip().lower()
    norm = normalisieren(fremdbezeichnung)

    # 1. Gelernter Alias fuer genau diese Quelle - der sicherste Fall.
    treffer = lager.aliase.get((quelle, norm))
    if treffer and treffer in lager.artikel:
        return treffer, 1.0, "alias"

    # 2. Sammelregel. Sie steht bewusst vor Aehnlichkeit und EAN: bei einem
    #    Sammelartikel sollen gerade NICHT die einzelnen Sorten auseinander
    #    laufen, auch wenn eine Sorte zufaellig gut auf einen anderen Artikel
    #    passen wuerde.
    regel = sammelregel_treffer(lager, fremdbezeichnung)
    if regel:
        return regel.artikel_id, 1.0, f"sammelartikel:{regel.muster}"

    # 3. Alias einer anderen Quelle (Bezeichnungen wiederholen sich oft).
    for (q, n), aid in lager.aliase.items():
        if n == norm and aid in lager.artikel:
            return aid, 1.0, f"alias:{q}"

    # 4. EAN, falls der Beleg eine mitliefert.
    if ean:
        for a in lager.artikel.values():
            if a.ean and a.ean == ean.strip():
                return a.artikel_id, 1.0, "ean"

    # 5. Namensaehnlichkeit gegen den Artikelstamm. Sammelartikel bleiben aussen
    #    vor - dort entscheidet allein die Regel.
    sammel_ids = {r.artikel_id for r in lager.sammelregeln}
    namen = {
        normalisieren(a.name): a.artikel_id
        for a in lager.artikel.values() if a.artikel_id not in sammel_ids
    }
    if namen:
        beste = difflib.get_close_matches(norm, list(namen), n=1, cutoff=0.0)
        if beste:
            guete = difflib.SequenceMatcher(None, norm, beste[0]).ratio()
            if guete >= SCHWELLE:
                return namen[beste[0]], guete, "aehnlichkeit"
            return None, guete, "unsicher"

    return None, 0.0, "unbekannt"


def sammelregel_treffer(lager, bezeichnung):
    """Erste Sammelregel, deren Muster in der Bezeichnung vorkommt.

    Leerzeichen werden dabei ignoriert: Auf Belegen steht mal "Elf Bar",
    mal "Elfbar" - beides soll dieselbe Regel treffen.
    """
    norm = normalisieren(bezeichnung).replace(" ", "")
    for regel in lager.sammelregeln:
        muster = regel.muster.replace(" ", "")
        if muster and muster in norm:
            return regel
    return None


def alias_lernen(lager, quelle, fremdbezeichnung, artikel_id):
    """Merkt sich eine Zuordnung, damit derselbe Beleg kuenftig sofort passt."""
    schluessel = ((quelle or "").strip().lower(), normalisieren(fremdbezeichnung))
    lager.aliase[schluessel] = artikel_id
