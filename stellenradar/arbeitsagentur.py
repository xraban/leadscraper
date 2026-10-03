"""Abruf der Jobsuche-API der Bundesagentur für Arbeit."""
from __future__ import annotations

import json
import logging
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Callable

import requests

from . import db
from .config import alle_suchbegriffe, pfad
from .filter import Filter
from .speicher import erneut_ausgeschrieben_pruefen, job_speichern

log = logging.getLogger("stellenradar")

QUELLE = "Arbeitsagentur"
DETAIL_URL = "https://www.arbeitsagentur.de/jobsuche/jobdetail/{refnr}"


STANDARD_ENDPUNKTE = ["pc/v4/jobs", "pc/v4/app/jobs", "pc/v6/jobs"]
# Manche Server lehnen unbekannte Programme ab (HTTP 403) – dann wird mit anderer Kennung erneut gefragt
USER_AGENTS = [
    "Stellen-Radar/1.0",
    None,   # Standard-Kennung von Python-requests
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0 Safari/537.36",
]
_LISTEN_SCHLUESSEL = ("stellenangebote", "stellenangebot", "jobs", "ergebnisse", "results", "content", "items")
_ANZAHL_SCHLUESSEL = ("maxErgebnisse", "totalElements", "total", "anzahl", "gesamt", "anzahlErgebnisse")


def _finde_liste(o, tiefe=0):
    """Sucht rekursiv eine Liste, deren Einträge wie Stellenanzeigen aussehen."""
    if tiefe > 4:
        return None
    if isinstance(o, list) and o and all(isinstance(x, dict) for x in o[:3]):
        if any(k in o[0] for k in ("refnr", "refNr", "referenznummer", "titel", "stellentitel")):
            return o
    werte = o.values() if isinstance(o, dict) else (o if isinstance(o, list) else [])
    for v in werte:
        if isinstance(v, (dict, list)):
            gefunden = _finde_liste(v, tiefe + 1)
            if gefunden is not None:
                return gefunden
    return None


def antwort_lesen(daten) -> tuple[list | None, int | None]:
    """Liefert (Anzeigenliste, Gesamtzahl). Liste ist None, wenn das Format unbekannt ist."""
    if not isinstance(daten, (dict, list)):
        return None, None
    items = None
    gesamt = None
    if isinstance(daten, dict):
        for k in _LISTEN_SCHLUESSEL:
            if isinstance(daten.get(k), list):
                items = daten[k]
                break
        for k in _ANZAHL_SCHLUESSEL:
            if daten.get(k) not in (None, ""):
                try:
                    gesamt = int(daten[k])
                    break
                except (TypeError, ValueError):
                    pass
        if gesamt is None and isinstance(daten.get("page"), dict):      # z. B. {"page": {"totalElements": ..}}
            for k in _ANZAHL_SCHLUESSEL:
                if k in daten["page"]:
                    try:
                        gesamt = int(daten["page"][k])
                        break
                    except (TypeError, ValueError):
                        pass
    if items is None:
        items = _finde_liste(daten)
    if items is None and gesamt is not None:
        items = []          # gültige Antwort ohne Treffer
    return items, gesamt


class ApiFehler(Exception):
    pass


