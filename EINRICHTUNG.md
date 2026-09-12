# Einrichtung auf dem Windows-Rechner

Bisher läuft die Inventur in einer Claude-Cloud-Sitzung. Die kommt an OneDrive
nicht heran, weil sie in einem abgeschotteten Container liegt und deine
Festplatte nicht sieht. Auf diesem Rechner ist OneDrive ein ganz normaler
synchronisierter Ordner — deshalb der Umzug.

**Was dadurch besser wird:** Prospekte und Stammdaten sind ohne Umweg lesbar.

**Was dadurch schlechter wird:** Die täglichen Berichte laufen nur noch, wenn
der Rechner an ist. Bisher liefen sie unabhängig davon. Das ist der Preis, und
er ist bewusst bezahlt.

## 1. Python installieren

Aus dem Microsoft Store „Python 3.12" installieren, oder von
[python.org/downloads](https://www.python.org/downloads/). Beim Installer von
python.org **„Add python.exe to PATH" ankreuzen** — ohne das findet die
Aufgabenplanung Python später nicht.

Prüfen in der PowerShell:

```powershell
py --version
```

Erwartet wird `Python 3.11` oder höher.

## 2. Programm ablegen

Entpacke das Paket nach:

```
C:\ProVend\Kalorien-Tracker
```

Der Pfad darf ein anderer sein, dann aber unten überall mit anpassen. Keine
Leerzeichen und keine Umlaute im Pfad — das erspart Anführungszeichen-Ärger in
der Aufgabenplanung.

## 3. Abhängigkeiten

```powershell
py -m pip install --upgrade pip
py -m pip install openpyxl Pillow
```

## 4. Zugangsdaten hinterlegen

Lege die Datei `C:\ProVend\Kalorien-Tracker\.env` an — mit dem Editor, nicht mit
Word. Inhalt:

```
VENSOFT_USER=hegebehrens
VENSOFT_PASS=hier-das-vensoft-passwort
MAIL_ABSENDER=hegebehrens.rechnung@gmail.com
MAIL_PASSWORT=hier-das-gmail-app-passwort
```

Das Programm liest die Datei beim Start selbst ein. Sie steht in `.gitignore`
und wird nie ins Repository übertragen.

**Das Gmail-Passwort ist nicht dein normales Passwort**, sondern ein
App-Passwort: Google-Konto → Sicherheit → Bestätigung in zwei Schritten →
App-Passwörter. Google zeigt es genau einmal an.

Achtung beim Speichern im Windows-Editor: unter „Dateityp" **Alle Dateien**
wählen, sonst heißt die Datei `.env.txt` und wird nicht gefunden.

## 5. Probelauf

```powershell
cd C:\ProVend\Kalorien-Tracker
py inventur.py bestand
py inventur.py tagesbericht
```

Der zweite Befehl ruft Vensoft ab. Kommen Zahlen, stimmen die Zugangsdaten.

## 6. OneDrive-Ordner eintragen

```powershell
py inventur.py prospekte "C:\Users\DEIN-NAME\OneDrive\60_Prospekte"
```

Ohne Argument zeigt der Befehl den hinterlegten Pfad an. Den genauen Pfad
findest du, indem du den Ordner im Explorer öffnest und oben in die Adresszeile
klickst.

## 7. Automatischer Versand

Zwei Wege. Der erste braucht Claude nicht und ist deshalb der zuverlässigere.

### Weg A: Windows-Aufgabenplanung (empfohlen)

Der Versand läuft dann per SMTP über die Adresse aus `MAIL_ABSENDER`, ganz ohne
Claude. Aufgabenplanung öffnen (`taskschd.msc`) → „Einfache Aufgabe erstellen":

| | Tagesbericht | Bestandsliste |
|---|---|---|
| Name | ProVend Tagesbericht | ProVend Bestandsliste |
| Trigger | Täglich, 07:00 | Wöchentlich, Montag, 12:00 |
| Aktion | Programm starten | Programm starten |
| Programm | `py` | `py` |
| Argumente | `inventur.py tagesbericht --mail` | `inventur.py bericht --mail` |
| Starten in | `C:\ProVend\Kalorien-Tracker` | `C:\ProVend\Kalorien-Tracker` |

„Starten in" ist nicht optional — ohne diese Angabe findet das Programm weder
`.env` noch die Daten.

In den Eigenschaften der Aufgabe zusätzlich **„Aufgabe so schnell wie möglich
nach einem verpassten Start ausführen"** ankreuzen. Sonst fällt der Bericht
aus, wenn der Rechner um 7 Uhr aus war.

Die Zeitumstellung Ende Oktober macht die Aufgabenplanung selbst mit — anders
als die bisherigen Cloud-Routinen, die in UTC rechnen.

### Weg B: Claude-Routine auf diesem Rechner

Behält den Gmail-Connector und das mitdenkende Auge (Verbindungsprüfung,
auffällige Muster). Setzt aber voraus, dass Claude auf dem Rechner läuft, wenn
die Routine fällig wird.

## 8. Umschalten — erst wenn Schritt 5 und 7 laufen

Solange die drei bisherigen Cloud-Routinen aktiv sind, kommen die Mails doppelt.
Erst abschalten, wenn hier alles läuft:

- ProVend Tagesbericht (täglich 7 Uhr)
- ProVend Bestandsliste (montags 12 Uhr)
- ProVend Monatsauswertung (1. des Monats, 7 Uhr)

Sag mir Bescheid, dann schalte ich sie ab. Vorher nicht — lieber eine Mail
doppelt als tagelang gar keine.

## Wenn etwas klemmt

| Meldung | Ursache |
|---|---|
| `py wird nicht erkannt` | Python ohne „Add to PATH" installiert |
| `ModuleNotFoundError: openpyxl` | Schritt 3 übersprungen |
| `VENSOFT_USER und VENSOFT_PASS muessen gesetzt sein` | `.env` fehlt, heißt `.env.txt`, oder liegt im falschen Ordner |
| `Authentication failed` beim Versand | normales Passwort statt App-Passwort in `MAIL_PASSWORT` |
| Aufgabenplanung läuft, aber nichts passiert | „Starten in" nicht gesetzt |
