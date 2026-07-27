# Rechnungen sortieren

`rechnungen_sortieren.py` arbeitet den Gmail-Posteingang durch, legt jede Rechnung
im iCloud-Steuerordner ab und erstellt den Monatsentwurf an den Rechnungseingang.

Das Skript muss **lokal auf dem Mac** laufen, auf dem iCloud Drive eingerichtet ist.

## Ordnerstruktur

Alle Rechnungen, die **an dich** gehen, liegen unter `Eingangsrechnungen`,
unterteilt nach Jahr und Monat:

```
iCloud Drive/Steuer/
└── Eingangsrechnungen/
    ├── 2025/
    │   ├── 01_Januar/
    │   │   ├── Geschäftlich/
    │   │   └── Privat/
    │   ├── 02_Februar/
    │   …
    │   └── 12_Dezember/
    └── 2026/
        …
```

Die Monatsnummer steht vorn, damit die Ordner chronologisch und nicht
alphabetisch sortieren — sonst käme April vor Februar.

Struktur ab 2025 bis zum laufenden Jahr anlegen:

```bash
python3 ordner_anlegen.py
```

Das Skript ist wiederholbar: vorhandene Ordner und Dateien bleiben unberührt,
es ergänzt nur was fehlt. Ein neues Jahr legst du später mit demselben Befehl
an. Vorher ansehen, was passieren würde:

```bash
python3 ordner_anlegen.py --dry-run
```

Rechnungen, deren Zuordnung unklar ist, landen im jeweiligen Monat unter
`_Zu_pruefen`. Dieser Ordner entsteht nur, wenn er gebraucht wird.

Ausgangsrechnungen an ProVend liegen bewusst **nicht** hier — die werden nur
in Gmail einsortiert (siehe unten).

## Einmalige Einrichtung

1. **Gmail-App-Passwort erzeugen** (normales Passwort funktioniert bei IMAP nicht):
   - https://myaccount.google.com/apppasswords öffnen
   - mit `hegebehrens.rechnung@gmail.com` anmelden
   - App-Passwort erzeugen, die 16 Zeichen kopieren

2. **IMAP in Gmail aktivieren**: Einstellungen → „Weiterleitung und POP/IMAP" →
   „IMAP aktivieren"

3. **Zugangsdaten setzen:**
   ```bash
   export GMAIL_APP_PASSWORD='xxxxxxxxxxxxxxxx'
   ```

## Benutzung

Erst ein Testlauf — der zeigt nur an, was passieren würde, und schreibt nichts:

```bash
python3 rechnungen_sortieren.py --dry-run
```

Sieht das Ergebnis richtig aus, dann echt laufen lassen:

```bash
python3 rechnungen_sortieren.py
```

Ohne weitere Angaben geht das Skript über den **gesamten Bestand** in `INBOX`
und `INBOX/Icloud Archiv`. Nur ein einzelner Monat:

```bash
python3 rechnungen_sortieren.py --jahr 2026 --monat 6
```

## Stichtag: was übermittelt wird

Abgelegt und einsortiert wird **jede** gefundene Rechnung, egal wie alt.

In den Entwurf an DATEV kommen dagegen nur Rechnungen **ab dem Stichtag**,
aktuell der **1. Juni 2026** (`STICHTAG` im Skript). Ältere sind dort bereits
eingereicht — sie werden nur weggeräumt. Das Skript meldet beim Lauf, wie viele
das betraf. Anderer Stichtag für einen einzelnen Lauf:

```bash
python3 rechnungen_sortieren.py --stichtag 01.01.2026
```

## Große Anhänge: mehrere Mails

Übersteigen die Anhänge **19,9 MB**, legt das Skript eine weitere Mail an und
verteilt die restlichen Belege dorthin. Der Betreff wird dann nummeriert:
„Rechnungseingang ab Juni 2026 (Teil 1 von 3)". Eine einzelne Rechnung wird nie
auseinandergerissen — ihre Belege bleiben zusammen in einer Mail.

Zwei Grenzen wirken dabei zusammen:

| Konstante | Wert | Zweck |
|---|---|---|
| `MAX_ANHANG_BYTES` | 19,9 MB | die gewünschte Regel, gemessen an der Rohgröße der Dateien |
| `MAX_MAIL_BYTES` | 24 MB | Schutzgrenze für die fertige Mail |

Die zweite Grenze ist nötig, weil Anhänge in einer Mail Base64-kodiert werden
und dabei **rund 35 % größer** werden. 19,9 MB Dateien ergäben etwa 27 MB
Mailgröße — Gmail nimmt aber nur 25 MB an. In der Praxis greift daher meist die
Schutzgrenze zuerst und teilt bei ungefähr 17,5 MB Rohdaten.

Wer die volle 19,9-MB-Regel ohne Rücksicht darauf will, setzt `MAX_MAIL_BYTES`
hoch — dann können die Mails allerdings am Gmail-Limit scheitern.

