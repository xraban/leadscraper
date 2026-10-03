#!/bin/bash
# Stellen-Radar – täglichen Abruf einrichten (Mac, launchd)
cd "$(dirname "$0")" || exit 1
ORDNER="$(pwd)"
if [ ! -x .venv/bin/python ]; then
  echo "Bitte zuerst 1_Installieren_Mac.command ausführen."; read -r; exit 1
fi
case "$ORDNER" in
  */Documents/*|*/Desktop/*|*/Downloads/*|*/Library/Mobile\ Documents/*)
    echo "HINWEIS: Der Programmordner liegt in Dokumente/Schreibtisch/Downloads/iCloud."
    echo "macOS blockiert dort oft automatische Hintergrund-Aufgaben."
    echo "Empfehlung: Ordner direkt in Ihren Benutzerordner verschieben (z. B. $HOME/Stellen-Radar)"
    echo "und dieses Skript dort erneut ausführen."
    read -r -p "Trotzdem fortfahren? (j/n) " antwort
    [ "$antwort" = "j" ] || exit 0;;
esac
read -r -p "Um wie viel Uhr soll der Abruf täglich laufen? (z. B. 07:00, Enter = 07:00): " ZEIT
ZEIT="${ZEIT:-07:00}"
STUNDE=$((10#${ZEIT%%:*})); MINUTE=$((10#${ZEIT##*:}))
mkdir -p "$ORDNER/logs" "$HOME/Library/LaunchAgents"
PLIST="$HOME/Library/LaunchAgents/de.stellenradar.abruf.plist"
cat > "$PLIST" <<PL
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>de.stellenradar.abruf</string>
  <key>ProgramArguments</key>
  <array>
    <string>$ORDNER/.venv/bin/python</string>
    <string>$ORDNER/abruf.py</string>
  </array>
  <key>WorkingDirectory</key><string>$ORDNER</string>
  <key>StartCalendarInterval</key>
  <dict><key>Hour</key><integer>$STUNDE</integer><key>Minute</key><integer>$MINUTE</integer></dict>
  <key>StandardOutPath</key><string>$ORDNER/logs/hintergrund.log</string>
  <key>StandardErrorPath</key><string>$ORDNER/logs/hintergrund.log</string>
</dict>
</plist>
PL
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null
launchctl bootstrap "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl load -w "$PLIST"
echo
echo "Eingerichtet: Der Abruf läuft ab jetzt täglich um $(printf '%02d:%02d' "$STUNDE" "$MINUTE") Uhr."
echo "Schläft der Mac zu dieser Zeit, wird der Abruf beim Aufwachen nachgeholt."
read -r -p "Enter drücken zum Schließen ..."
