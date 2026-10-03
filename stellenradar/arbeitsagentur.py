"""Abruf der Jobsuche-API der Bundesagentur für Arbeit."""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from typing import Callable

import requests

from . import db
from .config import alle_suchbegriffe
from .filter import Filter
from .speicher import erneut_ausgeschrieben_pruefen, job_speichern

log = logging.getLogger("stellenradar")

QUELLE = "Arbeitsagentur"
DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"


class ApiFehler(Exception):
    pass


class BAClient:
    def __init__(self, cfg: dict, session: requests.Session | None = None, schlafen=time.sleep):
        a = cfg.get("arbeitsagentur") or {}
        self.basis = a.get("basis_url", "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/")
        if not self.basis.endswith("/"):
            self.basis += "/"
        self.endpunkte = list(a.get("endpunkte") or ["pc/v4/app/jobs", "pc/v6/jobs"])
        self.aktiver = 0
        self.pause = float(a.get("pause_sekunden", 1.5))
        self.timeout = float(a.get("timeout_sekunden", 30))
        self.versuche = max(1, int(a.get("wiederholungen", 3)))
        self.session = session or requests.Session()
        self.session.headers.update({
            "X-API-Key": a.get("api_key", "jobboerse-jobsuche"),
            "User-Agent": "Stellen-Radar/1.0",
            "Accept": "application/json",
        })
        self.schlafen = schlafen
        self.anfragen = 0
        self._letzte = 0.0
        self._endpunkt_bestaetigt = False   # hat der aktuelle Endpunkt schon geantwortet?

    def _warten(self):
        rest = self.pause - (time.monotonic() - self._letzte)
        if rest > 0:
            self.schlafen(rest)
        self._letzte = time.monotonic()

    def suche(self, params: dict) -> dict:
        letzter_fehler = None
        while self.aktiver < len(self.endpunkte):
            url = self.basis + self.endpunkte[self.aktiver]
            for versuch in range(self.versuche):
                self._warten()
                self.anfragen += 1
                try:
                    r = self.session.get(url, params=params, timeout=self.timeout)
                except requests.RequestException as e:
                    letzter_fehler = f"Netzwerkfehler: {e}"
                    log.warning("  %s (Versuch %d/%d)", letzter_fehler, versuch + 1, self.versuche)
                    self.schlafen(self.pause * 2 ** (versuch + 1))
                    continue
                if r.status_code == 200:
                    try:
                        daten = r.json()
                        self._endpunkt_bestaetigt = True
                        return daten
                    except ValueError:
                        letzter_fehler = "Antwort ist kein JSON"
                        break   # -> nächsten Endpunkt probieren
                if r.status_code in (429, 500, 502, 503, 504):
                    letzter_fehler = f"HTTP {r.status_code}"
                    warte = r.headers.get("Retry-After")
                    sek = float(warte) if warte and warte.isdigit() else self.pause * 2 ** (versuch + 2)
                    log.warning("  Server meldet %s – warte %.0f s (Versuch %d/%d)",
                                letzter_fehler, sek, versuch + 1, self.versuche)
                    self.schlafen(sek)
                    continue
                letzter_fehler = f"HTTP {r.status_code}"
                break       # 400/401/403/404 -> nächsten Endpunkt probieren
            else:
                # alle Versuche mit Netzwerk-/Serverfehlern aufgebraucht
                raise ApiFehler(letzter_fehler or "unbekannter Fehler")
            if self._endpunkt_bestaetigt:
                # Endpunkt funktioniert grundsätzlich – nur diese Anfrage ist fehlerhaft
                raise ApiFehler(letzter_fehler)
            if self.aktiver + 1 < len(self.endpunkte):
                log.warning("  Endpunkt %s liefert %s – wechsle zu %s",
                            self.endpunkte[self.aktiver], letzter_fehler, self.endpunkte[self.aktiver + 1])
            self.aktiver += 1
        raise ApiFehler(f"Kein Endpunkt erreichbar (zuletzt: {letzter_fehler})")


