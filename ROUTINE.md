# Wöchentlicher Versand über eine Claude-Routine

Der Versand läuft ohne GitHub-Zugang und ohne App-Passwort: Eine Routine
startet montags eine Claude-Sitzung, die den Bericht erzeugt und ihn über
deine Gmail-Verbindung verschickt.

## Einmal einrichten

In Claude eine neue Routine anlegen:

- **Zeitpunkt:** wöchentlich, montags 12:00 Uhr
- **Verbindung:** Gmail auswählen (ohne die kann die Routine nicht senden)
- **Anweisung:** den Text im nächsten Abschnitt einfügen

## Anweisung für die Routine

```
Versende die wöchentliche ProVend-Bestandsliste. Führe alles ohne Rückfragen aus.

1. Repository Kalorien-Tracker, Branch claude/vending-inventory-system-ecvzuh:
   git fetch origin && git checkout claude/vending-inventory-system-ecvzuh && git pull

2. pip install openpyxl Pillow

3. ./inventur.py mailpaket

   Der Befehl erzeugt berichte/versandpaket.json. Die Datei enthält bereits
   alles Versandfertige: to, subject, body, htmlBody und attachments.

4. berichte/versandpaket.json einlesen und die Felder UNVERÄNDERT an
   mcp__Gmail__send_message übergeben:
     to          -> to
     subject     -> subject
     body        -> body
     htmlBody    -> htmlBody
     attachments -> attachments

   Die Feldnamen entsprechen genau den Parametern des Gmail-Werkzeugs.
   Inhalte nicht umformulieren, nicht kürzen, nichts hinzufügen. Der Anhang
   logo.png ist als inline markiert und gehört zum Layout der Mail.

5. Danach berichte/versandpaket.json löschen, den erzeugten Bericht committen
   und pushen:
   rm berichte/versandpaket.json
   git add -A && git commit -m "Bestandsliste <Datum>" && git push

Falls ein Schritt fehlschlägt: trotzdem eine Mail an die Empfänger aus
data/einstellungen.csv senden, mit einer klaren Beschreibung des Fehlers.
Eine Mail mit Fehlerhinweis ist besser als gar keine Mail.
```

## Warum das JSON

Die Routine soll den Inhalt nicht selbst formulieren. `./inventur.py mailpaket`
erzeugt Betreff, Text, HTML-Fassung und beide Anhänge fertig — die Routine
reicht sie nur weiter. Damit sieht jede wöchentliche Mail gleich aus,
unabhängig davon, wie die Sitzung den Auftrag interpretiert.

Das Paket ist rund 35 KB groß. Es wird nicht eingecheckt.
