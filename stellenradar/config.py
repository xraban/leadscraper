"""Laden der Einstellungen (config.yaml) und Hilfsfunktionen für Pfade."""
from __future__ import annotations

from pathlib import Path

import yaml

# Programmordner = Ordner, in dem config.yaml liegt
BASIS_ORDNER = Path(__file__).resolve().parent.parent
CONFIG_DATEI = BASIS_ORDNER / "config.yaml"

STATUS_WERTE = ["Neu", "Brief raus", "LinkedIn angefragt", "Antwort", "Lead an Ben", "Raus"]


class ConfigFehler(Exception):
    pass


def lade_config(pfad: Path | str | None = None) -> dict:
    pfad = Path(pfad) if pfad else CONFIG_DATEI
    try:
        with open(pfad, encoding="utf-8") as f:
            cfg = yaml.safe_load(f) or {}
    except FileNotFoundError as e:
        raise ConfigFehler(f"Einstellungsdatei nicht gefunden: {pfad}") from e
    except yaml.YAMLError as e:
        raise ConfigFehler(
            f"Die Einstellungsdatei {pfad.name} enthält einen Formatfehler "
            f"(meist falsche Einrückung oder fehlender Doppelpunkt):\n{e}"
        ) from e
    cfg["_basis"] = str(pfad.resolve().parent)
    return cfg


def pfad(cfg: dict, relativ: str) -> Path:
    """Wandelt einen Pfad aus der Config in einen absoluten Pfad um."""
    p = Path(relativ)
    if not p.is_absolute():
        p = Path(cfg.get("_basis", BASIS_ORDNER)) / p
    return p


def alle_suchbegriffe(cfg: dict) -> list[tuple[str, str]]:
    """Liste von (Fachbereich, Suchbegriff)."""
    out = []
    for fb, daten in (cfg.get("fachbereiche") or {}).items():
        for b in (daten or {}).get("begriffe") or []:
            out.append((fb, str(b)))
    return out
