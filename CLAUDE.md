# Stellen-Radar – Projektnotizen für Claude

Lokales Python-Tool (Windows + Mac) zur Lead-Generierung für eine IT-Personalvermittlung
(Direktvermittlung, Mittelstand, Region Rhein-Neckar/Bergstraße/Südhessen + bundesweit).
Der Nutzer ist **kein Entwickler**: Antworten auf Deutsch, Schritte für Laien erklären,
Bedienung über Doppelklick-Skripte (`1_…` bis `5_…` für Windows `.bat` / Mac `.command`).
Endnutzer-Doku: `ANLEITUNG.md`. Technischer Überblick: `README.md`.

## Arbeitsweise
- Branch: `claude/stellen-radar-tool-ysmlq4` (noch kein PR, nicht auf main).
- Tests: `python -m venv .venv && .venv/bin/pip install -r requirements.txt pytest && .venv/bin/pytest`
  (22 Tests, nutzen nachgebaute BA-API `tests/fake_ba.py`, kein Netz nötig).
- Die Cloud-Umgebung erreicht **arbeitsagentur.de und Karriereseiten nicht** (Proxy 403).
  Live-Tests macht der Nutzer auf seinem Windows-PC und schickt Screenshots/Logs.
  Diagnose: `logs/abruf_JJJJ-MM.log` und `logs/api_antwort_<endpunkt>.txt`.
- `.bat`-Dateien müssen CRLF behalten (`.gitattributes`: `*.bat -text`).
- f-Strings ohne verschachtelte gleiche Anführungszeichen (Python ≥ 3.10 muss laufen).
- Nutzer startet aus `C:\Users\…\OneDrive\Dokumente\Stellen-Radar` und aktualisiert
  per GitHub „Download ZIP“ + Überschreiben. Daher sind config.yaml und blacklist.txt nach einem Update wieder auf Standard,
  die Datenbank `daten/` bleibt erhalten (gitignored).

## Stand (03.10.2026)
Alle 8 Anforderungen umgesetzt und mit Testdaten getestet:
1. **BA-API** (`stellenradar/arbeitsagentur.py`): regional (69488, 80 km) + bundesweit,
   Pausen, Retries, Endpunkt-Fallback, Abbruch bei Nichterreichbarkeit.
   **Wichtig:** `pc/v4/jobs` und `pc/v4/app/jobs` liefern inzwischen HTTP 403; nur
   `pc/v6/jobs` funktioniert. Dessen Format: `ergebnisliste`, `referenznummer`,
   `stellenangebotsTitel`, `firma`, `stellenlokationen[].adresse{strasse,hausnummer,plz,ort}`
   + `breite/laenge`, `datumErsteVeroeffentlichung`, `maxErgebnisse`.
   Echte Beispielantwort: `tests/daten/ba_v6_antwort.json`.
2. **SQLite** (`db.py`, `speicher.py`): offline-Markierung (nur wenn alle Fundstellen-Suchen
   vollständig liefen), „erneut ausgeschrieben“ (gleiche Firma, Titelähnlichkeit ≥ 0,85,
   gleicher Ort, ≥ 14 Tage älter oder offline).
3. **Filter** (`filter.py`): Junior/Werkstudent/Praktikum/Ausbildung raus, `blacklist.txt`
   (mit Rechtsform = exakt, ohne = Wortsuche), Personaldienstleister nur markiert (+ Score-Abzug).
4. **Scoring** (`scoring.py`), Gewichte in `config.yaml` → `scoring`.
5. **Dashboard** (`dashboard.py`, Streamlit): Filter, Detailansicht mit Links, Pflegefelder,
   Excel-Export (`export.py`), Blacklist-/Config-Editor.
6. **Briefe** (`briefe.py`, xhtml2pdf, Vorlage `vorlagen/brief_vorlage.html`, DIN 5008 Form B),
   QR-Code mit utm-Parametern, Status → „Brief raus“.
7. **Täglicher Abruf**: `abruf.py`, Einrichtung per `4_Taeglich_einrichten_*`.
8. **Watchlist** (`watchlist.py`): Personio/Recruitee/Greenhouse/Lever/SmartRecruiters/Workable
   per Feed, softgarden/JOIN/eigene Seiten per HTML (max. 1×/Tag, robots.txt).

**Letzter Fix (8e59566):** v6-Antwortformat wird ausgewertet. Vorher wurden 7.991 Anzeigen
geliefert, aber 0 übernommen. **Vom Nutzer noch nicht live bestätigt.**

## Als Nächstes
1. **Live-Bestätigung abwarten**: Erscheinen nach „Daten jetzt abrufen“ Firmen? Falls nicht,
   Log + `api_antwort_pc_v6_jobs.txt` anfordern.
2. Nach dem ersten echten Abruf prüfen und ggf. nachjustieren:
   - Dauer (ca. 100 Anfragen; Treffer bis ~800 pro Begriff → `max_seiten` reicht?),
   - Trefferqualität der Suchbegriffe, Personaldienstleister-Erkennung, Blacklist,
   - Score-Gewichtung und Firmenzusammenführung (`firmen_schluessel`).
   v6 liefert `arbeitgeberKundennummerHash`; dieser stabile Arbeitgeber-ID könnte
   die Zusammenführung per Namen ersetzen bzw. ergänzen.
3. **Briefvorlage des Nutzers** ist noch nicht eingetroffen und muss an xhtml2pdf
   angepasst werden (`@frame`, keine Flexbox/Grid). Platzhalter siehe ANLEITUNG.md §8.
4. Watchlist mit echten Karriereseiten testen (bisher nur simulierte Feeds/HTML).
   softgarden hat keinen bekannten öffentlichen Feed, der HTML-Parser ist geraten.
5. Täglichen Abruf über die Windows-Aufgabenplanung beim Nutzer verifizieren.
6. Optional: PR auf main, sobald der Nutzer zufrieden ist (nur auf Anfrage).