class BAClient:
    def __init__(self, cfg: dict, session: requests.Session | None = None, schlafen=time.sleep,
                 protokoll_ordner: Path | None = None):
        a = cfg.get("arbeitsagentur") or {}
        self.basis = a.get("basis_url", "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/")
        if not self.basis.endswith("/"):
            self.basis += "/"
        self.endpunkte = list(dict.fromkeys(list(a.get("endpunkte") or []) + STANDARD_ENDPUNKTE))
        self.aktiver = 0
        self.ua_index = 0
        self.pause = float(a.get("pause_sekunden", 1.5))
        self.timeout = float(a.get("timeout_sekunden", 30))
        self.versuche = max(1, int(a.get("wiederholungen", 3)))
        self.session = session or requests.Session()
        self.session.headers.update({
            "X-API-Key": a.get("api_key", "jobboerse-jobsuche"),
            "Accept": "application/json",
        })
        self._ua_setzen()
        self.schlafen = schlafen
        self.protokoll_ordner = protokoll_ordner
        self.anfragen = 0
        self._letzte = 0.0
        self._endpunkt_bestaetigt = False   # hat der aktuelle Endpunkt schon gültig geantwortet?
        self.versuchsprotokoll: list[str] = []

    def _ua_setzen(self):
        ua = USER_AGENTS[self.ua_index]
        if ua:
            self.session.headers["User-Agent"] = ua
        else:
            self.session.headers.pop("User-Agent", None)
            self.session.headers["User-Agent"] = requests.utils.default_user_agent()

    @property
    def endpunkt(self) -> str:
        return self.endpunkte[min(self.aktiver, len(self.endpunkte) - 1)]

    def _warten(self):
        rest = self.pause - (time.monotonic() - self._letzte)
        if rest > 0:
            self.schlafen(rest)
        self._letzte = time.monotonic()

    def _beispiel_speichern(self, endpunkt: str, r, daten=None):
        """Speichert die erste Antwort je Endpunkt – hilft bei der Fehlersuche."""
        if not self.protokoll_ordner:
            return
        try:
            self.protokoll_ordner.mkdir(parents=True, exist_ok=True)
            datei = self.protokoll_ordner / f"api_antwort_{endpunkt.replace('/', '_')}.txt"
            if daten is not None:
                kopie = json.loads(json.dumps(daten))
                if isinstance(kopie, dict):
                    for k, v in kopie.items():
                        if isinstance(v, list):
                            kopie[k] = v[:3]
                text = json.dumps(kopie, ensure_ascii=False, indent=2)
            else:
                text = r.text[:5000]
            datei.write_text(f"// HTTP {r.status_code} {getattr(r, 'url', '')}\n{text}", encoding="utf-8")
        except Exception:  # noqa: BLE001 – nur Diagnose
            pass

    def suche(self, params: dict) -> dict:
        """Gibt {"items": [...], "gesamt": n|None, "roh": ...} zurück."""
        letzter_fehler = None
        while self.aktiver < len(self.endpunkte):
            url = self.basis + self.endpunkte[self.aktiver]
            naechster = False
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
                    except ValueError:
                        letzter_fehler = "Antwort ist kein JSON"
                        self._beispiel_speichern(self.endpunkte[self.aktiver], r)
                        naechster = True
                        break
                    items, gesamt = antwort_lesen(daten)
                    if not self._endpunkt_bestaetigt:
                        self._beispiel_speichern(self.endpunkte[self.aktiver], r, daten)
                    if items is None:
                        schluessel = list(daten.keys())[:10] if isinstance(daten, dict) else type(daten).__name__
                        letzter_fehler = f"unbekanntes Antwortformat (Felder: {schluessel})"
                        naechster = True
                        break
                    if not self._endpunkt_bestaetigt:
                        log.info("  Verwende Endpunkt %s", self.endpunkte[self.aktiver])
                        self.versuchsprotokoll.append(f"{self.endpunkte[self.aktiver]}: OK")
                    self._endpunkt_bestaetigt = True
                    return {"items": items, "gesamt": gesamt, "roh": daten}
                if r.status_code in (429, 500, 502, 503, 504):
                    letzter_fehler = f"HTTP {r.status_code}"
                    warte = r.headers.get("Retry-After")
                    sek = float(warte) if warte and warte.isdigit() else self.pause * 2 ** (versuch + 2)
                    log.warning("  Server meldet %s – warte %.0f s (Versuch %d/%d)",
                                letzter_fehler, sek, versuch + 1, self.versuche)
                    self.schlafen(sek)
                    continue
                letzter_fehler = f"HTTP {r.status_code}"
                if not self._endpunkt_bestaetigt:
                    self._beispiel_speichern(self.endpunkte[self.aktiver], r)
                if r.status_code == 403 and not self._endpunkt_bestaetigt \
                        and self.ua_index + 1 < len(USER_AGENTS):
                    self.ua_index += 1          # mit anderer Programmkennung erneut versuchen
                    self._ua_setzen()
                    log.warning("  %s liefert HTTP 403 – versuche andere Programmkennung",
                                self.endpunkte[self.aktiver])
                    return self.suche(params)
                naechster = True
                break       # 400/401/403/404 -> nächsten Endpunkt probieren
            if not naechster:
                # alle Versuche mit Netzwerk-/Serverfehlern aufgebraucht
                raise ApiFehler(letzter_fehler or "unbekannter Fehler")
            if self._endpunkt_bestaetigt:
                # Endpunkt funktioniert grundsätzlich – nur diese Anfrage ist fehlerhaft
                raise ApiFehler(letzter_fehler)
            self.versuchsprotokoll.append(f"{self.endpunkte[self.aktiver]}: {letzter_fehler}")
            if self.aktiver + 1 < len(self.endpunkte):
                log.warning("  Endpunkt %s liefert %s – wechsle zu %s",
                            self.endpunkte[self.aktiver], letzter_fehler, self.endpunkte[self.aktiver + 1])
            self.aktiver += 1
            self.ua_index = 0
            self._ua_setzen()
        raise ApiFehler("Kein Endpunkt lieferte Anzeigen (" + "; ".join(self.versuchsprotokoll) + ")")


