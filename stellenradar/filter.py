"""Textnormalisierung, Filter (Junior & Co.), Blacklist, Personaldienstleister-
Erkennung, Fachbereichs-Zuordnung und Regionsprüfung."""
from __future__ import annotations

import math
import re
import unicodedata
from difflib import SequenceMatcher
from pathlib import Path

from .config import pfad

_UMLAUTE = str.maketrans({"ä": "ae", "ö": "oe", "ü": "ue", "ß": "ss"})

# Rechtsformen, die beim Vergleich von Firmennamen ignoriert werden
_RECHTSFORMEN = {
    "gmbh", "mbh", "ag", "se", "kg", "kgaa", "co", "ug", "haftungsbeschraenkt", "ohg",
    "gbr", "ev", "eg", "inc", "ltd", "llc", "plc", "bv", "sa", "sarl", "gesellschaft",
    "mit", "beschraenkter", "haftung", "und", "the",
}


def _basis(text: str) -> str:
    text = (text or "").lower().translate(_UMLAUTE)
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    return text


def firmen_schluessel(name: str) -> str:
    """Normalisierter Schlüssel, damit 'Muster GmbH' und 'Muster GmbH & Co. KG'
    als dieselbe Firma erkannt werden."""
    t = _basis(name).replace("&", " ")
    t = re.sub(r"[^a-z0-9]+", " ", t)
    worte = t.split()
    # Rechtsformen nur am Ende abschneiden (z. B. "AG" in der Mitte bleibt)
    while worte and worte[-1] in _RECHTSFORMEN:
        worte.pop()
    return " ".join(worte) or _basis(name).strip()


def titel_normal(titel: str) -> str:
    """Titel ohne (m/w/d)-Zusätze, Satzzeichen und Groß/Klein – für Vergleiche."""
    t = _basis(titel)
    t = re.sub(r"\((?:[mwdfhix]\s*[/|,]?\s*)+\*?\)", " ", t)   # (m/w/d), (w/m/d) ...
    t = re.sub(r"\b[mwd]\s*/\s*[mwd](\s*/\s*[mwd])?\b", " ", t)
    t = re.sub(r"[^a-z0-9#+.]+", " ", t)
    return " ".join(t.split())


def titel_anzeige(titel: str) -> str:
    """Titel für Briefe: ohne (m/w/d) und überflüssige Leerzeichen."""
    t = re.sub(r"\s*\((?:[mwdfhixMWDFHIX]\s*[/|,]?\s*)+\*?\)", "", titel or "")
    t = re.sub(r"\s*\*?[mwdMWD]\s*/\s*[mwdMWD](\s*/\s*[mwdMWD])?\*?\s*$", "", t)
    return " ".join(t.split()).strip(" -–,")


def titel_aehnlichkeit(a: str, b: str) -> float:
    return SequenceMatcher(None, titel_normal(a), titel_normal(b)).ratio()


def _wortanfang_regex(begriffe: list[str]) -> re.Pattern | None:
    teile = [re.escape(_basis(b).strip()) for b in begriffe if str(b).strip()]
    if not teile:
        return None
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(teile) + ")")


def _ganzwort_regex(begriffe: list[str]) -> re.Pattern | None:
    teile = [re.escape(b) for b in begriffe if b]
    if not teile:
        return None
    return re.compile(r"(?<![a-z0-9])(?:" + "|".join(teile) + r")(?![a-z0-9])")


class Filter:
    def __init__(self, cfg: dict):
        f = cfg.get("filter") or {}
        self._ausschluss = _wortanfang_regex(f.get("titel_ausschluss") or [])
        self._pdl = _wortanfang_regex(f.get("personaldienstleister_hinweise") or [])
        self.blacklist_datei = pfad(cfg, f.get("blacklist_datei", "blacklist.txt"))
        self.lade_blacklist()
        # Fachbereiche: Schlüsselwörter für die Titel-Klassifizierung
        self._fb = []
        for fb, daten in (cfg.get("fachbereiche") or {}).items():
            worte = list((daten or {}).get("schluesselwoerter") or [])
            worte += list((daten or {}).get("begriffe") or [])
            rx = _wortanfang_regex(worte)
            if rx:
                self._fb.append((fb, rx))
        r = cfg.get("region") or {}
        self._lat, self._lon = r.get("lat"), r.get("lon")
        self._radius = float(r.get("radius_km", 80))
        self._plz = tuple(str(p) for p in (r.get("plz_praefixe") or []))

    # ---------------- Blacklist ----------------
    def lade_blacklist(self) -> None:
        eintraege = []
        if self.blacklist_datei.exists():
            for zeile in self.blacklist_datei.read_text(encoding="utf-8").splitlines():
                zeile = zeile.strip()
                if zeile and not zeile.startswith("#"):
                    eintraege.append(firmen_schluessel(zeile))
        self.blacklist = eintraege
        self._bl = _ganzwort_regex(eintraege)

    def ist_blacklist(self, arbeitgeber: str) -> bool:
        return bool(self._bl and self._bl.search(firmen_schluessel(arbeitgeber)))

    # ---------------- Titel / Arbeitgeber ----------------
    def titel_ausgeschlossen(self, titel: str) -> bool:
        return bool(self._ausschluss and self._ausschluss.search(_basis(titel)))

    def ist_personaldienstleister(self, arbeitgeber: str) -> bool:
        return bool(self._pdl and self._pdl.search(_basis(arbeitgeber)))

    def fachbereiche_fuer_titel(self, titel: str) -> list[str]:
        t = _basis(titel)
        return [fb for fb, rx in self._fb if rx.search(t)]

    # ---------------- Region ----------------
    def ist_regional(self, plz: str | None, lat=None, lon=None) -> bool:
        if lat not in (None, "") and lon not in (None, "") and self._lat is not None:
            try:
                return entfernung_km(float(lat), float(lon), self._lat, self._lon) <= self._radius
            except (TypeError, ValueError):
                pass
        plz = (plz or "").strip()
        return bool(plz) and plz.startswith(self._plz)


def entfernung_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def blacklist_hinzufuegen(datei: Path, firmenname: str) -> None:
    text = datei.read_text(encoding="utf-8") if datei.exists() else ""
    if text and not text.endswith("\n"):
        text += "\n"
    datei.write_text(text + firmenname.strip() + "\n", encoding="utf-8")
