# Hinweise für Claude

Dieses Projekt führt den Lagerbestand zweier Verkaufsautomaten von ProVend
Deutschland GbR (Frédéric Hege-Behrens). Das README erklärt die Mechanik.
Hier steht, was man aus den Daten allein nicht sieht — Dinge, die schon einmal
falsch gemacht wurden.

## Grundregel: erst prüfen, dann melden

Am 09.09.2026 meldete der Tagesbericht einen vermuteten „Datenabriss", weil
seit dem Morgen keine Verkäufe eingegangen waren. Es ging eine Warnung an drei
Empfänger. Tatsächlich lief alles — es wurde nur wenig gekauft.

**Fehlende Verkäufe sind kein Beleg für eine Störung.** Jeder Automat meldet
sich stündlich, auch ohne Verkauf. Der Beleg steht in
`vensoft_vencube.last_contact` und wird von `vensoft.verbindungsstand()`
ausgewertet. Vor jeder Aussage über einen Ausfall: diese Funktion fragen.

Das gilt allgemein. Eine Meldung an die Empfänger löst Handlungen aus —
jemand fährt zwanzig Kilometer zum Automaten. Lieber eine Prüfung zu viel.

## Was die Zahlen verschweigen

**Ein leerer Schacht sieht aus wie ein unbeliebtes Produkt.** Elfbar Pods
haben in Heiligenstedten vier Schächte für 56 Stück; bei der Befüllung lagen
3 Stück darin. Die daraus folgenden „4 Verkäufe in 90 Tagen" sagen nichts über
die Nachfrage. In Glückstadt macht derselbe Artikel 147,50 € je Schacht.

Vor jedem Urteil „verkauft sich nicht": `actual_amount` des Schachtes prüfen.
Nur wo Ware lag, ist eine Null aussagekräftig. Fehlversuche mit Status `empty`
gibt es praktisch nicht — Kunden wählen leere Schächte gar nicht erst an, der
Leerstand fällt in den Verkaufsdaten also nicht auf.

**Je Automat rechnen, nicht zusammengefasst.** Ein Artikel, der in Glückstadt
läuft und in Heiligenstedten nicht, erscheint in der Summe als unauffällig.
Getrennt gerechnet: Glückstadt 43,67 €/Schacht, Heiligenstedten 9,98 €.
Dieselbe Auswertung ergab zusammengefasst 6 tote Schächte, getrennt 9.

**Es gibt keine Einkaufspreise.** Das Bewegungsjournal hat kein Preisfeld, und
es wurde nie eine Einkaufsrechnung eingelesen. „Günstig" kann deshalb nur die
Spanne zum Verkaufspreis meinen, nie einen Vergleich mit früheren Einkäufen.
Wer das anders formuliert, behauptet mehr, als die Daten hergeben.

## Zuordnung von Fremdbezeichnungen

Belegtexte und Vensoft-Produktnamen werden über `lager/zuordnung.py` auf
Artikel abgebildet: Alias → Sammelregel → EAN → Namensähnlichkeit (ab 0,82).

Die Ähnlichkeit ist die gefährliche Stufe. „Red Bull Spring 2026 0,25" und
„Red Bull Pink 2026 0,25" liegen bei 0,92 — beinahe hätte das eine Sorte auf
die andere gebucht. Bei Sorten derselben Marke nie auf die Ähnlichkeit
verlassen, sondern einen Alias setzen.

**Ein Beispiel, das man nicht erraten kann:** Verkäufe von „Schwipp Schwapp"
waren in Wahrheit Mezzo Mix aus einem falsch beschrifteten Schacht. Der Alias
in `data/aliase.csv` bildet das ab. Korrigiert Vensoft die Beschriftung,
**muss dieser Alias weg**, sonst kippt die Zuordnung ins Gegenteil.

Vor einer Korrekturbuchung wegen eines Minusbestands immer fragen, ob nicht in
Wirklichkeit ein anderer Artikel verkauft wurde. Genau dieser Fall wurde
einmal falsch als Zählfehler gebucht.

## Automatik

Drei Routinen (Tagesbericht 7 Uhr, Bestandsliste montags 12 Uhr,
Monatsauswertung am 1.) laufen bisher über eine Claude-Cloud-Sitzung.
`ROUTINE.md` beschreibt sie, `EINRICHTUNG.md` den Umzug auf den Windows-Rechner
samt Aufgabenplanung — dort läuft der Versand per SMTP und braucht Claude nicht.

**Beim Umzug beides gleichzeitig aktiv zu lassen, erzeugt doppelte Mails.**
Die Cloud-Routinen erst abschalten, wenn der lokale Weg nachweislich läuft.

## Umgang mit den Berichten

`./inventur.py tagesbericht --mailpaket` erzeugt ein fertiges Versandpaket.
Dessen Inhalt wird **nicht umformuliert** — so sieht jede Mail gleich aus,
unabhängig davon, wer sie verschickt. Wenn etwas Zusätzliches gesagt werden
muss, gehört es als klar abgesetzter Hinweis dazu, nicht in die Zahlen hinein.

Auffälligkeiten, die keine Handlung erzwingen, gehören in den Chat, nicht in
die Mail. Die Mail liest das ganze Team.

## Zugangsdaten

`VENSOFT_USER`, `VENSOFT_PASS`, `MAIL_ABSENDER`, `MAIL_PASSWORT` kommen aus
`.env` oder der Umgebung — **nie ins Repository**, nie in den Chat. `.env`
steht in `.gitignore`. Beim Mailversand ist `MAIL_PASSWORT` ein App-Passwort,
nicht das Kontopasswort.

## Prüfen vor dem Commit

```bash
python3 tests/test_ablauf.py
```

Der Selbsttest geht den ganzen Ablauf durch: Anfangsbestand, Einkauf, Verkauf,
Zuordnung, Bericht.
