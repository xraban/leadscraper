"""Stellen-Radar – Datenabruf (Arbeitsagentur + Karriereseiten-Watchlist).

Aufruf:  python abruf.py              normaler täglicher Abruf
         python abruf.py --erzwingen  auch wenn der letzte Abruf erst kurz her ist
"""
from __future__ import annotations

import argparse
import logging
import sys

from stellenradar import arbeitsagentur, watchlist
from stellenradar.config import ConfigFehler, lade_config, pfad
from stellenradar.db import verbinden
from stellenradar.filter import Filter
from stellenradar.protokoll import logging_einrichten


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Stellen-Radar Datenabruf")
    ap.add_argument("--erzwingen", action="store_true", help="Mindestabstand ignorieren")
    ap.add_argument("--nur-arbeitsagentur", action="store_true")
    ap.add_argument("--nur-watchlist", action="store_true")
    args = ap.parse_args(argv)

    try:
        cfg = lade_config()
    except ConfigFehler as e:
        print(f"FEHLER: {e}")
        return 2
    logging_einrichten(cfg)
    log = logging.getLogger("stellenradar")
    log.info("=== Stellen-Radar Abruf gestartet ===")
    con = verbinden(pfad(cfg, cfg.get("datenbank", "daten/stellenradar.db")))
    flt = Filter(cfg)
    ok = True
    if not args.nur_watchlist:
        try:
            erg = arbeitsagentur.abrufen(con, cfg, flt, erzwingen=args.erzwingen)
            ok &= erg.get("uebersprungen") or erg.get("erfolgreich", False)
        except Exception:  # noqa: BLE001 – Abruf soll nie "hart" abstürzen
            log.exception("Unerwarteter Fehler beim Arbeitsagentur-Abruf")
            ok = False
    if not args.nur_arbeitsagentur:
        try:
            erg = watchlist.alle_abrufen(con, cfg, flt, erzwingen=args.erzwingen)
            ok &= erg.get("fehler", 0) == 0
        except Exception:  # noqa: BLE001
            log.exception("Unerwarteter Fehler beim Watchlist-Abruf")
            ok = False
    log.info("=== Abruf beendet (%s) ===", "OK" if ok else "mit Fehlern – siehe oben")
    con.close()
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
