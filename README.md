# Stellen-Radar

Lokales Lead-Tool für IT-Personalvermittlung. Es sammelt IT-Stellenanzeigen aus der Jobsuche-API
der Bundesagentur für Arbeit und von Karriereseiten (Watchlist), bewertet Arbeitgeber per Score und
erstellt Anschreiben als PDF.

**➡️ Bedienung und Installation (ohne Programmierkenntnisse): siehe [ANLEITUNG.md](ANLEITUNG.md).**

## Aufbau

| Datei/Ordner | Zweck |
|---|---|
| `config.yaml` | Suchbegriffe, Region, Filter, Scoring-Gewichtung, Brief-Vorschläge |
| `blacklist.txt` | ausgeblendete Arbeitgeber |
| `vorlagen/brief_vorlage.html` | Briefvorlage (DIN 5008, Fensterumschlag) |
| `abruf.py` | täglicher Datenabruf (Arbeitsagentur + Watchlist) |
| `dashboard.py` | Streamlit-Dashboard |
| `stellenradar/arbeitsagentur.py` | API-Client, Paging, Offline-Markierung |
| `stellenradar/watchlist.py` | ATS-Erkennung (Personio, Recruitee, Greenhouse, Lever, SmartRecruiters, Workable, softgarden, JOIN), Feeds, robots.txt |
| `stellenradar/speicher.py` | Speichern + Erkennung „erneut ausgeschrieben“ |
| `stellenradar/scoring.py` | Firmenübersicht und Score |
| `stellenradar/briefe.py` | Vorschläge, Platzhalter, QR-Code, PDF (xhtml2pdf) |
| `daten/`, `briefe/`, `logs/` | werden beim Betrieb angelegt (nicht im Repository) |

## Entwicklung

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
.venv/bin/pytest            # Tests (nutzen eine nachgebaute BA-API, kein Netz nötig)
.venv/bin/python abruf.py --erzwingen
.venv/bin/streamlit run dashboard.py
```
