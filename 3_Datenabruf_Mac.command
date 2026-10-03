#!/bin/bash
# Stellen-Radar – Datenabruf von Hand starten (Mac)
cd "$(dirname "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo "Bitte zuerst 1_Installieren_Mac.command ausführen."; read -r; exit 1
fi
.venv/bin/python abruf.py "$@"
echo
echo "Fertig. Das Protokoll steht im Ordner \"logs\"."
read -r -p "Enter drücken zum Schließen ..."
