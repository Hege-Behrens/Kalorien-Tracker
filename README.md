# Lagerverwaltung Verkaufsautomaten

Führt **einen** Lagerbestand: Rechnungen erhöhen ihn, die Verkaufszahlen der
Automaten mindern ihn. Meldet, was nachbestellt werden muss, und verschickt
wöchentlich eine Bestandsliste per E-Mail.

Bestände je Automat werden bewusst **nicht** geführt — das sagt die
Verkaufssoftware der Automaten bereits.

## Prinzip

Der Bestand wird nicht als Zahl fortgeschrieben, sondern als Summe aller
Bewegungen berechnet. Jede Buchung steht mit Datum, Beleg und Herkunft in
`data/bewegungen.csv`. Dadurch ist jede Zahl nachvollziehbar und ein Fehler
lässt sich korrigieren, ohne dass alles Folgende kippt.

| Bewegungsart | Wirkung | Herkunft |
|---|---|---|
| `ANFANGSBESTAND` | + | Inventur-Excel |
| `EINKAUF` | + | Rechnung / Kassenbon |
| `VERKAUF` | − | Automaten-Export |
| `KORREKTUR` | ± | gezählter Bestand |
| `SCHWUND` | − | Bruch, Ablauf, Diebstahl |

## Dateien

```
data/artikel.csv              Artikelstamm (Name, Gebindegröße, Mindestbestand)
data/bewegungen.csv           Journal aller Buchungen
data/aliase.csv               gelernte Zuordnungen Belegtext -> Artikel
data/offene_zuordnungen.csv   Belegzeilen, die noch keinem Artikel zugeordnet sind
berichte/                     erzeugte Excel-Bestandslisten
```

## Ablauf

**Einmalig — Lagerbestand einlesen:**

```bash
./inventur.py anfangsbestand Lagerbestand.xlsx
```

Die Spalten werden anhand ihrer Überschriften erkannt (`Artikel`, `Nr.`,
`Selektor`, `Menge Lager`, `Gesamt`, `Mindestbestand`, `Gebinde`, `Kategorie`,
`Lieferant`, `EAN`). Die Datei muss also nicht vorbereitet werden; Titel- und
Erklärzeilen über der Kopfzeile werden übersprungen, Summenzeilen am Ende
ebenfalls.

Standardmäßig wird die Spalte **`Gesamt`** übernommen, also Lager plus
Automaten. Grund: Nachfüllvorgänge werden nicht erfasst, die Verkaufszahlen
aber schon — würde nur das Lager geführt, zöge jeder Verkauf vom Lager ab,
obwohl die Ware längst im Automaten steht, und der Bestand liefe ins Minus.
Nur das Lager führen:

```bash
./inventur.py anfangsbestand Lagerbestand.xlsx --mengenspalte lager
```

**Laufend — Verkäufe direkt aus der Automatensoftware:**

```bash
./inventur.py vensoft
```

Holt die Verkäufe über die Vensoft-Schnittstelle und bucht sie ab. Zugangsdaten
kommen aus `VENSOFT_USER` und `VENSOFT_PASS`, die Domain `adapter.vensoft.de`
muss in der Netzwerkfreigabe der Umgebung stehen.

Die Verkaufsdaten liegen unter `data/vensoft/` und werden nur ergänzt — jeder
Abruf holt ausschließlich das, was seit der zuletzt gespeicherten Verkaufs-ID
dazugekommen ist. Nötig ist das, weil die Berichte auch die Vortage für den
Vergleich brauchen und ohne Zwischenspeicher jedes Mal die gesamte Historie
abrufen müssten: vier Minuten statt einer Sekunde.

Gebucht wird nur, was den Automaten wirklich verlassen hat: Vensoft kennt zehn
Verkaufsstatus, und `empty`, `error` und `cancel` bedeuten, dass **keine** Ware
ausgegeben wurde. Wer sie mitzählt, bucht Ware ab, die nie den Schacht verlassen
hat. Als Belegnummer dient die Verkaufs-ID von Vensoft, eine Doppelbuchung ist
damit ausgeschlossen.

