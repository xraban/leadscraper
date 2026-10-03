from __future__ import annotations

import json

import pytest

from stellenradar import db, watchlist
from stellenradar.config import lade_config
from stellenradar.filter import Filter
from stellenradar.scoring import firmen_uebersicht

PERSONIO_XML = """<?xml version="1.0" encoding="UTF-8"?>
<workzag-jobs>
  <position><id>101</id><office>Weinheim</office><name>DevOps Engineer (m/w/d)</name>
    <createdAt>2026-08-01T10:00:00+00:00</createdAt></position>
  <position><id>102</id><office>Weinheim</office><name>Buchhalter (m/w/d)</name>
    <createdAt>2026-08-01T10:00:00+00:00</createdAt></position>
  <position><id>103</id><office>Weinheim</office><name>Werkstudent IT-Support (m/w/d)</name></position>
  {extra}
</workzag-jobs>"""

KARRIERE_HTML = """<html><body><h1>Karriere</h1>
<p>Alle Stellen finden Sie <a href="https://musterfirma.jobs.personio.de/">hier</a>.</p></body></html>"""

JOIN_HTML = """<html><script id="__NEXT_DATA__" type="application/json">""" + json.dumps(
    {"props": {"pageProps": {"jobs": {"items": [
        {"id": 9001, "idParam": "9001-sap-berater", "title": "SAP Berater MM (m/w/d)",
         "city": {"cityName": "Mannheim"}, "createdAt": "2026-09-01T00:00:00Z", "employmentType": {}},
        {"id": 9002, "idParam": "9002-vertrieb", "title": "Vertriebsmitarbeiter (m/w/d)",
         "city": {"cityName": "Mannheim"}, "employmentType": {}}]}}}}) + "</script></html>"

GENERISCH_HTML = """<html><body>
<a href="/karriere/stellen/123">Systemadministrator Linux (m/w/d)</a>
<a href="/karriere/stellen/124">Lagerist (m/w/d)</a>
<a href="/impressum">Impressum</a></body></html>"""


class R:
    def __init__(self, status=200, text="", daten=None):
        self.status_code, self.text = status, text
        self.content = text.encode("utf-8")
        self._daten = daten

    def json(self):
        return self._daten

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


class FakeWeb:
    def __init__(self, seiten):
        self.seiten = seiten
        self.headers = {}
        self.aufrufe = []

    def get(self, url, timeout=None):
        self.aufrufe.append(url)
        if url in self.seiten:
            v = self.seiten[url]
            return v() if callable(v) else v
        if url.endswith("/robots.txt"):
            return R(404)
        return R(404, "nicht gefunden")


@pytest.fixture
def umg(tmp_path):
    cfg = lade_config()
    con = db.verbinden(tmp_path / "w.db")
    return cfg, con, Filter(cfg)


def test_erkennung():
    assert watchlist.system_erkennen("https://acme.jobs.personio.de")["feed_url"] == \
        "https://acme.jobs.personio.de/xml?language=de"
    assert watchlist.system_erkennen('<iframe src="https://boards.greenhouse.io/embed/job_board?for=acme">')[
        "feed_url"] == "https://boards-api.greenhouse.io/v1/boards/acme/jobs"
    assert watchlist.system_erkennen("https://acme.softgarden.io/de/vacancies")["system"] == "softgarden"
    assert watchlist.system_erkennen("https://join.com/companies/acme")["system"] == "JOIN"
    assert watchlist.system_erkennen("https://jobs.lever.co/acme")["system"] == "Lever"
    assert watchlist.system_erkennen("https://www.acme.de/karriere") is None


