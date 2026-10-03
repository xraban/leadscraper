"""Gemeinsames Speichern von Anzeigen (beide Quellen) und Erkennung
"erneut ausgeschrieben"."""
from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from .db import firma_sicherstellen
from .filter import Filter, firmen_schluessel, titel_aehnlichkeit


def _datum(text: str | None) -> date | None:
    if not text:
        return None
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError:
        return None


def job_speichern(con: sqlite3.Connection, flt: Filter, job: dict, zeit: str,
                  fundstelle: str | None = None, erstimport: bool = False) -> bool:
    """Legt eine Anzeige an oder aktualisiert sie. Gibt True zurück, wenn sie neu ist."""
    firma_key = firmen_schluessel(job["arbeitgeber"])
    regional = job.get("regional")
    if regional is None:
        regional = flt.ist_regional(job.get("plz"), job.get("lat"), job.get("lon"))
    fachbereiche = ", ".join(sorted(set(job.get("fachbereiche") or [])))

    alt = con.execute("SELECT fundstellen, regional, fachbereiche FROM jobs WHERE id=?",
                      (job["id"],)).fetchone()
    if alt:
        fund = set(json.loads(alt["fundstellen"] or "[]"))
        if fundstelle:
            fund.add(fundstelle)
        fb_alt = {f.strip() for f in (alt["fachbereiche"] or "").split(",") if f.strip()}
        fachbereiche = ", ".join(sorted(fb_alt | set(job.get("fachbereiche") or [])))
        con.execute(
            """UPDATE jobs SET titel=?, arbeitgeber=?, firma_key=?, ort=?, plz=?, strasse=?,
                   lat=?, lon=?, regional=?, fachbereiche=?, veroeffentlicht=COALESCE(?, veroeffentlicht),
                   zuletzt_gesehen=?, online=1, offline_seit=NULL, url=?, externe_url=?,
                   fundstellen=?
               WHERE id=?""",
            (job["titel"], job["arbeitgeber"], firma_key, job.get("ort"), job.get("plz"),
             job.get("strasse"), job.get("lat"), job.get("lon"),
             int(bool(regional) or bool(alt["regional"])), fachbereiche,
             job.get("veroeffentlicht"), zeit, job.get("url"), job.get("externe_url"),
             json.dumps(sorted(fund), ensure_ascii=False), job["id"]),
        )
        return False

    firma_sicherstellen(con, firma_key, job["arbeitgeber"])
    con.execute(
        """INSERT INTO jobs(id, quelle, refnr, titel, arbeitgeber, firma_key, ort, plz, strasse,
               lat, lon, regional, fachbereiche, veroeffentlicht, erstmals_gesehen, zuletzt_gesehen,
               online, kette_start, url, externe_url, fundstellen, erstimport, watch_id)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,1,?,?,?,?,?,?)""",
        (job["id"], job["quelle"], job.get("refnr"), job["titel"], job["arbeitgeber"], firma_key,
         job.get("ort"), job.get("plz"), job.get("strasse"), job.get("lat"), job.get("lon"),
         int(bool(regional)), fachbereiche, job.get("veroeffentlicht"), zeit, zeit,
         job.get("veroeffentlicht") or zeit[:10], job.get("url"), job.get("externe_url"),
         json.dumps([fundstelle] if fundstelle else [], ensure_ascii=False),
         int(erstimport), job.get("watch_id")),
    )
    return True


def erneut_ausgeschrieben_pruefen(con: sqlite3.Connection, cfg: dict) -> int:
    """Markiert Anzeigen, deren Arbeitgeber zuvor schon eine sehr ähnliche Stelle
    (andere Ref.-Nr.) veröffentlicht hatte. Gibt die Anzahl neuer Markierungen zurück."""
    e = cfg.get("erneut_ausgeschrieben") or {}
    schwelle = float(e.get("aehnlichkeit", 0.85))
    abstand = timedelta(days=int(e.get("min_abstand_tage", 14)))
    gleicher_ort = bool(e.get("gleicher_ort", True))

    zeilen = [dict(r) for r in con.execute(
        "SELECT id, quelle, titel, firma_key, ort, veroeffentlicht, erstmals_gesehen, online, "
        "erneut_ausgeschrieben, vorgaenger_id, kette_start FROM jobs ORDER BY firma_key")]
    nach_firma: dict[tuple, list[dict]] = {}
    for z in zeilen:
        nach_firma.setdefault((z["firma_key"], z["quelle"]), []).append(z)

    markiert = 0
    for gruppe in nach_firma.values():
        if len(gruppe) < 2:
            continue
        # älteste zuerst, damit Ketten (A -> B -> C) korrekt entstehen
        gruppe.sort(key=lambda z: (_datum(z["veroeffentlicht"]) or _datum(z["erstmals_gesehen"])
                                   or date.max, z["erstmals_gesehen"] or ""))
        for i, neu in enumerate(gruppe):
            if neu["erneut_ausgeschrieben"]:
                continue
            d_neu = _datum(neu["veroeffentlicht"]) or _datum(neu["erstmals_gesehen"])
            bester, beste_sim = None, 0.0
            for alt in gruppe[:i]:
                if gleicher_ort and alt["ort"] and neu["ort"] and \
                        alt["ort"].strip().lower() != neu["ort"].strip().lower():
                    continue
                d_alt = _datum(alt["veroeffentlicht"]) or _datum(alt["erstmals_gesehen"])
                zeitlich = bool(d_alt and d_neu and d_alt <= d_neu - abstand)
                abgeloest = (not alt["online"]) and (alt["erstmals_gesehen"] or "") < (neu["erstmals_gesehen"] or "")
                if not (zeitlich or abgeloest):
                    continue
                sim = titel_aehnlichkeit(alt["titel"], neu["titel"])
                if sim >= schwelle and sim > beste_sim:
                    bester, beste_sim = alt, sim
            if bester:
                start = min(filter(None, [bester["kette_start"], bester["veroeffentlicht"],
                                          neu["kette_start"]]))
                con.execute("UPDATE jobs SET erneut_ausgeschrieben=1, vorgaenger_id=?, kette_start=? "
                            "WHERE id=?", (bester["id"], start, neu["id"]))
                neu.update(erneut_ausgeschrieben=1, vorgaenger_id=bester["id"], kette_start=start)
                markiert += 1
    con.commit()
    return markiert
