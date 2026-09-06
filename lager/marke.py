"""Markenfarben und Logo fuer die Bestandsliste.

Die Farben werden aus dem Logo abgeleitet, damit Bericht und E-Mail ohne
zusaetzliche Pflege zum Erscheinungsbild passen. Ueber die Einstellungen
lassen sie sich jederzeit ueberschreiben.
"""

import colorsys
import os

from .daten import DATA

LOGO_ORDNER = os.path.join(DATA, "marke")
LOGO_NAMEN = ("logo.png", "logo.jpg", "logo.jpeg", "logo.gif", "logo.webp")

# Neutrale Ausweichfarben, solange kein Logo hinterlegt ist.
STANDARD = {
    "primaer": "1F2937",    # Kopfzeilen, Titel
    "akzent": "2563EB",     # Hervorhebungen, Links
    "hell": "F3F4F6",       # Zebrastreifen, Flaechen
    "text": "111827",
}

# Ampelfarben bleiben unabhaengig von der Marke - Rot muss Rot bleiben.
STATUS_FARBEN = {
    "MINUS": "DC2626",
    "LEER": "EF4444",
    "NACHBESTELLEN": "F59E0B",
    "KNAPP": "FCD34D",
    "OK": "10B981",
}


def logo_pfad():
    """Pfad zum hinterlegten Logo, oder None."""
    for name in LOGO_NAMEN:
        pfad = os.path.join(LOGO_ORDNER, name)
        if os.path.exists(pfad):
            return pfad
    return None


def _hex(rgb):
    return "".join(f"{kanal:02X}" for kanal in rgb[:3])


def _luminanz(rgb):
    """Wahrgenommene Helligkeit 0..1 - entscheidet ueber Schriftfarbe."""
    r, g, b = (kanal / 255 for kanal in rgb[:3])
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def textfarbe_auf(hexfarbe):
    """Schwarz oder Weiss, je nachdem was auf der Flaeche lesbar ist."""
    rgb = tuple(int(hexfarbe[i:i + 2], 16) for i in (0, 2, 4))
    return "111827" if _luminanz(rgb) > 0.55 else "FFFFFF"


def aufhellen(hexfarbe, anteil=0.9):
    """Mischt eine Farbe mit Weiss - fuer Flaechen hinter Text."""
    rgb = tuple(int(hexfarbe[i:i + 2], 16) for i in (0, 2, 4))
    return _hex(tuple(round(kanal + (255 - kanal) * anteil) for kanal in rgb))


def abdunkeln(hexfarbe, anteil=0.45):
    """Mischt eine Farbe mit Schwarz."""
    rgb = tuple(int(hexfarbe[i:i + 2], 16) for i in (0, 2, 4))
    return _hex(tuple(round(kanal * (1 - anteil)) for kanal in rgb))


def farben_aus_logo(pfad):
    """Bestimmt Primaer- und Akzentfarbe aus den Logofarben.

    Die meisten Logos bestehen aus einem dunklen Neutralton fuer die Schrift
    und einer kraeftigen Schmuckfarbe. Genau so wird hier zugeordnet: das
    dunkle Neutral traegt Kopfzeilen und Ueberschriften, die Schmuckfarbe
    setzt die Akzente. Fehlt eins von beidem, wird es aus dem anderen
    abgeleitet.
    """
    try:
        from PIL import Image
    except ImportError:
        return None

    with Image.open(pfad) as bild:
        bild = bild.convert("RGBA")
        bild.thumbnail((200, 200))
        pixel = [p for p in bild.getdata() if p[3] > 128]

    bunt, neutral = {}, {}
    for r, g, b, _ in pixel:
        _, helligkeit, saettigung = colorsys.rgb_to_hls(r / 255, g / 255, b / 255)
        if helligkeit > 0.93:          # Papierweiss ist keine Markenfarbe
            continue
        # Grobes Raster, damit Kantenglaettung und Verlaeufe zusammenfallen.
        schluessel = (round(r / 24), round(g / 24), round(b / 24))
        ziel = bunt if saettigung >= 0.25 and helligkeit >= 0.15 else neutral
        eintrag = ziel.setdefault(schluessel, [0, (r, g, b)])
        eintrag[0] += 1

    if not (bunt or neutral):
        return None

    akzent = max(bunt.values(), key=lambda e: e[0])[1] if bunt else None
    # Als Primaerfarbe der dunkelste haeufige Neutralton.
    haeufige_neutrale = sorted(neutral.values(), key=lambda e: -e[0])[:4]
    primaer = min(haeufige_neutrale, key=lambda e: _luminanz(e[1]))[1] if haeufige_neutrale else None

    if akzent is None:
        akzent = primaer
    if primaer is None or _luminanz(primaer) > 0.45:
        primaer = tuple(int(abdunkeln(_hex(akzent), 0.55)[i:i + 2], 16) for i in (0, 2, 4))

    return {"primaer": _hex(primaer), "akzent": _hex(akzent)}


def palette(lager=None):
    """Farbpalette: Einstellungen schlagen Logo, Logo schlaegt Standard."""
    farben = dict(STANDARD)

    pfad = logo_pfad()
    if pfad:
        abgeleitet = farben_aus_logo(pfad)
        if abgeleitet:
            farben.update(abgeleitet)
            farben["hell"] = aufhellen(abgeleitet["akzent"], 0.93)

    if lager is not None:
        for name in ("primaer", "akzent", "hell", "text"):
            wert = lager.einstellungen.get(f"farbe_{name}", "").strip().lstrip("#").upper()
            if len(wert) == 6:
                farben[name] = wert

    return farben


def logo_fuer_einbettung(breite=280):
    """Verkleinerte Kopie des Logos fuer Excel und E-Mail.

    Das Original ist fuer den Druck gedacht und waere als Mailanhang unnoetig
    schwer. Die Kopie liegt im Cache-Ordner und wird nur neu erzeugt, wenn sie
    fehlt oder aelter als das Original ist.
    """
    quelle = logo_pfad()
    if not quelle:
        return None, (0, 0)

    ziel = os.path.join(LOGO_ORDNER, f"logo_{breite}.png")
    if not os.path.exists(ziel) or os.path.getmtime(ziel) < os.path.getmtime(quelle):
        try:
            from PIL import Image
        except ImportError:
            return quelle, (0, 0)
        with Image.open(quelle) as bild:
            bild = bild.convert("RGBA")
            rand = bild.getbbox()
            if rand:
                bild = bild.crop(rand)
            hoehe = round(bild.height * breite / bild.width)
            klein = bild.resize((breite, hoehe), Image.LANCZOS)
            # Ein zwei- bis dreifarbiges Logo braucht keine Millionen Farben.
            # Die Palette spart rund 80 Prozent Dateigroesse, was im
            # E-Mail-Anhang und im Versandpaket spuerbar ist.
            try:
                klein = klein.quantize(colors=64, method=Image.FASTOCTREE)
            except (ValueError, OSError):
                pass
            klein.save(ziel, optimize=True)

    try:
        from PIL import Image
        with Image.open(ziel) as bild:
            return ziel, bild.size
    except ImportError:
        return ziel, (breite, breite)
