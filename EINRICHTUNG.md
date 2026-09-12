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
python --version
```

Erwartet wird `Python 3.11` oder höher.

**Wichtig:** `python` **ohne** Dateiname dahinter startet die interaktive
Python-Eingabe. Der Zeilenanfang wird dann zu `>>>`, und ab da versteht das
Fenster keine PowerShell-Befehle mehr. `cd` scheitert dort an einem
`SyntaxError`, weil Python das `\U` in `\Users` für eine Escape-Sequenz hält —
das sieht aus, als sei der Pfad falsch, ist es aber nicht.

| Zeilenanfang | wo du bist |
|---|---|
| `PS C:\...>` | PowerShell — hierhin gehören alle Befehle dieser Anleitung |
| `>>>` | Python — mit `exit()` wieder heraus |

Nach `python` folgt in dieser Anleitung deshalb **immer** ein Dateiname oder `-m`.

## 2. Programm ablegen

Entpacke das Paket in den ProVend-Ordner, sodass es so aussieht:

```
C:\Users\Frédéric\OneDrive\KI-Workstation\03_PROVEND_DEUTSCHLAND\
    10_Inventur\          <- hierher das Paket
    60_Prospekte\         <- liegt schon da
```

Damit liegt alles ProVend beieinander und wird von OneDrive mitgesichert.
Der Ordnername `10_Inventur` ist frei wählbar; er passt nur zu eurer
Nummerierung.

### Zwei Einstellungen, die OneDrive braucht

**„Immer auf diesem Gerät behalten".** Rechtsklick auf `10_Inventur` →
diese Option setzen. Ohne sie macht OneDrive aus selten benutzten Dateien
Platzhalter, die erst beim Öffnen geladen werden — eine nachts laufende
Aufgabe scheitert dann, weil die Datei nicht wirklich da ist.

**Nicht gleichzeitig auf zwei Rechnern arbeiten.** OneDrive synchronisiert
auch, während das Programm schreibt. Läuft die Inventur auf zwei Geräten,
entstehen Dateien wie `bewegungen-Kopie mit Konflikt.csv`, und Buchungen gehen
verloren. Ein Rechner führt das Journal — das ist keine technische Grenze,
sondern eine Absprache, die eingehalten werden muss.

## 3. Abhängigkeiten

```powershell
python -m pip install --upgrade pip
python -m pip install openpyxl Pillow tzdata
```

`tzdata` ist die Zeitzonendatenbank. Linux und macOS bringen eine mit, Windows
nicht. Ohne sie läuft alles trotzdem — die Kontaktzeitpunkte der Automaten
werden dann nur so angezeigt, wie die Schnittstelle sie liefert, und das ist
ohnehin schon deutsche Zeit.

## 4. Zugangsdaten hinterlegen

**Nicht in den OneDrive-Ordner.** Passwörter, die dort liegen, werden in die
Cloud synchronisiert. Lege die Datei stattdessen in dein Benutzerprofil:

```
C:\Users\Frédéric\.provend.env
```

Das Programm sucht dort zuerst und findet sie unabhängig davon, wo das Projekt
liegt. Inhalt — mit dem Editor schreiben, nicht mit Word:

```
VENSOFT_USER=hegebehrens
VENSOFT_PASS=hier-das-vensoft-passwort
MAIL_ABSENDER=hegebehrens.rechnung@gmail.com
MAIL_PASSWORT=hier-das-gmail-app-passwort
```

Das Programm liest die Datei beim Start selbst ein. Gesucht wird in dieser
Reihenfolge: die Umgebungsvariable `PROVEND_ENV`, dann
`%USERPROFILE%\.provend.env`, zuletzt eine `.env` im Projektordner. Was schon
in der Windows-Umgebung gesetzt ist, hat immer Vorrang.

Eine `.env` im Projekt funktioniert also weiterhin — nur eben nicht, solange
das Projekt in OneDrive liegt.

### Das Gmail-App-Passwort

Nicht das normale Kontopasswort. Ein App-Passwort holst du so:

1. Bei [myaccount.google.com](https://myaccount.google.com) mit
   **hegebehrens.rechnung@gmail.com** anmelden — dem Absenderkonto, nicht der
   iCloud-Adresse.
2. **Sicherheit → Bestätigung in zwei Schritten** muss eingeschaltet sein.
   Ohne sie bietet Google keine App-Passwörter an; die Seite meldet dann nur,
   die Einstellung sei nicht verfügbar.
3. Direkt zu [myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords),
   einen Namen vergeben (etwa `ProVend Inventur`) und erstellen.
4. Google zeigt **16 Zeichen in vier Blöcken**, etwa `abcd efgh ijkl mnop`.
   Die Leerzeichen gehören **nicht** dazu — in die Datei kommen die 16 Zeichen
   am Stück.

Google zeigt das Passwort genau einmal. Ist es weg, einfach ein neues erzeugen
und das alte löschen.

Prüfen, ob es stimmt — ohne eine Mail zu verschicken:

```powershell
python inventur.py zugang --mailtest
```

Oder per Doppelklick auf `windows\Mailzugang testen.cmd` — die Datei wechselt
selbst in den richtigen Ordner.

Der Befehl meldet sich bei Gmail an und trennt sofort wieder. `535` oder
`Username and Password not accepted` heißt: falsches Passwort, meist ein
mitkopiertes Leerzeichen.

### Wenn daraus `.provend.env.txt` wird

Das passiert leicht: Der Windows-Editor hängt `.txt` an, sobald im Feld
*Dateityp* beim Klick auf Speichern noch „Textdokumente" stand — die Auswahl
muss **vor** dem Tippen des Namens umgestellt sein. Und der Explorer blendet
bekannte Endungen aus, also sieht die Datei danach richtig aus.

Das Programm liest die `.txt`-Fassung trotzdem, es geht also nichts kaputt.
Sauber machen lässt es sich so:

```powershell
cd $env:USERPROFILE
Rename-Item ".provend.env.txt" ".provend.env"
Get-ChildItem -Force ".provend*" | Select-Object Name, Length
```

Zuverlässiger beim nächsten Mal: den Namen im Speichern-Dialog in
Anführungszeichen setzen — `".provend.env"`. Dann nimmt der Dialog ihn
wörtlich.

### Prüfen, ob es sitzt

```powershell
python inventur.py zugang
```

Der Befehl zeigt, welche Datei gelesen wurde und welche Werte gesetzt sind.
Passwörter werden dabei nur als Zeichenzahl ausgegeben, nie im Klartext.

## 5. Probelauf

**Nicht `inventur.py` im Explorer doppelklicken.** Windows öffnet dann kurz
ein Fenster, führt das Programm aus und schließt sofort wieder — die Ausgabe
ist weg, bevor man sie lesen kann, auch eine Fehlermeldung.

Für den Alltag liegen im Ordner `windows` Verknüpfungen zum Doppelklicken
(`Tagesbericht.cmd`, `Bestandsliste.cmd`, …). Sie lassen das Fenster offen,
bis du eine Taste drückst, und wechseln selbst in den richtigen Ordner. Bis auf
`Taeglich versenden.cmd` lesen sie nur — die eine bucht und verschickt.

Zum Einrichten trotzdem die PowerShell benutzen — dort siehst du Fehler im
Zusammenhang:

```powershell
cd "C:\Users\Frédéric\OneDrive\KI-Workstation\03_PROVEND_DEUTSCHLAND\10_Inventur"
python inventur.py bestand
python inventur.py tagesbericht
```

Die Anführungszeichen sind nötig — der Pfad enthält einen Bindestrich und
einen Akzent.

Der zweite Befehl ruft Vensoft ab. Kommen Zahlen, stimmen die Zugangsdaten.

## 6. OneDrive-Ordner eintragen

```powershell
python inventur.py prospekte "C:\Users\Frédéric\OneDrive\KI-Workstation\03_PROVEND_DEUTSCHLAND\60_Prospekte"
```

Ohne Argument zeigt der Befehl den hinterlegten Pfad an. Den genauen Pfad
findest du, indem du den Ordner im Explorer öffnest und oben in die Adresszeile
klickst.

## 7. Automatischer Versand

Zwei Wege. Der erste braucht Claude nicht und ist deshalb der zuverlässigere.

### Weg A: Windows-Aufgabenplanung (empfohlen)

Der Versand läuft per SMTP über die Adresse aus `MAIL_ABSENDER`, ganz ohne
Claude. Aufgabenplanung öffnen (`taskschd.msc`) → „Einfache Aufgabe erstellen".

**Aufgabe 1 — Tagesbericht, täglich 07:00**

| Feld | Wert |
|---|---|
| Programm | `cmd.exe` |
| Argumente | `/c "Taeglich versenden.cmd"` |
| Starten in | `…\10_Inventur\windows` |

**Aufgabe 2 — Bestandsliste, montags 12:00**

| Feld | Wert |
|---|---|
| Programm | `python` |
| Argumente | `inventur.py bericht --mail` |
| Starten in | `…\10_Inventur` |

**Aufgabe 3 — Monatsauswertung, am 1. um 07:30**

| Feld | Wert |
|---|---|
| Programm | `python` |
| Argumente | `inventur.py monatsbericht --mail` |
| Starten in | `…\10_Inventur` |

Bei „Starten in" den **vollen** Pfad eintragen, ohne Anführungszeichen — etwa
`C:\Users\Frédéric\OneDrive\KI-Workstation\03_PROVEND_DEUTSCHLAND\10_Inventur`.
Das Feld ist nicht optional: Ohne die Angabe findet das Programm seine Daten
nicht. Anführungszeichen gehören dort nicht hinein, anders als in der
PowerShell — die Aufgabenplanung nimmt den Text wörtlich.

**Warum der Tagesbericht über eine .cmd-Datei läuft:** Er macht zwei Schritte
— erst die Verkäufe abbuchen, dann die Mail verschicken. Bricht der erste ab,
unterbleibt der zweite. Sonst ginge ein Bericht auf unvollständigen Zahlen
hinaus, und niemand würde es merken.

Die Monatsauswertung läuft bewusst eine halbe Stunde nach dem Tagesbericht: So
sind die Verkäufe des Vortags gebucht, bevor der Monat abgerechnet wird.

In den Eigenschaften jeder Aufgabe zusätzlich **„Aufgabe so schnell wie möglich
nach einem verpassten Start ausführen"** ankreuzen. Sonst fällt der Bericht
aus, wenn der Rechner zur fraglichen Zeit aus war.

Die Zeitumstellung Ende Oktober macht die Aufgabenplanung selbst mit — anders
als die bisherigen Cloud-Routinen, die in UTC rechnen und dadurch eine Stunde
früher feuern.

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
| `python wird nicht erkannt` | Python ohne „Add to PATH" installiert, oder PowerShell nach der Installation nicht neu geöffnet |
| `SyntaxError: unicodeescape` bei `cd` | Du bist im Python-Interpreter (`>>>`) statt in PowerShell — mit `exit()` heraus |
| `NameError: name '...' is not defined` | dasselbe: `>>>` statt `PS` |
| `ModuleNotFoundError: openpyxl` | Schritt 3 übersprungen |
| `VENSOFT_USER und VENSOFT_PASS muessen gesetzt sein` | `.provend.env` fehlt, heißt `.provend.env.txt`, oder liegt nicht im Benutzerprofil |
| `Authentication failed` beim Versand | normales Passwort statt App-Passwort in `MAIL_PASSWORT` |
| Aufgabenplanung läuft, aber nichts passiert | „Starten in" nicht gesetzt |
| `FileNotFoundError` bei einer Datei, die es gibt | OneDrive hat sie ausgelagert — „Immer auf diesem Gerät behalten" setzen |
| Dateien heißen plötzlich „Kopie mit Konflikt" | Auf zwei Rechnern gleichzeitig gearbeitet |
