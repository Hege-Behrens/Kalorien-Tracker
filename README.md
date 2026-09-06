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

**Laufend — Rechnungen und Verkäufe:**

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

**Abfragen:**

```bash
./inventur.py bestand      # vollständige Liste
./inventur.py warnungen    # nur, was nachbestellt werden muss
./inventur.py bericht      # Excel-Bestandsliste in berichte/
./inventur.py bericht --mail
```

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

`.github/workflows/bestandsliste.yml` läuft montags früh und verschickt die
Liste per iCloud-SMTP. Dafür in den GitHub-Secrets des Repositories hinterlegen:

| Secret | Inhalt |
|---|---|
| `ICLOUD_EMAIL` | Absenderadresse |
| `ICLOUD_APP_PASSWORD` | App-spezifisches Passwort (appleid.apple.com) |
| `BESTANDSLISTE_EMPFAENGER` | Empfänger, kommagetrennt |

Lokal genügen dieselben Variablen als Umgebungsvariablen (siehe `.env.example`).

## Test

```bash
python3 tests/test_ablauf.py
```

Spielt den gesamten Ablauf auf einer Kopie der Beispieldaten durch.