def anzeige_umwandeln(item: dict) -> dict | None:
    refnr = item.get("refnr") or item.get("refNr")
    arbeitgeber = (item.get("arbeitgeber") or "").strip()
    titel = (item.get("titel") or item.get("beruf") or "").strip()
    if not refnr or not arbeitgeber or not titel:
        return None
    ort = item.get("arbeitsort") or {}
    if isinstance(ort, list):
        ort = ort[0] if ort else {}
    koord = ort.get("koordinaten") or {}
    veroeff = item.get("aktuelleVeroeffentlichungsdatum") or item.get("veroeffentlichungsdatum")
    return {
        "id": refnr,
        "quelle": QUELLE,
        "refnr": refnr,
        "titel": titel,
        "arbeitgeber": arbeitgeber,
        "ort": ort.get("ort"),
        "plz": ort.get("plz"),
        "strasse": ort.get("strasse"),
        "lat": koord.get("lat"),
        "lon": koord.get("lon"),
        "veroeffentlicht": str(veroeff)[:10] if veroeff else None,
        "url": DETAIL_URL.format(refnr=refnr),
        "externe_url": item.get("externeUrl"),
    }


def _suchlaeufe(cfg: dict) -> list[tuple[str, dict]]:
    s = cfg.get("suchlaeufe") or {}
    out = []
    reg = s.get("regional")
    if reg and reg.get("aktiv", True):
        out.append(("regional", {"wo": str(reg.get("wo", "69488")), "umkreis": int(reg.get("umkreis", 80))}))
    bw = s.get("bundesweit")
    if bw and bw.get("aktiv", True):
        out.append(("bundesweit", {}))
    return out


def abruf_noetig(con, cfg: dict) -> tuple[bool, str]:
    stunden = float((cfg.get("arbeitsagentur") or {}).get("mindestabstand_stunden", 6))
    letzter = db.letzter_erfolgreicher_lauf(con, QUELLE)
    if not letzter:
        return True, ""
    ende = datetime.fromisoformat(letzter["ende"])
    if datetime.now() - ende < timedelta(hours=stunden):
        return False, (f"Letzter erfolgreicher Abruf war {ende:%d.%m.%Y %H:%M} – "
                       f"weniger als {stunden:g} Stunden her, daher übersprungen.")
    return True, ""