## Was das Skript macht

1. durchsucht Posteingang und iCloud-Archiv nach Rechnungen
2. ordnet jede Rechnung privat oder geschäftlich zu
3. legt die Anhänge ab unter
   `Eingangsrechnungen/<Jahr>/<MM_Monat>/Privat` bzw. `.../Geschäftlich`
   — benannt nach dem Muster `2026-07-03_Absender_Rechnung.pdf`
4. setzt in Gmail das Label `Rechnungen/Privat` bzw. `Rechnungen/Geschäftlich`
   — ProVend-Rechnungen stattdessen `ProVend Deutschland/Rechnungen an ProVend`
5. legt im Entwürfe-Ordner eine Übersicht an, adressiert an den
   DATEV-Rechnungseingang, mit den Belegen ab Stichtag im Anhang
   (ohne ProVend) — bei Bedarf auf mehrere Mails verteilt

## Erkennungsregeln

Eine Mail gilt nur dann als Rechnung, wenn **beides** zutrifft: ein Stichwort
(Rechnung, Invoice, Beleg, Quittung …) **und** ein Anhang (PDF, XML, Bild).
So rutschen Werbemails mit dem Wort „Rechnung" nicht durch.

Die Zuordnung privat/geschäftlich läuft über zwei Musterlisten im Skript:
`GESCHAEFTLICH_MUSTER` und `PRIVAT_MUSTER`. **Diese Listen sind der Stellhebel** —
trag dort deine Lieferanten und Anbieter ein, dann trifft das Skript die
Zuordnung zuverlässig.

**Alles rund um Immobilien zählt geschäftlich.** Das steckt in
`IMMOBILIEN_MUSTER` und greift nicht nur auf Firmennamen, sondern auf das
Fachvokabular: Immobilie, Immo…, Makler, Exposé, Grundstück, Grundbuch,
Teilungserklärung, Hausverwaltung, Energieausweis, Wertermittlung,
Verkehrswert, Mietvertrag, Nebenkostenabrechnung, Notar, IVD, Stadtmarketing,
IndustrialPort, Werbeschild. Damit fällt auch ein neuer Lieferant richtig,
solange sein Betreff oder Text einen dieser Begriffe führt.

Bewusst **nicht** in der Liste stehen `wohnung` und `kaufvertrag`: die kämen
auch in privaten Rechnungen vor — Möbelkauf, Gebrauchtwagen — und würden diese
fälschlich ins Geschäftliche ziehen. Zwei Tests halten das fest.

Weiter als geschäftlich eingetragen sind unter anderem Meike Weitzel, APCOA,
Deutsche Post sowie sämtlicher Ladestrom fürs Auto (`LADESTROM_MUSTER`:
EnBW mobility+, Ionity, EWE Go, Shell Recharge, Aral Pulse, Allego, Tesla,
Qwello, ladecloud … sowie Stichwörter wie Ladevorgang, Ladesäule, Wallbox).

Als privat eingetragen sind unter anderem CHRIST, Condor, Netflix, Zalando
und Versicherungen.

Ein Muster greift ab Wortanfang, deshalb steht dort `christ.de` und nicht
`christ` — sonst würde jede Mail von einem „Christian" oder „Christoph" als
privat einsortiert.

Passt eine Rechnung auf keine der beiden Listen, wird **nicht geraten**. Sie landet
in `Steuer/<Jahr>/_Zu_pruefen`, bekommt kein Gmail-Label und erscheint im Entwurf
unter „NOCH ZU PRÜFEN". Bei Steuerunterlagen ist eine offene Zuordnung billiger
als eine falsche.

## ProVend Deutschland

ProVend läuft komplett getrennt vom übrigen Rechnungslauf und hat einen eigenen
Ordner:

```
ProVend Deutschland
└── Rechnungen an ProVend
```

Rechnungen mit ProVend-Bezug werden **nur weggeräumt**:

- Label `ProVend Deutschland/Rechnungen an ProVend` wird gesetzt
- **keine** Ablage im iCloud-Steuerordner
- **kein** Eintrag und **kein** Anhang im Entwurf an DATEV — sie werden nicht versendet

Erkannt wird ProVend über `PROVEND_MUSTER`, und zwar in Absender **und**
Empfänger. Das ist wichtig, weil eine Rechnung, die *an* ProVend geht, die
Adresse im To/Cc trägt und nicht im Absender.

**Selgros zählt zu ProVend.** Die Einkäufe laufen dort, deshalb steht `selgros`
mit im Muster — sie werden gleich behandelt, ob sie nun über ProVend
weitergeleitet wurden oder direkt von Selgros kommen.

Beim Ausführen meldet das Skript in der Konsole, wie viele ProVend-Rechnungen
einsortiert und aus dem Entwurf herausgehalten wurden — in der Mail selbst
taucht davon nichts auf.

