"""Karriereseiten-Watchlist: erkennt das Bewerbermanagement-System einer Karriereseite,
nutzt (wenn vorhanden) den öffentlichen Job-Feed und liest sonst die HTML-Seite –
höchstens einmal täglich und nur, wenn robots.txt es erlaubt."""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Callable
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser

import requests
from bs4 import BeautifulSoup

from . import db
from .filter import Filter
from .speicher import erneut_ausgeschrieben_pruefen, job_speichern

log = logging.getLogger("stellenradar")

QUELLE = "Karriereseite"

# --------------------------------------------------------------------------------------
# Systeme: (Name, Regex auf URL/HTML, Feed-URL-Vorlage oder None, Seiten-URL-Vorlage)
# --------------------------------------------------------------------------------------
SYSTEME = [
    ("Personio", re.compile(r"([a-z0-9][a-z0-9-]*)\.jobs\.personio\.(de|com)", re.I),
     "https://{0}.jobs.personio.{1}/xml?language=de", "https://{0}.jobs.personio.{1}/"),
    ("Recruitee", re.compile(r"([a-z0-9][a-z0-9-]*)\.recruitee\.com", re.I),
     "https://{0}.recruitee.com/api/offers/", "https://{0}.recruitee.com/"),
    ("Greenhouse", re.compile(r"(?:boards|job-boards)(?:\.eu)?\.greenhouse\.io/(?:embed/job_board(?:/js)?\?for=)?([a-z0-9_-]+)", re.I),
     "https://boards-api.greenhouse.io/v1/boards/{0}/jobs", "https://boards.greenhouse.io/{0}"),
    ("Lever", re.compile(r"jobs\.(?:eu\.)?lever\.co/([a-z0-9_-]+)", re.I),
     "https://api.lever.co/v0/postings/{0}?mode=json", "https://jobs.lever.co/{0}"),
    ("SmartRecruiters", re.compile(r"(?:careers|jobs)\.smartrecruiters\.com/([a-z0-9_-]+)", re.I),
     "https://api.smartrecruiters.com/v1/companies/{0}/postings", "https://jobs.smartrecruiters.com/{0}"),
    ("Workable", re.compile(r"apply\.workable\.com/([a-z0-9_-]+)", re.I),
     "https://apply.workable.com/api/v1/widget/accounts/{0}", "https://apply.workable.com/{0}/"),
    ("softgarden", re.compile(r"([a-z0-9][a-z0-9-]*)\.softgarden\.io", re.I),
     None, "https://{0}.softgarden.io/de/vacancies"),
    ("JOIN", re.compile(r"join\.com/companies/([a-z0-9_-]+)", re.I),
     None, "https://join.com/companies/{0}"),
]
_UNGUELTIGE_SUBDOMAINS = {"www", "api", "static", "cdn", "assets", "app", "widget", "embed", "boards", "jobs"}


def system_erkennen(text: str) -> dict | None:
    """Sucht in URL oder HTML nach bekannten Systemen."""
    for name, rx, feed, seite in SYSTEME:
        for m in rx.finditer(text or ""):
            teile = [g.lower() for g in m.groups() if g]
            if not teile or teile[0] in _UNGUELTIGE_SUBDOMAINS:
                continue
            return {"system": name, "feed_url": feed.format(*teile) if feed else None,
                    "seite": seite.format(*teile)}
    return None


# --------------------------------------------------------------------------------------
# HTTP mit robots.txt
# --------------------------------------------------------------------------------------
class Abrufer:
    def __init__(self, cfg: dict, session: requests.Session | None = None, schlafen=time.sleep):
        w = cfg.get("watchlist") or {}
        self.ua = w.get("user_agent", "Stellen-Radar/1.0")
        self.pause = float(w.get("pause_sekunden", 2))
        self.timeout = float(w.get("timeout_sekunden", 30))
        self.session = session or requests.Session()
        self.session.headers.update({"User-Agent": self.ua, "Accept-Language": "de-DE,de;q=0.9"})
        self.schlafen = schlafen
        self._robots: dict[str, RobotFileParser | None] = {}
        self._letzte = 0.0

    def _get(self, url: str) -> requests.Response:
        rest = self.pause - (time.monotonic() - self._letzte)
        if rest > 0:
            self.schlafen(rest)
        self._letzte = time.monotonic()
        return self.session.get(url, timeout=self.timeout)

    def erlaubt(self, url: str) -> bool | None:
        """True/False laut robots.txt, None wenn die Website nicht erreichbar ist."""
        teile = urlsplit(url)
        basis = f"{teile.scheme}://{teile.netloc}"
        if basis not in self._robots:
            rp = RobotFileParser()
            try:
                r = self._get(basis + "/robots.txt")
                if r.status_code in (401, 403):
                    rp.disallow_all = True
                elif r.status_code >= 400:
                    rp.allow_all = True
                else:
                    rp.parse(r.text.splitlines())
            except requests.RequestException:
                rp = None    # robots.txt nicht erreichbar -> vorsichtshalber nicht abrufen
            self._robots[basis] = rp
        rp = self._robots[basis]
        return None if rp is None else rp.can_fetch(self.ua, url)

    def html(self, url: str) -> str:
        erlaubt = self.erlaubt(url)
        if erlaubt is None:
            raise ConnectionError(f"Website nicht erreichbar ({urlsplit(url).netloc}) – URL prüfen")
        if not erlaubt:
            raise PermissionError(f"robots.txt verbietet den Abruf von {url}")
        r = self._get(url)
        r.raise_for_status()
        return r.text

    def feed(self, url: str) -> requests.Response:
        r = self._get(url)
        r.raise_for_status()
        return r