def _text(wert) -> str:
    if isinstance(wert, dict):
        wert = wert.get("name") or wert.get("bezeichnung") or wert.get("titel") or ""
    return str(wert or "").strip()


def anzeige_umwandeln(item: dict) -> dict | None:
    refnr = _text(item.get("refnr") or item.get("refNr") or item.get("referenznummer") or item.get("hashId"))
    arbeitgeber = _text(item.get("arbeitgeber") or item.get("arbeitgeberName") or item.get("firma"))
    titel = _text(item.get("titel") or item.get("stellentitel") or item.get("stellenbezeichnung")
                  or item.get("beruf"))
    if not refnr or not arbeitgeber or not titel:
        return None
    ort = item.get("arbeitsort") or item.get("arbeitsorte") or {}
    if isinstance(ort, list):
        ort = ort[0] if ort else {}
    if not isinstance(ort, dict):
        ort = {"ort": str(ort)}
    koord = ort.get("koordinaten") or {}
    veroeff = (item.get("aktuelleVeroeffentlichungsdatum") or item.get("veroeffentlichungsdatum")
               or item.get("veroeffentlichtAm") or item.get("ersteVeroeffentlichungsdatum"))
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

    protokoll = pfad(cfg, "logs")
    client = client or BAClient(cfg, protokoll_ordner=protokoll)
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
    roh_anzeigen = 0          # Anzeigen in den API-Antworten (vor Umwandlung/Filter)
    unlesbar = 0              # Anzeigen, deren Felder nicht erkannt wurden
    abbruch_grund = ""

    abbruch = False
    for lauf, ort_params in laeufe:
        for fb, begriff in begriffe:
            if abbruch:
                break
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
                    if not client._endpunkt_bestaetigt:
                        abbruch = True     # API von Anfang an nicht erreichbar -> Abruf beenden
                        abbruch_grund = str(e)
                    break
                items = daten["items"]
                treffer_gesamt = daten["gesamt"]
                roh_anzeigen += len(items)
                for item in items:
                    job = anzeige_umwandeln(item) if isinstance(item, dict) else None
                    if not job:
                        unlesbar += 1
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

    if abbruch:
        meldungen.insert(0, "Die Arbeitsagentur-API hat keine Anzeigen geliefert – Abruf abgebrochen. "
                            f"Details: {abbruch_grund}. Antwortbeispiele liegen im Ordner {protokoll}.")
        log.error(meldungen[0])
    elif roh_anzeigen and unlesbar == roh_anzeigen:
        fehler += 1
        meldungen.insert(0, f"Die API lieferte {roh_anzeigen} Anzeigen, deren Format aber nicht erkannt wurde. "
                            f"Antwortbeispiel: Ordner {protokoll} (Dateien api_antwort_*.txt).")
        log.error(meldungen[0])
    elif not abbruch and roh_anzeigen == 0 and vollstaendig:
        meldungen.insert(0, "Die API hat geantwortet, aber für keinen Suchbegriff Anzeigen geliefert. "
                            f"Antwortbeispiel: Ordner {protokoll} (Dateien api_antwort_*.txt).")
        log.warning(meldungen[0])
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
