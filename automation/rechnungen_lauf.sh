#!/bin/bash
#
# Startet den Rechnungslauf für launchd.
#
# Das App-Passwort liegt in der macOS-Keychain, nicht in einer Datei und nicht
# in der plist — die wäre für jeden Prozess im Klartext lesbar.
#
# Einmalig hinterlegen:
#   security add-generic-password -a "$USER" -s gmail-rechnungen -w 'App-Passwort'

set -uo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOG_DIR="$HOME/Library/Logs/Rechnungen"
LOG_FILE="$LOG_DIR/rechnungen.log"

mkdir -p "$LOG_DIR"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" >> "$LOG_FILE"
}

# Log knapp halten: ab 5 MB einmal rotieren.
if [ -f "$LOG_FILE" ] && [ "$(stat -f%z "$LOG_FILE" 2>/dev/null || echo 0)" -gt 5242880 ]; then
    mv "$LOG_FILE" "$LOG_FILE.1"
fi

PASSWORT="$(security find-generic-password -a "$USER" -s gmail-rechnungen -w 2>/dev/null)"
if [ -z "$PASSWORT" ]; then
    log "FEHLER: Kein Passwort in der Keychain unter 'gmail-rechnungen'."
    log "        security add-generic-password -a \"\$USER\" -s gmail-rechnungen -w 'App-Passwort'"
    exit 1
fi

# iCloud Drive muss eingehängt sein, sonst legt der Lauf ins Leere ab.
ICLOUD="$HOME/Library/Mobile Documents/com~apple~CloudDocs"
if [ ! -d "$ICLOUD" ]; then
    log "FEHLER: iCloud Drive nicht gefunden – Lauf abgebrochen."
    exit 1
fi

log "=== Lauf gestartet (${1:-sortieren}) ==="

export GMAIL_APP_PASSWORD="$PASSWORT"
cd "$REPO_DIR" || { log "FEHLER: $REPO_DIR nicht erreichbar."; exit 1; }

if [ "${1:-sortieren}" = "entwurf" ]; then
    # Monatslauf: Entwurf für den VORMONAT.
    #
    # Der Zeitraum ist entscheidend. Liefe der Entwurf über den gesamten
    # Bestand, enthielte er jeden Monat auch alles Vorherige noch einmal und
    # DATEV bekäme dieselben Belege wieder und wieder.
    #
    # --nur-entwurf, weil der Sortierlauf Ablage und Label bereits erledigt
    # hat: ohne das würde hier ein zweites Mal in den Steuerordner geschrieben.
    MONAT=$(date -v-1m +%-m)
    JAHR=$(date -v-1m +%Y)
    log "Entwurf für ${MONAT}/${JAHR}"
    /usr/bin/python3 rechnungen_sortieren.py \
        --jahr "$JAHR" --monat "$MONAT" --nur-entwurf >> "$LOG_FILE" 2>&1
else
    # Regellauf: nur einsortieren und ablegen, keine Entwürfe.
    /usr/bin/python3 rechnungen_sortieren.py --kein-entwurf >> "$LOG_FILE" 2>&1
fi

STATUS=$?
unset GMAIL_APP_PASSWORD

if [ $STATUS -eq 0 ]; then
    log "=== Lauf beendet ==="
else
    log "=== Lauf mit Fehler beendet (Code $STATUS) ==="
fi

exit $STATUS