def test_personio_ueber_eigene_karriereseite(umg):
    cfg, con, flt = umg
    extra = {"x": ""}
    web = FakeWeb({
        "https://www.musterfirma.de/karriere": R(text=KARRIERE_HTML),
        "https://musterfirma.jobs.personio.de/xml?language=de":
            lambda: R(text=PERSONIO_XML.replace("{extra}", extra["x"])),
    })
    ab = watchlist.Abrufer(cfg, session=web, schlafen=lambda s: None)
    wid = db.watchlist_hinzufuegen(con, "Musterfirma GmbH", "https://www.musterfirma.de/karriere")
    erg = watchlist.eintrag_abrufen(con, cfg, flt, wid, abrufer=ab)
    assert erg["status"] == "ok" and erg["it"] == 1 and erg["neu"] == 0      # Erstimport ist nicht "neu"
    e = db.watchlist_laden(con)[0]
    assert e["system"] == "Personio" and e["feed_url"].endswith("/xml?language=de")
    job = con.execute("SELECT * FROM jobs").fetchone()
    assert job["quelle"] == "Karriereseite" and job["url"] == "https://musterfirma.jobs.personio.de/job/101"
    assert job["veroeffentlicht"] == "2026-08-01"

    # neue IT-Stelle taucht auf -> "NEU (Karriereseite)"
    extra["x"] = "<position><id>104</id><name>SAP Basis Administrator (m/w/d)</name></position>"
    web.aufrufe.clear()
    erg = watchlist.eintrag_abrufen(con, cfg, flt, wid, abrufer=ab)
    assert erg["neu"] == 1
    assert "https://www.musterfirma.de/karriere" not in web.aufrufe     # Feed direkt, Seite nicht erneut
    df = firmen_uebersicht(con, cfg, flt)
    assert df.iloc[0]["Neu"] == "NEU (Karriereseite)" and df.iloc[0]["Quellen"] == "Karriereseite"

    # Stelle verschwindet -> offline
    extra["x"] = ""
    watchlist.eintrag_abrufen(con, cfg, flt, wid, abrufer=ab)
    assert con.execute("SELECT online FROM jobs WHERE id=?", (f"KS:{wid}:104",)).fetchone()[0] == 0


def test_join_und_html_nur_einmal_taeglich(umg):
    cfg, con, flt = umg
    web = FakeWeb({"https://join.com/companies/acme": R(text=JOIN_HTML),
                   "https://www.beispiel.de/jobs": R(text=GENERISCH_HTML)})
    ab = watchlist.Abrufer(cfg, session=web, schlafen=lambda s: None)
    w1 = db.watchlist_hinzufuegen(con, "Acme GmbH", "https://join.com/companies/acme")
    w2 = db.watchlist_hinzufuegen(con, "Beispiel AG", "https://www.beispiel.de/jobs")
    erg = watchlist.alle_abrufen(con, cfg, flt, abrufer=ab)
    assert erg["abgerufen"] == 2
    titel = {r[0] for r in con.execute("SELECT titel FROM jobs")}
    assert titel == {"SAP Berater MM (m/w/d)", "Systemadministrator Linux (m/w/d)"}
    assert con.execute("SELECT ort FROM jobs WHERE watch_id=?", (w1,)).fetchone()[0] == "Mannheim"
    # zweiter Abruf am selben Tag: Seiten ohne Feed werden übersprungen
    web.aufrufe.clear()
    erg = watchlist.alle_abrufen(con, cfg, flt, erzwingen=True, abrufer=ab)
    assert erg["uebersprungen"] == 2 and web.aufrufe == []
    systeme = {e["id"]: e["system"] for e in db.watchlist_laden(con)}
    assert systeme == {w1: "JOIN", w2: "HTML (ohne Feed)"}


def test_robots_txt_wird_beachtet(umg):
    cfg, con, flt = umg
    web = FakeWeb({"https://www.geheim.de/robots.txt": R(text="User-agent: *\nDisallow: /karriere"),
                   "https://www.geheim.de/karriere": R(text=GENERISCH_HTML)})
    ab = watchlist.Abrufer(cfg, session=web, schlafen=lambda s: None)
    wid = db.watchlist_hinzufuegen(con, "Geheim GmbH", "https://www.geheim.de/karriere")
    erg = watchlist.eintrag_abrufen(con, cfg, flt, wid, abrufer=ab)
    assert erg["status"] == "robots"
    assert "https://www.geheim.de/karriere" not in web.aufrufe
    assert con.execute("SELECT COUNT(*) FROM jobs").fetchone()[0] == 0