Die Zuordnung der Vensoft-Produkte zu den Lagerartikeln steht fest in
`data/aliase.csv` und wird **nicht** über Namensähnlichkeit geraten. Grund:
„Red Bull Spring 2026 0,25" und „Red Bull Pink 2026 0,25" stimmen zu 92 %
überein — die Ähnlichkeitssuche hätte die Spring-Verkäufe auf Pink gebucht.

**Laufend — Rechnungen und Verkäufe aus Dateien:**

```bash
./inventur.py einkauf rechnung.csv --quelle selgros
./inventur.py verkauf verkaeufe.csv
```

Erwartete Spalten (Reihenfolge egal, Benennung tolerant, `;` oder `,` als
Trennzeichen):

```
Datum;Bezeichnung;Menge;Einheit;Beleg;Quelle
2026-09-02;COCA COLA 0,33 DS;5;gebinde;SG-2026-0912;selgros
```

`Einheit` unterscheidet `stueck` von `gebinde` — bei `gebinde` wird mit der
Gebindegröße des Artikels multipliziert. Ohne Angabe gilt Stück.

Ist für einen Artikel keine Gebindegröße hinterlegt, wird eine Gebinde-Zeile
**nicht** gebucht, sondern zurückgestellt: „5 Kisten" als 5 Stück zu buchen
wäre ein Fehler um Faktor 24. Trage `stueck_pro_gebinde` in
`data/artikel.csv` nach und führe `./inventur.py zuordnen` aus.

### Stichtag und Dublettenschutz bei Verkäufen

Verkäufe werden erst ab einem Stichtag gebucht — alles davor steckt bereits im
Anfangsbestand und würde sonst doppelt abgezogen:

```bash
./inventur.py stichtag 2026-09-06T15:00
./inventur.py stichtag              # aktuellen Stichtag anzeigen
```

Zeilen vor dem Stichtag werden übersprungen und gezählt. Zeilen, die nur ein
Datum ohne Uhrzeit tragen **und** auf den Stichtag selbst fallen, werden nicht
gebucht, sondern gemeldet: ob sie vor oder nach 15:00 Uhr liegen, ist nicht
entscheidbar, und Raten wäre hier ein stiller Fehler.

Gegen Doppelbuchungen bekommt jede Verkaufszeile eine stabile Kennung aus
Zeitpunkt, Quelle, Automat und Artikel — Verkaufsexporte tragen selten eine
Belegnummer, überlappen sich aber häufig. Enthält der Export eine
Transaktionsnummer, wird diese verwendet. Ein Export, der bereits gebuchte
Zeiträume erneut enthält, kann daher gefahrlos eingelesen werden: die bekannten
Zeilen werden erkannt und übersprungen, nur die neuen kommen dazu.

**Täglicher Umsatzbericht:**

```bash
./inventur.py tagesbericht                      # gestern
./inventur.py tagesbericht --datum 2026-09-07
./inventur.py tagesbericht --mailpaket          # versandfertiges JSON
```

Umsatz, Verkäufe, Vergleich zum Vortag und zum 7-Tage-Schnitt, aufgeteilt nach
Standort und Produkt. Standardmäßig für **gestern** — der laufende Tag wäre
unvollständig.

Der Umsatz ist die Summe der Bruttopreise aus Vensoft, also inklusive
Mehrwertsteuer. Das **Pfand ist im ausgezeichneten Preis enthalten** (bestätigt
von ProVend, aus den Daten allein nicht ableitbar: die Zahlungsfelder der
Schnittstelle sind leer). Es wird deshalb nur nachrichtlich ausgewiesen und
nicht aufgeschlagen.