# --------------------------------------------------------------------------------------
# Parser – jeweils Liste von dicts: id, titel, ort, plz, url, veroeffentlicht
# --------------------------------------------------------------------------------------
def _datum(text) -> str | None:
    if text in (None, ""):
        return None
    if isinstance(text, (int, float)):                       # Millisekunden (Lever)
        return datetime.fromtimestamp(text / 1000).date().isoformat()
    m = re.match(r"(\d{4}-\d{2}-\d{2})", str(text))
    return m.group(1) if m else None


def parse_personio(xml_text: str, seite: str) -> list[dict]:
    root = ET.fromstring(xml_text.encode("utf-8") if isinstance(xml_text, str) else xml_text)
    out = []
    for pos in root.iter("position"):
        jid = (pos.findtext("id") or "").strip()
        titel = (pos.findtext("name") or "").strip()
        if jid and titel:
            out.append({"id": jid, "titel": titel, "ort": (pos.findtext("office") or "").strip() or None,
                        "url": urljoin(seite, f"job/{jid}"), "veroeffentlicht": _datum(pos.findtext("createdAt"))})
    return out


def parse_recruitee(daten: dict, seite: str) -> list[dict]:
    return [{"id": str(o.get("id")), "titel": o.get("title", ""), "ort": o.get("city") or o.get("location"),
             "url": o.get("careers_url") or seite, "veroeffentlicht": _datum(o.get("published_at") or o.get("created_at"))}
            for o in daten.get("offers", []) if o.get("title")]


def parse_greenhouse(daten: dict, seite: str) -> list[dict]:
    return [{"id": str(j.get("id")), "titel": j.get("title", ""), "ort": (j.get("location") or {}).get("name"),
             "url": j.get("absolute_url") or seite, "veroeffentlicht": _datum(j.get("first_published") or j.get("updated_at"))}
            for j in daten.get("jobs", []) if j.get("title")]


def parse_lever(daten: list, seite: str) -> list[dict]:
    return [{"id": str(j.get("id")), "titel": j.get("text", ""), "ort": (j.get("categories") or {}).get("location"),
             "url": j.get("hostedUrl") or seite, "veroeffentlicht": _datum(j.get("createdAt"))}
            for j in daten if isinstance(j, dict) and j.get("text")]


def parse_smartrecruiters(daten: dict, seite: str) -> list[dict]:
    out = []
    for j in daten.get("content", []):
        loc = j.get("location") or {}
        out.append({"id": str(j.get("id")), "titel": j.get("name", ""), "ort": loc.get("city"),
                    "plz": loc.get("postalCode"), "url": f"{seite.rstrip('/')}/{j.get('id')}",
                    "veroeffentlicht": _datum(j.get("releasedDate"))})
    return [j for j in out if j["titel"]]


def parse_workable(daten: dict, seite: str) -> list[dict]:
    return [{"id": j.get("shortcode") or j.get("url") or j.get("title"), "titel": j.get("title", ""),
             "ort": j.get("city"), "url": j.get("url") or j.get("shortlink") or seite,
             "veroeffentlicht": _datum(j.get("published_on") or j.get("created_at"))}
            for j in daten.get("jobs", []) if j.get("title")]


_JOB_LINK = re.compile(r"(job|stelle|karriere|career|position|vacanc|jobs|offer|ausschreibung|anzeige)", re.I)
_MWD = re.compile(r"\(\s*[mwdfh]\s*/\s*[mwdfh]", re.I)


def _id_aus(url: str, titel: str) -> str:
    return hashlib.sha1((url or titel).encode("utf-8")).hexdigest()[:12]


