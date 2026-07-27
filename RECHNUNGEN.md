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
   — ProVend-Rechnungen stattdessen `ProVend Deutschland/Rechnungen an ProVend`
5. legt im Entwürfe-Ordner eine Monatsübersicht an, adressiert an den
   DATEV-Rechnungseingang, mit allen Belegen im Anhang (ohne ProVend)

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
