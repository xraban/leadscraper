#!/bin/bash
# Stellen-Radar – Dashboard starten (Mac)
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Bitte zuerst 1_Installieren_Mac.command ausführen."; read -r; exit 1
fi
echo "Das Dashboard öffnet sich gleich im Browser."
echo "Dieses Fenster bitte OFFEN LASSEN – Schließen beendet das Dashboard."
.venv/bin/python stellenradar_starten.py
