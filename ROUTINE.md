# Automatische Abläufe

Zwei Routinen laufen über diese Claude-Sitzung. Sie wecken die bestehende
Sitzung, statt eine neue zu starten — nur so ist der Zugriff auf das
Repository, auf Vensoft und auf Gmail gegeben.

| Routine | Zeitpunkt | Was sie tut |
|---|---|---|
| ProVend Tagesbericht | täglich 7:00 | Verkäufe von Vensoft abbuchen, Umsatzbericht des Vortags versenden |
| ProVend Bestandsliste | montags 12:00 | Bestandsliste mit Warnungen und Bestellvorschlägen versenden |
| ProVend Monatsauswertung | am 1. um 7:30 | Auswertung des Vormonats mit Artikel-CSV versenden |

Alle drei gehen an Hegebehrens@icloud.com, sebgri@t-online.de und
info@provenddeutschland.de.

Die Monatsauswertung läuft bewusst eine halbe Stunde nach dem Tagesbericht:
so sind die Verkäufe des Vortags bereits gebucht, bevor der Monat abgerechnet
wird.

**Zur Uhrzeit:** Zeitpläne laufen in UTC ohne Zeitumstellung. Die Einträge
`0 5 * * *`, `30 5 1 * *` und `0 10 * * 1` treffen in der Sommerzeit 7:00,
7:30 und 12:00 Uhr; ab Ende Oktober entsprechen sie 6:00, 6:30 und 11:00 Uhr
deutscher Zeit.

## Wöchentlicher Versand über eine Claude-Routine

Der Versand läuft ohne GitHub-Passwort und ohne App-Passwort: Eine Routine
startet montags eine Claude-Sitzung, die den Bericht erzeugt und ihn über die
Gmail-Verbindung verschickt.

## Voraussetzung: das Repository muss für die Umgebung freigegeben sein

Eine frisch gestartete Routine-Sitzung bekommt das Repository **nicht**
automatisch. Ohne Freigabe scheitert sie beim Klonen mit `403`.

Zwei Wege, das zu lösen:

1. **In der Umgebungskonfiguration** unter [claude.ai/code](https://claude.ai/code)
   das Repository `Hege-Behrens/Kalorien-Tracker` als Quelle der Umgebung
   „Standard" hinterlegen. Das ist der dauerhafte Weg und wirkt für jede
   künftige Sitzung.

2. **Die Routine holt es sich selbst** über `add_repo` — Schritt 1 der
   Anweisung unten. Das funktioniert nur, wenn der GitHub-Zugang des Kontos
   das Repository umfasst.

Schritt 1 der Anweisung deckt Weg 2 ab. Falls die Routine trotzdem an der
Freigabe scheitert, hilft nur Weg 1.

## Einmal einrichten

In Claude eine neue Routine anlegen:

- **Zeitpunkt:** wöchentlich, montags 12:00 Uhr
- **Verbindung:** Gmail auswählen (ohne die kann die Routine nicht senden)
- **Anweisung:** den Text im nächsten Abschnitt einfügen

## Anweisung für die Routine

```
Versende die wöchentliche ProVend-Bestandsliste. Führe alles ohne Rückfragen aus.

1. Verschaffe dir Zugriff auf das Repository. Rufe dafür das Werkzeug add_repo
   (MCP-Server claude-code-remote) auf mit:
     owner="Hege-Behrens", repo="Kalorien-Tracker", access="push"

   Prüfe das Repository NICHT vorher mit curl, git ls-remote oder gh — bei
   privaten Repositories liefert das irreführende 404er. Rufe direkt add_repo
   auf. Führe danach den Klonbefehl aus, den die Antwort nennt, und melde den
   Klon mit register_repo_root.

   Ist das Repository bereits als Quelle der Umgebung vorhanden, entfällt
   dieser Schritt — dann liegt es schon im Arbeitsverzeichnis.

2. Branch wechseln und Stand holen:
   git fetch origin && git checkout claude/vending-inventory-system-ecvzuh && git pull

3. pip install openpyxl Pillow

4. ./inventur.py mailpaket

   Der Befehl erzeugt berichte/versandpaket.json. Die Datei enthält bereits
   alles Versandfertige: to, subject, body, htmlBody und attachments.

5. berichte/versandpaket.json einlesen und die Felder UNVERÄNDERT an
   mcp__Gmail__send_message übergeben:
     to          -> to
     subject     -> subject
     body        -> body
     htmlBody    -> htmlBody
     attachments -> attachments

   Die Feldnamen entsprechen genau den Parametern des Gmail-Werkzeugs.
   Inhalte nicht umformulieren, nicht kürzen, nichts hinzufügen. Der Anhang
   logo.png ist als inline markiert und gehört zum Layout der Mail.

6. Danach berichte/versandpaket.json löschen, den erzeugten Bericht committen
   und pushen:
   rm berichte/versandpaket.json
   git add -A && git commit -m "Bestandsliste <Datum>" && git push

Falls ein Schritt fehlschlägt, sende trotzdem eine Mail an
Hegebehrens@icloud.com, sebgri@t-online.de und info@provenddeutschland.de mit
Betreff "ProVend Bestandsliste - Versand fehlgeschlagen" und einer genauen
Beschreibung, woran es lag. Eine Mail mit Fehlerhinweis ist besser als gar
keine Mail — sonst fällt tagelang niemandem auf, dass nichts kommt.
```

## Warum das JSON

Die Routine soll den Inhalt nicht selbst formulieren. `./inventur.py mailpaket`
erzeugt Betreff, Text, HTML-Fassung und beide Anhänge fertig — die Routine
reicht sie nur weiter. Damit sieht jede wöchentliche Mail gleich aus,
unabhängig davon, wie die Sitzung den Auftrag interpretiert.

Das Paket ist rund 33 KB groß. Es wird nicht eingecheckt.

## Wenn es nicht klappt

Die Fehlermeldung der Sitzung sagt, woran es liegt:

| Meldung | Ursache |
|---|---|
| `403` beim Klonen, keine Zugangsdaten | Repository nicht für die Umgebung freigegeben — siehe oben |
| `add_repo` meldet fehlende Berechtigung | GitHub-Zugang des Kontos umfasst das Repository nicht |
| Gmail-Werkzeug nicht gefunden | Bei der Routine ist die Gmail-Verbindung nicht ausgewählt |
| `ModuleNotFoundError: openpyxl` | Schritt 3 wurde übersprungen |