Produkte erscheinen unter **euren** Artikelnamen, nicht unter den
Vensoft-Bezeichnungen — sonst stünde ein falsch beschrifteter Schacht auch im
Bericht unter dem falschen Namen.

Fehlversuche ohne Warenausgabe (leerer Schacht, Störung, Abbruch) zählen nicht
zum Umsatz, werden aber ausgewiesen: mehrere an einem Tag sind ein Hinweis auf
einen Automaten, der Aufmerksamkeit braucht.

**Monatsauswertung:**

```bash
./inventur.py monatsbericht                     # Vormonat
./inventur.py monatsbericht --monat 2026-08
./inventur.py monatsbericht --mailpaket
```

Dieselben Kennzahlen wie im Tagesbericht, über einen Kalendermonat, mit
Vergleich zum Vormonat, bestem Verkaufstag und Umsatzanteil je Standort. Alle
verkauften Artikel liegen als CSV im Anhang.

**Abfragen:**

```bash
./inventur.py bestand      # vollständige Liste
./inventur.py warnungen    # nur, was nachbestellt werden muss
./inventur.py bericht      # Excel-Bestandsliste in berichte/
./inventur.py bericht --mail
```

**Mindestbestände** — übergangsweise für alle Artikel dieselbe Schwelle:

```bash
./inventur.py mindestbestaende --pauschal 5
```

Aus dem gemessenen Verbrauch ableiten (sobald ein paar Wochen Verkaufsdaten
vorliegen):

```bash
./inventur.py mindestbestaende --puffer 14
./inventur.py mindestbestaende --puffer 14 --uebernehmen
```

Der Vorschlag deckt so viele Tage Verbrauch ab, wie zwischen Warnung und
Nachschub vergehen. Artikel ohne gemessene Verkäufe bekommen keinen Vorschlag.

**Zählkorrektur nach einer Inventur:**

```bash
./inventur.py korrektur coca-cola-033l-dose 264
```

Die Differenz zum gebuchten Bestand wird als `KORREKTUR` verbucht, der
bisherige Verlauf bleibt erhalten.

## Zuordnung von Belegtexten

Auf dem Kassenbon steht `COCA COLA 0,33 DS`, im Artikelstamm
`Coca-Cola 0,33l Dose`. Die Zuordnung läuft über gelernte Aliase, EAN und
Namensähnlichkeit. Was nicht sicher zugeordnet werden kann, wird **nicht
gebucht**, sondern in `data/offene_zuordnungen.csv` gesammelt:

1. In der Spalte `vorschlag` die passende `artikel_id` eintragen
2. `./inventur.py zuordnen`

Die Zuordnung wird gespeichert und greift ab dann automatisch — der Aufwand
sinkt mit jeder verarbeiteten Rechnung. Ist es wirklich ein neues Produkt:

```bash
./inventur.py einkauf rechnung.csv --quelle rewe --neue-artikel
```

Dieselbe Rechnung kann gefahrlos mehrfach eingelesen werden: geprüft wird auf
Positionsebene (Belegnummer + Bezeichnung), bereits gebuchte Zeilen werden
übersprungen.

## Statuslogik

| Status | Bedingung |
|---|---|
| `MINUS` | Bestand negativ — es wurde mehr verkauft als eingekauft, also fehlt eine Rechnung |
| `LEER` | Bestand 0 |
| `NACHBESTELLEN` | Bestand ≤ Mindestbestand |
| `KNAPP` | Reichweite < 7 Tage |
| `OK` | sonst |

Die Reichweite ergibt sich aus dem Durchschnittsverbrauch der letzten 28 Tage
laut Verkaufsbuchungen. Der Bestellvorschlag füllt auf 21 Tage Reichweite auf
und wird auf volle Gebinde aufgerundet.

## Sammelartikel (wechselnde Sorten)

