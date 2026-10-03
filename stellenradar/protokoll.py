"""Protokoll (Logdatei im Ordner logs + Ausgabe im Konsolenfenster)."""
from __future__ import annotations

import logging
import sys
from datetime import datetime

from .config import pfad


def logging_einrichten(cfg: dict) -> None:
    ordner = pfad(cfg, "logs")
    ordner.mkdir(parents=True, exist_ok=True)
    datei = ordner / f"abruf_{datetime.now():%Y-%m}.log"
    fmt = logging.Formatter("%(asctime)s %(levelname)-7s %(message)s", "%Y-%m-%d %H:%M:%S")
    log = logging.getLogger("stellenradar")
    log.setLevel(logging.INFO)
    log.handlers.clear()
    fh = logging.FileHandler(datei, encoding="utf-8")
    fh.setFormatter(fmt)
    log.addHandler(fh)
    if sys.stdout is not None:          # bei pythonw (Aufgabenplanung) gibt es keine Konsole
        sh = logging.StreamHandler(sys.stdout)
        sh.setFormatter(fmt)
        log.addHandler(sh)
