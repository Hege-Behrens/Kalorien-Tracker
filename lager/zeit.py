"""Zeitstempel aus Belegzeilen lesen.

Verkaufsexporte liefern das Datum in ganz unterschiedlichen Formaten. Fuer den
Stichtag muss aber sekundengenau entschieden werden, ob eine Zeile schon im
Anfangsbestand steckt oder noch gebucht werden muss.
"""

from datetime import datetime

# Reihenfolge = Priorisierung. Deutsche Formate stehen mit drin, weil
# Automatensoftware sie haeufig ausgibt.
FORMATE = [
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d",
    "%d.%m.%Y %H:%M:%S",
    "%d.%m.%Y %H:%M",
    "%d.%m.%Y",
    "%d.%m.%y %H:%M:%S",
    "%d.%m.%y %H:%M",
    "%d.%m.%y",
    "%d/%m/%Y %H:%M:%S",
    "%d/%m/%Y %H:%M",
    "%d/%m/%Y",
]

NUR_DATUM = {"%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y", "%d/%m/%Y"}


def lesen(text):
    """Liefert (zeitpunkt, hat_uhrzeit). Bei unlesbarem Text (None, False)."""
    text = (text or "").strip()
    if not text:
        return None, False
    text = text.replace("Z", "").split(".")[0] if "T" in text and text.count(".") == 1 else text
    for format_ in FORMATE:
        try:
            return datetime.strptime(text, format_), format_ not in NUR_DATUM
        except ValueError:
            continue
    return None, False


def zusammensetzen(datum_text, zeit_text):
    """Fuegt getrennte Datums- und Uhrzeitspalten zusammen."""
    zeitpunkt, hat_uhrzeit = lesen(datum_text)
    if zeitpunkt is None:
        return None, False
    if hat_uhrzeit or not (zeit_text or "").strip():
        return zeitpunkt, hat_uhrzeit

    for format_ in ("%H:%M:%S", "%H:%M"):
        try:
            uhrzeit = datetime.strptime(zeit_text.strip(), format_).time()
            return zeitpunkt.replace(hour=uhrzeit.hour, minute=uhrzeit.minute,
                                     second=uhrzeit.second), True
        except ValueError:
            continue
    return zeitpunkt, False