Hinweis: Rechnungen, die du selbst an ProVend geschickt hast, liegen im
Gesendet-Ordner, nicht im Posteingang. Das Skript durchsucht den Posteingang;
ausgehende Rechnungen erfasst es nur, wenn du dich selbst ins Cc gesetzt hast.

## Tests

Die Erkennungsregeln sind durch Tests abgesichert:

```bash
python3 test_rechnungen.py
```

Wenn du die Musterlisten erweiterst, trag dort am besten einen Testfall nach.
Die Muster greifen ab Wortanfang und tolerieren Trennzeichen — `ewe go` findet
auch `ewe-go.de`, `ladestrom` auch `Ladestromabrechnung`, aber `elli` nicht
mehr das `elli` in `voellig`.

## Automatisch laufen lassen

```bash
./automation/installieren.sh
```

Das Skript fragt einmalig nach dem Gmail-App-Passwort, legt es in der
**macOS-Keychain** ab und richtet zwei launchd-Jobs ein:

| Job | Wann | Was |
|---|---|---|
| `…rechnungen.sortieren` | täglich 7:00 und 19:00 Uhr | einsortieren und ablegen, **keine** Entwürfe |
| `…rechnungen.entwurf` | am 1. jedes Monats, 8:00 Uhr | Entwurf für den **Vormonat**, ohne erneute Ablage |

Die Trennung ist Absicht: Liefe der Entwurf zweimal täglich mit, lägen nach
einer Woche vierzehn Entwürfe mit überlappendem Inhalt im Postfach. Sortiert
und abgelegt wird trotzdem zweimal am Tag, sodass nichts liegen bleibt.

Der Entwurfslauf nimmt genau den **Vormonat** (`--jahr`/`--monat`) und läuft
mit `--nur-entwurf`. Beides ist notwendig: über den gesamten Bestand enthielte
der Entwurf jeden Monat auch alles Vorherige noch einmal, und ohne
`--nur-entwurf` schriebe er die Belege ein zweites Mal in den Steuerordner.

Andere Zeiten? Die `StartCalendarInterval`-Blöcke in
`automation/*.plist` anpassen und `installieren.sh` erneut ausführen.

### Bedienung

```bash
./automation/installieren.sh --status      # läuft es?
./automation/installieren.sh --entfernen   # wieder abbauen
tail -f ~/Library/Logs/Rechnungen/rechnungen.log

# Lauf sofort auslösen, ohne auf die Uhrzeit zu warten
launchctl kickstart -p gui/$(id -u)/de.hegebehrens.rechnungen.sortieren
```

### Warum die Keychain

Das App-Passwort steht **nicht** in der plist und in keiner Datei im
Repository — dort wäre es für jeden lesbaren Prozess im Klartext sichtbar.
Der Wrapper holt es zur Laufzeit mit `security find-generic-password` und gibt
es nur als Umgebungsvariable an den Lauf weiter.

Manuell hinterlegen oder ändern:

```bash
security add-generic-password -a "$USER" -s gmail-rechnungen -w 'App-Passwort' -U
```

### Doppelte Ablage

Ein wiederholter Lauf darf dieselbe Rechnung nicht erneut ablegen — sonst
lägen nach einer Woche vierzehn Kopien jedes Belegs im Steuerordner.

Das Skript prüft deshalb vor jedem Lauf, welche Message-IDs bereits in einem
der Ziel-Label liegen, und überspringt diese. Der Zustand steht damit im
Postfach selbst; es gibt keine Zustandsdatei, die verloren gehen oder
veralten kann. Nach einem Rechnerwechsel funktioniert es unverändert weiter.

Eine Mail ohne Message-ID wird immer mitgenommen — doppelt abgelegt ist
ärgerlich, übersehen wäre schlimmer. Wer bewusst alles noch einmal ablegen
will, nimmt `--erneut`.

**Der Entwurf verwendet diese Filterung bewusst nicht.** Sie steuert allein,
was abgelegt und gelabelt wird. Würde der Entwurf ebenfalls nur „neue"
Rechnungen aufnehmen, fände er nach dem zweimal täglichen Sortierlauf nie
wieder etwas — der Monatsentwurf bliebe für immer leer, ohne dass es
auffiele. Er arbeitet deshalb über den vollen Zeitraum.

## Ablage anderswo erledigen

Soll das Wegsortieren in iCloud woanders passieren, übernimmt
`--nur-entwurf` den Rest:

```bash
python3 rechnungen_sortieren.py --jahr 2026 --monat 6 --nur-entwurf
```

Dann werden weder Dateien geschrieben noch Label gesetzt — es entstehen nur
die Entwürfe. Ein Steuerordner muss dafür nicht existieren, das Skript läuft
also auch auf einem Rechner ohne iCloud Drive.

### Wenn der Mac schlief

launchd holt einen verpassten Lauf beim Aufwachen nach. Ist der Mac zur
geplanten Zeit ganz aus, fällt der Lauf aus — der nächste holt alles nach,
weil ohnehin über den gesamten Bestand gearbeitet wird.