Sortimente, deren Sorten ständig durchwechseln und die im Automaten trotzdem
nur einen Platz belegen, werden als **ein** Posten geführt — sonst zerfällt der
Bestand in Sorten, die es nächste Woche nicht mehr gibt.

```bash
./inventur.py sammelartikel "Elf Bar" --name "Elf Bar Pots (alle Sorten)" --gebinde 10
```

Ab dann wird jede Belegzeile, die den Text enthält, auf diesen einen Artikel
gebucht — egal ob `ELF BAR POT MANGO ICE`, `Elf Bar Pot Watermelon` oder
`ELFBAR POT BLUEBERRY`. Leerzeichen werden ignoriert, `Elfbar` trifft also
genauso. Bereits gebuchte Einzelsorten zieht der Befehl mit um und legt die
leeren Sortenartikel still; der Bestand geht dabei nicht verloren.

Die Regel hat Vorrang vor der Namensähnlichkeit — bei einem Sammelartikel
sollen die Sorten gerade *nicht* auseinanderlaufen. Für `Elf Bar` ist die Regel
in `data/sammelregeln.csv` bereits hinterlegt. Der Mindestbestand gilt für den
Sammelartikel als Ganzes; werden in der Excel je Sorte Mindestbestände
genannt, gilt der größte davon.

## Wöchentlicher Versand

Zwei Wege, je nachdem was verfügbar ist:

**Über eine Claude-Routine** (ohne GitHub-Zugang, ohne App-Passwort) —
siehe [ROUTINE.md](ROUTINE.md). Der Befehl

```bash
./inventur.py mailpaket
```

erzeugt `berichte/versandpaket.json` mit Betreff, Text, HTML-Fassung und
beiden Anhängen. Die Feldnamen entsprechen den Parametern des
Gmail-Werkzeugs, die Routine reicht sie unverändert weiter.

**Über GitHub Actions**

`.github/workflows/bestandsliste.yml` läuft **montags um 12 Uhr** und
verschickt die Liste per SMTP. Beide Wege gleichzeitig zu aktivieren, führt
zu doppelten Mails — eins von beidem genügt.

Die Empfänger stehen in `data/einstellungen.csv` und werden hier gesetzt:

```bash
./inventur.py empfaenger a@beispiel.de b@beispiel.de
./inventur.py empfaenger          # anzeigen
```

Für den Absender braucht es zwei GitHub-Secrets im Repository
(Settings → Secrets and variables → Actions):

| Secret | Inhalt |
|---|---|
| `MAIL_ABSENDER` | Absenderadresse, z.B. `hegebehrens.rechnung@gmail.com` |
| `MAIL_PASSWORT` | App-Passwort des Anbieters |

Der SMTP-Server wird aus der Domain der Absenderadresse abgeleitet (Gmail,
iCloud und T-Online sind hinterlegt), lässt sich aber mit `SMTP_HOST` und
`SMTP_PORT` überschreiben. Das App-Passwort gehört ausschließlich in die
GitHub-Secrets — nicht in eine Datei im Repository. Lokal genügen dieselben
Werte als Umgebungsvariablen (siehe `.env.example`).

Ein App-Passwort ist nötig, weil weder Google noch Apple SMTP mit dem
normalen Kontopasswort zulassen:

- Gmail: [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)
  (setzt Zwei-Faktor-Authentifizierung voraus)
- iCloud: [appleid.apple.com](https://appleid.apple.com) → Anmelden und Sicherheit

**Zur Uhrzeit:** GitHub führt Zeitpläne in UTC aus und kennt keine
Zeitumstellung. Der Eintrag `0 10 * * 1` trifft in der Sommerzeit 12 Uhr; ab
Ende Oktober entspricht er 11 Uhr deutscher Zeit und müsste für punktgenau
12 Uhr auf `0 11 * * 1` geändert werden.

## Test

```bash
python3 tests/test_ablauf.py
```

Spielt den gesamten Ablauf auf einer Kopie der Beispieldaten durch.