def parse_join(html_text: str, seite: str) -> list[dict]:
    out: dict[str, dict] = {}
    soup = BeautifulSoup(html_text, "html.parser")
    skript = soup.find("script", id="__NEXT_DATA__")
    if skript and skript.string:
        try:
            daten = json.loads(skript.string)
        except ValueError:
            daten = None

        def suchen(o):
            if isinstance(o, dict):
                titel = o.get("title")
                jid = o.get("idParam") or o.get("id")
                if isinstance(titel, str) and jid and ("idParam" in o or "employmentType" in o or "city" in o):
                    stadt = o.get("city")
                    if isinstance(stadt, dict):
                        stadt = stadt.get("cityName") or stadt.get("name")
                    url = urljoin(seite.rstrip("/") + "/", str(o.get("idParam") or jid))
                    out[str(jid)] = {"id": str(jid), "titel": titel, "ort": stadt if isinstance(stadt, str) else None,
                                     "url": url, "veroeffentlicht": _datum(o.get("createdAt"))}
                for v in o.values():
                    suchen(v)
            elif isinstance(o, list):
                for v in o:
                    suchen(v)
        suchen(daten)
    if not out:
        for a in soup.find_all("a", href=True):
            href = urljoin(seite, a["href"])
            m = re.search(r"join\.com/companies/[^/]+/(\d+)", href)
            titel = a.get_text(" ", strip=True)
            if m and titel:
                out[m.group(1)] = {"id": m.group(1), "titel": titel, "url": href}
    return list(out.values())


def parse_html_links(html_text: str, seite: str) -> list[dict]:
    """Allgemein (auch softgarden): Links, die nach Stellenanzeige aussehen."""
    soup = BeautifulSoup(html_text, "html.parser")
    out: dict[str, dict] = {}
    for a in soup.find_all("a", href=True):
        href = urljoin(seite, a["href"])
        if href.startswith(("mailto:", "tel:", "javascript:")):
            continue
        # Titel: bevorzugt eine Überschrift im Link, sonst der Linktext
        kopf = a.find(["h1", "h2", "h3", "h4", "h5", "strong"])
        titel = (kopf.get_text(" ", strip=True) if kopf else a.get_text(" ", strip=True))
        titel = " ".join(titel.split())
        if not (5 <= len(titel) <= 160):
            continue
        if not (_JOB_LINK.search(href) or _MWD.search(titel)):
            continue
        out.setdefault(href, {"id": _id_aus(href, titel), "titel": titel, "url": href})
    return list(out.values())


# --------------------------------------------------------------------------------------
# Abruf
# --------------------------------------------------------------------------------------
def _html_faellig(eintrag: dict, cfg: dict) -> bool:
    if not eintrag.get("letzter_abruf"):
        return True
    stunden = float((cfg.get("watchlist") or {}).get("html_mindestabstand_stunden", 20))
    return datetime.now() - datetime.fromisoformat(eintrag["letzter_abruf"]) >= timedelta(hours=stunden)


def stellen_holen(eintrag: dict, abrufer: Abrufer) -> tuple[list[dict], dict]:
    """Ermittelt das System (falls nötig) und liefert (Stellenliste, Systeminfo)."""
    url = eintrag["url"]
    info = None
    if eintrag.get("system"):
        info = {"system": eintrag["system"], "feed_url": eintrag.get("feed_url"),
                "seite": eintrag.get("seite_url") or url}
    else:
        info = system_erkennen(url)
    seiten_html = None
    if not info:
        # eigene Karriereseite: HTML laden und nach eingebetteten Systemen suchen
        seiten_html = abrufer.html(url)
        info = system_erkennen(seiten_html) or {"system": "HTML (ohne Feed)", "feed_url": None, "seite": url}

    name, feed, seite = info["system"], info.get("feed_url"), info.get("seite") or url
    if feed:
        r = abrufer.feed(feed)
        if name == "Personio":
            stellen = parse_personio(r.content, seite)
        else:
            daten = r.json()
            parser = {"Recruitee": parse_recruitee, "Greenhouse": parse_greenhouse, "Lever": parse_lever,
                      "SmartRecruiters": parse_smartrecruiters, "Workable": parse_workable}[name]
            stellen = parser(daten, seite)
    else:
        text = seiten_html if (seiten_html is not None and seite == url) else abrufer.html(seite)
        stellen = parse_join(text, seite) if name == "JOIN" else parse_html_links(text, seite)
    return stellen, info


