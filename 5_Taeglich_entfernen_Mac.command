#!/bin/bash
PLIST="$HOME/Library/LaunchAgents/de.stellenradar.abruf.plist"
launchctl bootout "gui/$(id -u)" "$PLIST" 2>/dev/null || launchctl unload "$PLIST" 2>/dev/null
rm -f "$PLIST"
echo "Der tägliche Abruf wurde entfernt."
read -r -p "Enter drücken zum Schließen ..."
