#!/bin/bash
#
# Richtet die beiden launchd-Jobs für den Rechnungslauf ein.
#
#   ./automation/installieren.sh              installieren
#   ./automation/installieren.sh --status     Status anzeigen
#   ./automation/installieren.sh --entfernen  wieder abbauen
#
# Muss lokal auf dem Mac laufen.

set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
AGENTS_DIR="$HOME/Library/LaunchAgents"
JOBS=(de.hegebehrens.rechnungen.sortieren de.hegebehrens.rechnungen.entwurf)
KEYCHAIN_DIENST="gmail-rechnungen"

status() {
    echo "Installierte Jobs:"
    for job in "${JOBS[@]}"; do
        if launchctl list | grep -q "$job"; then
            echo "  ✓ $job"
        else
            echo "  – $job (nicht geladen)"
        fi
    done
    echo
    echo "Nächste Läufe:"
    for job in "${JOBS[@]}"; do
        plist="$AGENTS_DIR/$job.plist"
        [ -f "$plist" ] && echo "  $job → $plist"
    done
    echo
    echo "Log: $HOME/Library/Logs/Rechnungen/rechnungen.log"
}

entfernen() {
    for job in "${JOBS[@]}"; do
        launchctl bootout "gui/$(id -u)/$job" 2>/dev/null
        rm -f "$AGENTS_DIR/$job.plist"
        echo "Entfernt: $job"
    done
    echo
    echo "Die Jobs sind abgebaut. Das Passwort bleibt in der Keychain –"
    echo "zum Löschen:  security delete-generic-password -s $KEYCHAIN_DIENST"
}

case "${1:-}" in
    --status)    status;    exit 0 ;;
    --entfernen) entfernen; exit 0 ;;
esac

echo "Richte den Rechnungslauf ein …"
echo "Repository: $REPO_DIR"
echo

# 1. Passwort in der Keychain
if ! security find-generic-password -a "$USER" -s "$KEYCHAIN_DIENST" -w >/dev/null 2>&1; then
    echo "Es liegt noch kein App-Passwort in der Keychain."
    echo "Hol dir eins unter https://myaccount.google.com/apppasswords"
    echo
    read -r -s -p "Gmail-App-Passwort (Eingabe bleibt unsichtbar): " passwort
    echo
    if [ -z "$passwort" ]; then
        echo "Abgebrochen: kein Passwort eingegeben."
        exit 1
    fi
    security add-generic-password -a "$USER" -s "$KEYCHAIN_DIENST" -w "$passwort" -U
    unset passwort
    echo "In der Keychain hinterlegt."
else
    echo "App-Passwort liegt bereits in der Keychain."
fi
echo

# 2. Startskript ausführbar machen
chmod +x "$REPO_DIR/automation/rechnungen_lauf.sh"

# 3. plists mit den echten Pfaden erzeugen und laden
mkdir -p "$AGENTS_DIR" "$HOME/Library/Logs/Rechnungen"

for job in "${JOBS[@]}"; do
    vorlage="$REPO_DIR/automation/$job.plist"
    ziel="$AGENTS_DIR/$job.plist"

    sed -e "s|__REPO__|$REPO_DIR|g" -e "s|__HOME__|$HOME|g" "$vorlage" > "$ziel"

    # Einen eventuell laufenden Job erst abmelden, sonst schlägt bootstrap fehl.
    launchctl bootout "gui/$(id -u)/$job" 2>/dev/null
    if launchctl bootstrap "gui/$(id -u)" "$ziel" 2>/dev/null; then
        echo "Eingerichtet: $job"
    else
        echo "FEHLER beim Laden von $job – bitte Ausgabe von 'launchctl error' prüfen."
    fi
done

echo
echo "Fertig."
echo
echo "  Sortieren  täglich um 7:00 und 19:00 Uhr"
echo "  Entwurf    am 1. jedes Monats um 8:00 Uhr"
echo
echo "Log:            tail -f ~/Library/Logs/Rechnungen/rechnungen.log"
echo "Status:         ./automation/installieren.sh --status"
echo "Sofort testen:  launchctl kickstart -p gui/$(id -u)/${JOBS[0]}"
echo "Abbauen:        ./automation/installieren.sh --entfernen"