def eintrag_abrufen(con, cfg: dict, flt: Filter | None, wid: int, erzwingen: bool = False,
                    abrufer: Abrufer | None = None) -> dict:
    """Ruft einen Watchlist-Eintrag ab. Feeds werden immer abgerufen, Seiten ohne Feed
    höchstens einmal täglich – auch bei `erzwingen` (Rücksicht auf die Websites)."""
    flt = flt or Filter(cfg)
    abrufer = abrufer or Abrufer(cfg)
    eintrag = next((e for e in db.watchlist_laden(con) if e["id"] == wid), None)
    if not eintrag:
        return {"status": "fehlt", "meldung": "Eintrag nicht gefunden"}
    hat_feed = bool(eintrag.get("feed_url"))
    if eintrag.get("system") and not hat_feed and not _html_faellig(eintrag, cfg):
        return {"status": "übersprungen", "meldung": "Seite ohne Feed – heute schon abgerufen"}

    zeit = db.jetzt()
    try:
        stellen, info = stellen_holen(eintrag, abrufer)
    except PermissionError as e:
        db.watchlist_aendern(con, wid, letzter_abruf=zeit, letzte_meldung=str(e))
        log.warning("Watchlist %s: %s", eintrag["firma"], e)
        return {"status": "robots", "meldung": str(e)}
    except Exception as e:  # noqa: BLE001
        meldung = f"Fehler: {e}"
        db.watchlist_aendern(con, wid, letzter_abruf=zeit, letzte_meldung=meldung[:300])
        log.warning("Watchlist %s: %s", eintrag["firma"], meldung)
        return {"status": "fehler", "meldung": meldung}

    erstimport = not eintrag.get("erstabruf_erledigt")
    gesehen, neu, it = set(), 0, 0
    for s in stellen:
        titel = (s.get("titel") or "").strip()
        fbs = flt.fachbereiche_fuer_titel(titel)
        if not fbs or flt.titel_ausgeschlossen(titel):
            continue
        it += 1
        jid = f"KS:{wid}:{s['id']}"
        job = {"id": jid, "quelle": QUELLE, "refnr": None, "titel": titel, "arbeitgeber": eintrag["firma"],
               "ort": s.get("ort"), "plz": s.get("plz"), "veroeffentlicht": s.get("veroeffentlicht"),
               "url": s.get("url"), "fachbereiche": fbs, "watch_id": wid,
               "regional": True if (s.get("plz") and flt.ist_regional(s.get("plz"))) else None}
        if job_speichern(con, flt, job, zeit, erstimport=erstimport):
            neu += 1
        gesehen.add(jid)
    # nicht mehr vorhandene Stellen -> offline
    offline = 0
    for r in con.execute("SELECT id FROM jobs WHERE watch_id=? AND quelle=? AND online=1", (wid, QUELLE)).fetchall():
        if r["id"] not in gesehen:
            con.execute("UPDATE jobs SET online=0, offline_seit=? WHERE id=?", (zeit, r["id"]))
            offline += 1
    con.commit()
    system = info["system"] + (" (Feed)" if info.get("feed_url") else "")
    meldung = f"{system}: {len(stellen)} Stellen, davon {it} IT" + (f", {neu} neu" if neu and not erstimport else "")
    db.watchlist_aendern(con, wid, system=info["system"], feed_url=info.get("feed_url"),
                         seite_url=info.get("seite"), letzter_abruf=zeit,
                         letzter_erfolg=zeit, letzte_meldung=meldung, erstabruf_erledigt=1)
    log.info("Watchlist %s – %s", eintrag["firma"], meldung)
    return {"status": "ok", "meldung": meldung, "neu": 0 if erstimport else neu, "offline": offline, "it": it}


def alle_abrufen(con, cfg: dict, flt: Filter | None = None, erzwingen: bool = False,
                 fortschritt: Callable[[float, str], None] | None = None,
                 abrufer: Abrufer | None = None) -> dict:
    flt = flt or Filter(cfg)
    abrufer = abrufer or Abrufer(cfg)
    eintraege = db.watchlist_laden(con, nur_aktiv=True)
    erg = {"abgerufen": 0, "neu": 0, "fehler": 0, "uebersprungen": 0}
    for i, e in enumerate(eintraege, start=1):
        if fortschritt:
            fortschritt(i / max(1, len(eintraege)), e["firma"])
        r = eintrag_abrufen(con, cfg, flt, e["id"], erzwingen=erzwingen, abrufer=abrufer)
        if r["status"] == "ok":
            erg["abgerufen"] += 1
            erg["neu"] += r.get("neu", 0)
        elif r["status"] == "übersprungen":
            erg["uebersprungen"] += 1
        else:
            erg["fehler"] += 1
    if eintraege:
        erneut_ausgeschrieben_pruefen(con, cfg)
        log.info("Watchlist: %d abgerufen, %d übersprungen (ohne Feed, heute schon abgerufen), "
                 "%d Fehler, %d neue IT-Stellen", erg["abgerufen"], erg["uebersprungen"], erg["fehler"], erg["neu"])
    return erg
