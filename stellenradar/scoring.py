"""Firmenübersicht und Scoring."""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pandas as pd

from .filter import Filter

SPALTEN = ["firma_key", "Firma", "Score", "Offene Stellen", "Älteste Anzeige (Tage)",
           "Erneut ausgeschrieben", "Regional", "Neu", "Fachbereiche", "Orte", "Quellen",
           "Personaldienstleister?", "Blacklist", "Status", "Letzte Aktion", "Ansprechpartner",
           "Score-Details"]


def _tage(datum_text: str | None, heute: date) -> int | None:
    if not datum_text:
        return None
    try:
        return (heute - date.fromisoformat(str(datum_text)[:10])).days
    except ValueError:
        return None


def score_berechnen(cfg: dict, stellen: int, alter_tage: int, erneut: bool, regional: bool,
                    pdl: bool) -> tuple[float, str]:
    s = cfg.get("scoring") or {}
    p_stellen = min(stellen * float(s.get("punkte_pro_stelle", 10)), float(s.get("max_punkte_stellen", 50)))
    p_alter = min(max(alter_tage, 0) * float(s.get("punkte_pro_tag_offen", 0.5)),
                  float(s.get("max_punkte_alter", 30)))
    p_erneut = float(s.get("bonus_erneut_ausgeschrieben", 20)) if erneut else 0.0
    p_reg = float(s.get("bonus_regional", 25)) if regional else 0.0
    p_pdl = -float(s.get("abzug_personaldienstleister", 0)) if pdl else 0.0
    gesamt = round(p_stellen + p_alter + p_erneut + p_reg + p_pdl, 1)
    teile = [f"Stellen {p_stellen:g}", f"Alter {p_alter:g}"]
    if p_erneut:
        teile.append(f"erneut +{p_erneut:g}")
    if p_reg:
        teile.append(f"regional +{p_reg:g}")
    if p_pdl:
        teile.append(f"PDL {p_pdl:g}")
    return gesamt, ", ".join(teile)


def jobs_laden(con, firma_key: str | None = None) -> pd.DataFrame:
    sql = "SELECT * FROM jobs"
    params: tuple = ()
    if firma_key:
        sql += " WHERE firma_key=?"
        params = (firma_key,)
    return pd.read_sql_query(sql, con, params=params)


def firmen_uebersicht(con, cfg: dict, flt: Filter | None = None, heute: date | None = None) -> pd.DataFrame:
    flt = flt or Filter(cfg)
    heute = heute or date.today()
    neu_grenze = (datetime.now() - timedelta(days=float(cfg.get("neu_tage", 1)))).isoformat(sep=" ")
    jobs = [dict(r) for r in con.execute("SELECT * FROM jobs")]
    firmen = {r["firma_key"]: dict(r) for r in con.execute("SELECT * FROM firmen")}

    gruppen: dict[str, list[dict]] = {}
    for j in jobs:
        gruppen.setdefault(j["firma_key"], []).append(j)

    zeilen = []
    for key, js in gruppen.items():
        f = firmen.get(key, {})
        online = [j for j in js if j["online"]]
        basis = online or js
        alter = max((_tage(j["kette_start"] or j["veroeffentlicht"] or j["erstmals_gesehen"], heute) or 0
                     for j in online), default=0)
        erneut = any(j["erneut_ausgeschrieben"] for j in online)
        regional = any(j["regional"] for j in basis)
        # häufigster Arbeitgebername als Anzeigename
        namen = pd.Series([j["arbeitgeber"] for j in js]).value_counts()
        name = f.get("name") or namen.index[0]
        pdl = flt.ist_personaldienstleister(name)
        score, details = score_berechnen(cfg, len(online), alter, erneut, regional, pdl)
        neue = [j for j in online if (j["erstmals_gesehen"] or "") >= neu_grenze and not j["erstimport"]]
        if any(j["quelle"] == "Karriereseite" for j in neue):
            neu = "NEU (Karriereseite)"
        elif neue:
            neu = "NEU"
        else:
            neu = ""
        fbs = sorted({fb.strip() for j in basis for fb in (j["fachbereiche"] or "").split(",") if fb.strip()})
        orte = sorted({j["ort"] for j in basis if j["ort"]})
        person = " ".join(x for x in [f.get("anrede"), f.get("person")] if x)
        zeilen.append({
            "firma_key": key, "Firma": name, "Score": score, "Offene Stellen": len(online),
            "Älteste Anzeige (Tage)": alter, "Erneut ausgeschrieben": erneut, "Regional": regional,
            "Neu": neu, "Fachbereiche": ", ".join(fbs), "Orte": ", ".join(orte),
            "Quellen": ", ".join(sorted({j["quelle"] for j in basis})),
            "Personaldienstleister?": pdl, "Blacklist": flt.ist_blacklist(name),
            "Status": f.get("status") or "Neu", "Letzte Aktion": f.get("letzte_aktion") or "",
            "Ansprechpartner": person, "Score-Details": details,
        })
    df = pd.DataFrame(zeilen, columns=SPALTEN)
    if not df.empty:
        df = df.sort_values(["Score", "Offene Stellen"], ascending=False).reset_index(drop=True)
    return df
