from __future__ import annotations

import pytest

from stellenradar import arbeitsagentur
from stellenradar.config import lade_config
from stellenradar.db import verbinden
from stellenradar.filter import Filter, firmen_schluessel, titel_normal

from fake_ba import STANDARD, FakeSession


@pytest.fixture
def umgebung(tmp_path):
    cfg = lade_config()
    cfg["arbeitsagentur"]["pause_sekunden"] = 0
    cfg["arbeitsagentur"]["seitengroesse"] = 2      # Blättern testen
    cfg["_test_logs"] = tmp_path / "logs"
    con = verbinden(tmp_path / "test.db")
    return cfg, con, Filter(cfg)


def lauf(cfg, con, flt, session):
    client = arbeitsagentur.BAClient(cfg, session=session, schlafen=lambda s: None,
                                     protokoll_ordner=cfg.get("_test_logs"))
    return arbeitsagentur.abrufen(con, cfg, flt, client=client, erzwingen=True)


def test_erster_abruf(umgebung):
    cfg, con, flt = umgebung
    erg = lauf(cfg, con, flt, FakeSession())
    assert erg["erfolgreich"]
    ids = {r["id"] for r in con.execute("SELECT id FROM jobs")}
    # Junior, Werkstudent, Ausbildung sind rausgefiltert
    assert "10000-1004-S" not in ids and "10000-4002-S" not in ids and "10000-9001-S" not in ids
    assert len(ids) == len(STANDARD) - 3
    # regional / bundesweit
    reg = {r["id"]: r["regional"] for r in con.execute("SELECT id, regional FROM jobs")}
    assert reg["10000-1001-S"] == 1 and reg["10000-4001-S"] == 0
    # beide Läufe gefunden, Fundstellen gemerkt, nicht doppelt gespeichert
    r = con.execute("SELECT fundstellen FROM jobs WHERE id='10000-1001-S'").fetchone()
    assert "regional|DevOps Engineer" in r[0] and "bundesweit|Kubernetes" in r[0]
    # GmbH und GmbH & Co. KG -> gleiche Firma
    keys = {r[0] for r in con.execute("SELECT firma_key FROM jobs WHERE arbeitgeber LIKE 'Odenwald%'")}
    assert keys == {"odenwald elektronik"}
    # erneut ausgeschrieben
    r = con.execute("SELECT erneut_ausgeschrieben, vorgaenger_id FROM jobs WHERE id='10000-2002-S'").fetchone()
    assert tuple(r) == (1, "10000-2001-S")
    assert con.execute("SELECT erneut_ausgeschrieben FROM jobs WHERE id='10000-2001-S'").fetchone()[0] == 0


def test_offline_und_neu(umgebung):
    cfg, con, flt = umgebung
    lauf(cfg, con, flt, FakeSession())
    weniger = [s for s in STANDARD if s[0] != "10000-6001-S"]
    weniger.append(("10000-6002-S", "Netzwerkadministrator (m/w/d)", "Stadtwerke Darmstadt Digital GmbH",
                    "64283", "Darmstadt", 49.872, 8.651, 0, ["Netzwerkadministrator"]))
    erg = lauf(cfg, con, flt, FakeSession(weniger))
    assert erg["offline"] == 1 and erg["neu"] == 1
    alt = con.execute("SELECT online, offline_seit FROM jobs WHERE id='10000-6001-S'").fetchone()
    assert alt["online"] == 0 and alt["offline_seit"]
    neu = con.execute("SELECT erneut_ausgeschrieben, vorgaenger_id, erstimport FROM jobs "
                      "WHERE id='10000-6002-S'").fetchone()
    assert tuple(neu) == (1, "10000-6001-S", 0)
    # Anzeige taucht wieder auf -> wieder online
    lauf(cfg, con, flt, FakeSession())
    assert con.execute("SELECT online FROM jobs WHERE id='10000-6001-S'").fetchone()[0] == 1


def test_fehler_markiert_nichts_offline(umgebung):
    cfg, con, flt = umgebung
    lauf(cfg, con, flt, FakeSession())
    leer = [s for s in STANDARD if "Netzwerkadministrator" not in s[8]]
    erg = lauf(cfg, con, flt, FakeSession(leer, fehler_bei={"Netzwerkadministrator"}))
    assert not erg["erfolgreich"]
    assert con.execute("SELECT online FROM jobs WHERE id='10000-6001-S'").fetchone()[0] == 1


def test_endpunkt_wechsel(umgebung):
    cfg, con, flt = umgebung
    s = FakeSession(v4_status=404)
    erg = lauf(cfg, con, flt, s)
    assert erg["erfolgreich"]
    assert s.aufrufe[0][0].endswith("pc/v4/jobs") and s.aufrufe[-1][0].endswith("pc/v6/jobs")
    p = s.aufrufe[-1][1]
    assert p["angebotsart"] == 1 and p["zeitarbeit"] == "false" and p["pav"] == "false"