def abrufen(con, cfg: dict, flt: Filter | None = None, client: BAClient | None = None,
            erzwingen: bool = False, fortschritt: Callable[[float, str], None] | None = None) -> dict:
    flt = flt or Filter(cfg)
    if not erzwingen:
        ok, grund = abruf_noetig(con, cfg)
        if not ok:
            log.info(grund)
            return {"uebersprungen": True, "grund": grund}

    client = client or BAClient(cfg)
    a = cfg.get("arbeitsagentur") or {}
    size = min(100, int(a.get("seitengroesse", 100)))
    max_seiten = int(a.get("max_seiten", 30))
    seit = int(a.get("veroeffentlichtseit") or 0)

    start = db.jetzt()
    erstimport = db.letzter_erfolgreicher_lauf(con, QUELLE) is None
    begriffe = alle_suchbegriffe(cfg)
    laeufe = _suchlaeufe(cfg)
    gesamt = max(1, len(begriffe) * len(laeufe))
    vollstaendig: set[str] = set()
    meldungen: list[str] = []
    fehler = 0
    gesehen: set[str] = set()
    neu = 0
    gefiltert: set[str] = set()
    schritt = 0

    for lauf, ort_params in laeufe:
        for fb, begriff in begriffe:
            schritt += 1
            fundstelle = f"{lauf}|{begriff}"
            if fortschritt:
                fortschritt(schritt / gesamt, f"{lauf}: {begriff}")
            log.info("Suche %-10s %s", lauf, begriff)
            seite, treffer_gesamt = 1, None
            while True:
                params = {"was": begriff, "angebotsart": 1, "zeitarbeit": "false", "pav": "false",
                          "size": size, "page": seite, **ort_params}
                if seit > 0:
                    params["veroeffentlichtseit"] = seit
                try:
                    daten = client.suche(params)
                except ApiFehler as e:
                    fehler += 1
                    meldungen.append(f"{fundstelle} Seite {seite}: {e}")
                    log.error("  Fehler: %s", e)
                    break
                items = daten.get("stellenangebote") or []
                try:
                    treffer_gesamt = int(daten.get("maxErgebnisse") or 0)
                except (TypeError, ValueError):
                    treffer_gesamt = None
                for item in items:
                    job = anzeige_umwandeln(item)
                    if not job:
                        continue
                    if flt.titel_ausgeschlossen(job["titel"]):
                        gefiltert.add(job["id"])
                        continue
                    job["fachbereiche"] = flt.fachbereiche_fuer_titel(job["titel"]) or [fb]
                    if lauf == "regional":
                        job["regional"] = True
                    if job_speichern(con, flt, job, start, fundstelle, erstimport):
                        neu += 1
                    gesehen.add(job["id"])
                con.commit()
                fertig = (not items or len(items) < size
                          or (treffer_gesamt is not None and seite * size >= treffer_gesamt))
                if fertig:
                    vollstaendig.add(fundstelle)
                    log.info("  %s Treffer", treffer_gesamt if treffer_gesamt is not None else "?")
                    break
                if seite >= max_seiten:
                    meldungen.append(f"{fundstelle}: nach {max_seiten} Seiten abgebrochen "
                                     f"({treffer_gesamt} Treffer) – max_seiten erhöhen?")
                    log.warning("  max_seiten erreicht (%s Treffer)", treffer_gesamt)
                    break
                seite += 1

    offline = offline_markieren(con, start, gesehen, vollstaendig, seit)
    erneut = erneut_ausgeschrieben_pruefen(con, cfg)
    erfolgreich = len(vollstaendig) > 0 and fehler == 0
    ergebnis = {
        "uebersprungen": False, "anfragen": client.anfragen, "gefunden": len(gesehen), "neu": neu,
        "offline": offline, "erneut": erneut, "gefiltert": len(gefiltert), "meldungen": meldungen,
        "erfolgreich": erfolgreich,
    }
    db.lauf_speichern(con, quelle=QUELLE, start=start, ende=db.jetzt(), erfolgreich=int(erfolgreich),
                      anfragen=client.anfragen, gefunden=len(gesehen), neu=neu, offline=offline,
                      erneut=erneut, meldungen="\n".join(meldungen))
    log.info("Arbeitsagentur: %d Anfragen, %d Anzeigen gefunden, %d neu, %d offline, "
             "%d erneut ausgeschrieben, %d (Junior/Praktikum ...) ausgefiltert",
             client.anfragen, len(gesehen), neu, offline, erneut, len(gefiltert))
    return ergebnis


def offline_markieren(con, start: str, gesehen: set[str], vollstaendig: set[str],
                      seit_tage: int) -> int:
    """Markiert Anzeigen als offline, die bei diesem Abruf nicht mehr auftauchten –
    aber nur, wenn alle Suchen, in denen sie früher gefunden wurden, diesmal
    vollständig und fehlerfrei durchliefen."""
    grenze = (date.today() - timedelta(days=seit_tage)).isoformat() if seit_tage > 0 else None
    zeilen = con.execute(
        "SELECT id, fundstellen, veroeffentlicht FROM jobs "
        "WHERE quelle=? AND online=1", (QUELLE,)).fetchall()
    n = 0
    for z in zeilen:
        if z["id"] in gesehen:
            continue
        fund = json.loads(z["fundstellen"] or "[]")
        if not fund or not all(f in vollstaendig for f in fund):
            continue
        if grenze and (z["veroeffentlicht"] or "") < grenze:
            continue   # nur aus dem Suchzeitraum gefallen, nicht unbedingt offline
        con.execute("UPDATE jobs SET online=0, offline_seit=? WHERE id=?", (start, z["id"]))
        n += 1
    con.commit()
    return n
