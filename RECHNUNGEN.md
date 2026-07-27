# Rechnungen sortieren

`rechnungen_sortieren.py` arbeitet den Gmail-Posteingang durch, legt jede Rechnung
im iCloud-Steuerordner ab und erstellt den Monatsentwurf an den Rechnungseingang.

Das Skript muss **lokal auf dem Mac** laufen, auf dem iCloud Drive eingerichtet ist.

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

Ein anderer Monat:

```bash
python3 rechnungen_sortieren.py --jahr 2026 --monat 6
```

## Was das Skript macht

1. durchsucht den Posteingang nach Rechnungen des Monats
2. ordnet jede Rechnung privat oder geschäftlich zu
3. legt die Anhänge ab unter
   `iCloud Drive/Steuer/<Jahr>/Privat` bzw. `.../Geschäftlich`
   — benannt nach dem Muster `2026-07-03_Absender_Rechnung.pdf`
4. setzt in Gmail das Label `Rechnungen/Privat` bzw. `Rechnungen/Geschäftlich`
5. legt im Entwürfe-Ordner eine Monatsübersicht an, adressiert an den
   DATEV-Rechnungseingang, mit allen Belegen im Anhang

## Erkennungsregeln

Eine Mail gilt nur dann als Rechnung, wenn **beides** zutrifft: ein Stichwort
(Rechnung, Invoice, Beleg, Quittung …) **und** ein Anhang (PDF, XML, Bild).
So rutschen Werbemails mit dem Wort „Rechnung" nicht durch.

Die Zuordnung privat/geschäftlich läuft über zwei Musterlisten im Skript:
`GESCHAEFTLICH_MUSTER` und `PRIVAT_MUSTER`. **Diese Listen sind der Stellhebel** —
trag dort deine Lieferanten und Anbieter ein, dann trifft das Skript die
Zuordnung zuverlässig.

Als geschäftlich eingetragen sind unter anderem Immoscout, Meike Weitzel und
sämtlicher Ladestrom fürs Auto (`LADESTROM_MUSTER`: EnBW mobility+, Ionity,
EWE Go, Shell Recharge, Aral Pulse, Allego, Tesla … sowie Stichwörter wie
Ladevorgang, Ladesäule, Wallbox).

Passt eine Rechnung auf keine der beiden Listen, wird **nicht geraten**. Sie landet
in `Steuer/<Jahr>/_Zu_pruefen`, bekommt kein Gmail-Label und erscheint im Entwurf
unter „NOCH ZU PRÜFEN". Bei Steuerunterlagen ist eine offene Zuordnung billiger
als eine falsche.

## Nur sortieren, nicht hochladen

Absender in `NICHT_HOCHLADEN_MUSTER` — aktuell **Provend** — werden in Gmail
ganz normal einsortiert, aber:

- die Belege landen **nicht** im iCloud-Steuerordner
- sie hängen **nicht** am Entwurf an DATEV

Im Entwurf erscheinen sie am Ende unter „NICHT ÜBERMITTELT – nur einsortiert",
damit im Monatsabschluss sichtbar bleibt, dass sie bewusst ausgelassen wurden
und nicht etwa vergessen.

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
