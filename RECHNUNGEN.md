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

Als geschäftlich eingetragen sind unter anderem Immoscout, ImmoWerbung,
Meike Weitzel, APCOA, Deutsche Post sowie sämtlicher Ladestrom fürs Auto
(`LADESTROM_MUSTER`:
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

## Regelmäßig laufen lassen

Für den Monatsabschluss, z. B. am 1. jedes Monats um 9 Uhr für den Vormonat —
via `crontab -e`:

```
0 9 1 * * cd /pfad/zum/repo && GMAIL_APP_PASSWORD='...' python3 rechnungen_sortieren.py --monat $(date -v-1m +%m) --jahr $(date -v-1m +%Y)
```
