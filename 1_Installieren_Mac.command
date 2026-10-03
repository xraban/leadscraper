#!/bin/bash
# Stellen-Radar – Installation (Mac)
cd "$(dirname "$0")" || exit 1
echo "============================================"
echo "  Stellen-Radar wird eingerichtet ..."
echo "============================================"
PY=""
for kandidat in python3.13 python3.12 python3.11 python3.10 python3; do
  if command -v "$kandidat" >/dev/null 2>&1 && \
     "$kandidat" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 10) else 1)' 2>/dev/null; then
    PY="$kandidat"; break
  fi
done
if [ -z "$PY" ]; then
  echo "Python (Version 3.10 oder neuer) wurde nicht gefunden."
  echo "Bitte von https://www.python.org/downloads/ installieren und diese Datei erneut öffnen."
  read -r -p "Enter drücken zum Schließen ..."; exit 1
fi
echo "Verwende $($PY --version)"
[ -x .venv/bin/python ] || "$PY" -m venv .venv || { echo "FEHLER beim Anlegen der Umgebung"; read -r; exit 1; }
echo "Installiere benötigte Pakete (dauert einige Minuten) ..."
.venv/bin/python -m pip install --upgrade pip
if ! .venv/bin/python -m pip install -r requirements.txt; then
  echo "FEHLER bei der Installation. Bitte Internetverbindung prüfen und erneut versuchen."
  read -r -p "Enter drücken zum Schließen ..."; exit 1
fi
chmod +x ./*.command
echo
echo "Fertig! Starten Sie jetzt 2_Dashboard_starten_Mac.command"
read -r -p "Enter drücken zum Schließen ..."
