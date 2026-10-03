from __future__ import annotations

from datetime import date
from urllib.parse import parse_qs, urlsplit

import pandas as pd

from stellenradar import briefe
from stellenradar.config import lade_config


def _jobs(*zeilen):
    spalten = ["id", "titel", "online", "erneut_ausgeschrieben", "kette_start", "veroeffentlicht",
               "erstmals_gesehen", "fachbereiche"]
    return pd.DataFrame([dict(zip(spalten, z)) for z in zeilen], columns=spalten)


def test_vorschlaege():
    cfg = lade_config()
    heute = date(2026, 10, 3)
    b, e = briefe.vorschlag(cfg, "X", _jobs(("1", "DevOps Engineer (m/w/d)", 1, 0, "2026-09-28", "2026-09-28", "", "")), heute)
    assert b == "Ihre Vakanz DevOps Engineer" and "eine/n DevOps Engineer" in e
    b, e = briefe.vorschlag(cfg, "X", _jobs(("1", "SAP Basis (m/w/d)", 1, 0, "2026-06-01", "2026-06-01", "", "")), heute)
    assert "seit rund 18 Wochen" in e
    b, e = briefe.vorschlag(cfg, "X", _jobs(("1", "SAP FI (m/w/d)", 1, 0, "2026-05-01", "2026-05-01", "", ""),
                                             ("2", "SAP FI (w/m/d)", 1, 1, "2026-05-01", "2026-09-01", "", "")), heute)
    assert b == "Ihre Vakanz SAP FI" and "erneut ausgeschrieben" in e     # gleiche Stelle nur 1x
    b, e = briefe.vorschlag(cfg, "X", _jobs(("1", "Java Dev (m/w/d)", 1, 0, "2026-09-01", "2026-09-01", "", ""),
                                             ("2", "Data Engineer (m/w/d)", 1, 0, "2026-09-20", "2026-09-20", "", "")), heute)
    assert b == "Ihre 2 offenen IT-Positionen" and "Java Dev und eine/n Data Engineer" in e


def test_qr_link_und_platzhalter():
    cfg = lade_config()
    cfg["briefe"]["qr_basis_url"] = "https://example.de/kontakt?ref=1"
    url = briefe.qr_link(cfg, "Müller & Söhne GmbH")
    q = parse_qs(urlsplit(url).query)
    assert q == {"ref": ["1"], "utm_source": ["brief"], "utm_campaign": ["mueller-soehne-gmbh"]}
    werte = briefe.platzhalter_werte(cfg, {"anrede": "Frau", "person": "Erika Muster", "strasse": "Weg 1",
                                           "plz": "69469", "ort": "Weinheim"}, "A & B GmbH", "Betreff", "Hallo")
    assert werte["briefanrede"] == "Sehr geehrte Frau Muster,"
    assert werte["ort"] == "69469 Weinheim" and werte["firma"] == "A &amp; B GmbH"
    html = briefe.html_fuellen('<style>p{color:red}</style><img src="{qr_url}">{firma} {unbekannt}', werte)
    assert "p{color:red}" in html and 'src="data:image/png;base64,' in html
    assert "A &amp; B GmbH" in html and "{unbekannt}" in html
    assert briefe.briefanrede("", "") == "Sehr geehrte Damen und Herren,"


def test_pdf(tmp_path):
    cfg = lade_config()
    cfg["briefe"]["ausgabe_ordner"] = str(tmp_path)
    firma = {"anrede": "Herr", "person": "Max Müller", "strasse": "Hauptstr. 1", "plz": "69469", "ort": "Weinheim"}
    p1 = briefe.brief_erstellen(cfg, firma, "Test GmbH", "Betreff", "Einstieg", date(2026, 10, 3))
    p2 = briefe.brief_erstellen(cfg, firma, "Test GmbH", "Betreff", "Einstieg", date(2026, 10, 3))
    assert p1.read_bytes()[:5] == b"%PDF-" and p1 != p2 and p2.name.endswith("_2.pdf")