def test_mindestabstand(umgebung):
    cfg, con, flt = umgebung
    lauf(cfg, con, flt, FakeSession())
    erg = arbeitsagentur.abrufen(con, cfg, flt, client=None, erzwingen=False)
    assert erg["uebersprungen"]


def test_filter_hilfen(umgebung):
    cfg, con, flt = umgebung
    assert flt.ist_personaldienstleister("Kurpfalz Personalservice GmbH")
    assert flt.ist_personaldienstleister("Amadeus FiRe AG")
    assert not flt.ist_personaldienstleister("Stadtverwaltung Weinheim")
    assert flt.ist_blacklist("SAP SE") and flt.ist_blacklist("Hays Professional Solutions GmbH")
    assert not flt.ist_blacklist("Sapient GmbH")
    assert not flt.ist_blacklist("SAP Beratung Müller GmbH")   # "SAP SE" mit Rechtsform -> exakt
    assert flt.ist_blacklist("BASF Digital Solutions GmbH")    # "BASF" ohne Rechtsform -> Wort
    assert flt.titel_ausgeschlossen("Praktikum im Bereich DevOps")
    assert not flt.titel_ausgeschlossen("Senior DevOps Engineer")
    assert titel_normal("SAP Berater FI/CO (m/w/d)") == titel_normal("SAP-Berater FI/CO (w/m/d)")
    assert firmen_schluessel("Muster GmbH & Co. KG") == firmen_schluessel("Muster GmbH")
    assert "SAP" in flt.fachbereiche_fuer_titel("SAP ABAP Entwickler (m/w/d)")
    assert flt.ist_regional("69469") and not flt.ist_regional("20457")


def test_keine_verbindung_bricht_ab(umgebung):
    import requests

    cfg, con, flt = umgebung

    class Kaputt:
        headers = {}
        n = 0

        def get(self, *a, **k):
            Kaputt.n += 1
            raise requests.ConnectionError("keine Verbindung")

    erg = lauf(cfg, con, flt, Kaputt())
    assert not erg["erfolgreich"] and "keine Anzeigen geliefert" in erg["meldungen"][0]
    assert Kaputt.n == cfg["arbeitsagentur"]["wiederholungen"]   # nur die erste Suche probiert


def test_403_andere_kennung_und_unbekanntes_format(umgebung):
    """v4 lehnt die Programmkennung ab, v4/app liefert fremdes Format -> v6 wird genutzt."""
    from fake_ba import FakeResponse

    cfg, con, flt = umgebung
    cfg["arbeitsagentur"]["endpunkte"] = ["pc/v4/jobs", "pc/v4/app/jobs", "pc/v6/jobs"]
    s = FakeSession()
    original = s.get

    def get(url, params=None, timeout=None):
        if url.endswith("pc/v4/jobs"):
            s.aufrufe.append((url, dict(params)))
            if "Stellen-Radar" in s.headers.get("User-Agent", "") or "python" in s.headers.get("User-Agent", ""):
                return FakeResponse(403)
            return FakeResponse(200, {"etwas": "anderes"})
        if url.endswith("pc/v4/app/jobs"):
            s.aufrufe.append((url, dict(params)))
            return FakeResponse(200, {"meldung": "unbekannt"})
        return original(url, params, timeout)

    s.get = get
    erg = lauf(cfg, con, flt, s)
    assert erg["erfolgreich"] and erg["gefunden"] == 13
    assert s.aufrufe[-1][0].endswith("pc/v6/jobs")
    assert (cfg["_test_logs"] / "api_antwort_pc_v4_app_jobs.txt").exists()


def test_antwortformate():
    lesen = arbeitsagentur.antwort_lesen
    assert lesen({"maxErgebnisse": "0"}) == ([], 0)
    items, n = lesen({"ergebnis": {"liste": [{"refNr": "1", "titel": "A"}]}, "totalElements": 7})
    assert items == [{"refNr": "1", "titel": "A"}] and n == 7
    assert lesen({"fehler": "x"}) == (None, None)
    job = arbeitsagentur.anzeige_umwandeln({"refNr": "R1", "stellentitel": "Dev", "arbeitgeber": {"name": "X GmbH"},
                                            "arbeitsorte": [{"ort": "Weinheim", "plz": "69469"}]})
    assert job["arbeitgeber"] == "X GmbH" and job["ort"] == "Weinheim" and job["titel"] == "Dev"


def test_null_treffer_meldung(umgebung):
    cfg, con, flt = umgebung
    erg = lauf(cfg, con, flt, FakeSession(stellen=[]))
    assert "für keinen Suchbegriff Anzeigen" in erg["meldungen"][0]
