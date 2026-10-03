"""Stellen-Radar – Dashboard (Streamlit).  Start:  streamlit run dashboard.py"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import yaml

from stellenradar import arbeitsagentur, briefe, db, watchlist
from stellenradar.config import CONFIG_DATEI, STATUS_WERTE, ConfigFehler, lade_config, pfad
from stellenradar.export import excel_bytes
from stellenradar.filter import Filter, blacklist_hinzufuegen
from stellenradar.protokoll import logging_einrichten
from stellenradar.scoring import firmen_uebersicht, jobs_laden

st.set_page_config(page_title="Stellen-Radar", page_icon="📡", layout="wide")

try:
    CFG = lade_config()
except ConfigFehler as e:
    st.error(str(e))
    st.info("Bitte korrigieren Sie die Datei config.yaml im Programmordner und laden Sie die Seite neu.")
    st.stop()

FLT = Filter(CFG)
logging_einrichten(CFG)   # Fortschritt im Konsolenfenster + Logdatei im Ordner logs
CON = db.verbinden(pfad(CFG, CFG.get("datenbank", "daten/stellenradar.db")))


def _datum_de(text) -> str:
    if not text:
        return ""
    try:
        return datetime.fromisoformat(str(text)).strftime("%d.%m.%Y")
    except ValueError:
        return str(text)


def _als_datum(text):
    try:
        return date.fromisoformat(str(text)[:10]) if text else None
    except ValueError:
        return None


# ===================================================================== Seitenleiste
with st.sidebar:
    st.title("📡 Stellen-Radar")
    letzter = db.letzter_erfolgreicher_lauf(CON, arbeitsagentur.QUELLE)
    st.caption("Letzter Abruf Arbeitsagentur: " + (_datum_de(letzter["ende"]) + " " + letzter["ende"][11:16]
                                                   if letzter else "noch keiner"))
    if st.button("🔄 Daten jetzt abrufen", width="stretch",
                 help="Holt neue Anzeigen von der Arbeitsagentur und den Watchlist-Karriereseiten. "
                      "Dauert einige Minuten."):
        with st.status("Abruf läuft …", expanded=True) as status:
            balken = st.progress(0.0, text="Arbeitsagentur …")
            try:
                erg = arbeitsagentur.abrufen(CON, CFG, FLT, erzwingen=True,
                                             fortschritt=lambda p, t: balken.progress(p, text=t))
                st.write(f"Arbeitsagentur: {erg['gefunden']} Anzeigen, davon {erg['neu']} neu, "
                         f"{erg['offline']} offline, {erg['erneut']} erneut ausgeschrieben.")
                for m in erg["meldungen"]:
                    st.warning(m)
                balken.progress(0.0, text="Karriereseiten …")
                werg = watchlist.alle_abrufen(CON, CFG, FLT, fortschritt=lambda p, t: balken.progress(p, text=t))
                st.write(f"Karriereseiten: {werg.get('abgerufen', 0)} abgerufen, "
                         f"{werg.get('neu', 0)} neue IT-Stellen.")
                if erg.get("gefunden", 0) == 0 or not erg.get("erfolgreich"):
                    status.update(label="Abruf mit Problemen – Details hier", state="error", expanded=True)
                    st.info("Bitte die Meldungen oben beachten. Die Dateien api_antwort_*.txt im Ordner "
                            "„logs“ zeigen, was die Arbeitsagentur geantwortet hat.")
                else:
                    status.update(label="Abruf fertig", state="complete")
            except Exception as e:  # noqa: BLE001
                status.update(label="Abruf fehlgeschlagen", state="error")
                st.error(f"Fehler: {e}")

    st.header("Filter")
    f_suche = st.text_input("Firmenname enthält")
    f_region = st.radio("Region", ["Alle", "Nur Region", "Nur außerhalb"], horizontal=True)
    alle_fb = list((CFG.get("fachbereiche") or {}).keys())
    f_fb = st.multiselect("Fachbereich", alle_fb, placeholder="alle")
    f_status = st.multiselect("Status", STATUS_WERTE, placeholder="alle")
    f_neu = st.checkbox("Nur neue seit gestern")
    f_erneut = st.checkbox("Nur erneut ausgeschriebene")
    f_pdl = st.checkbox("Personaldienstleister ausblenden")
    f_bl = st.checkbox("Blacklist-Firmen anzeigen")
    f_ohne = st.checkbox("Auch Firmen ohne offene Stellen")


# ===================================================================== Daten
df = firmen_uebersicht(CON, CFG, FLT)
gefiltert = df.copy()
if not gefiltert.empty:
    if f_suche:
        gefiltert = gefiltert[gefiltert["Firma"].str.contains(f_suche, case=False, regex=False)]
    if f_region == "Nur Region":
        gefiltert = gefiltert[gefiltert["Regional"]]
    elif f_region == "Nur außerhalb":
        gefiltert = gefiltert[~gefiltert["Regional"]]
    if f_fb:
        gefiltert = gefiltert[gefiltert["Fachbereiche"].apply(lambda s: any(fb in s.split(", ") for fb in f_fb))]
    if f_status:
        gefiltert = gefiltert[gefiltert["Status"].isin(f_status)]
    if f_neu:
        gefiltert = gefiltert[gefiltert["Neu"] != ""]
    if f_erneut:
        gefiltert = gefiltert[gefiltert["Erneut ausgeschrieben"]]
    if f_pdl:
        gefiltert = gefiltert[~gefiltert["Personaldienstleister?"]]
    if not f_bl:
        gefiltert = gefiltert[~gefiltert["Blacklist"]]
    if not f_ohne:
        gefiltert = gefiltert[gefiltert["Offene Stellen"] > 0]
    gefiltert = gefiltert.reset_index(drop=True)

tab_firmen, tab_watch, tab_einst = st.tabs(["🏢 Firmen", "👀 Karriereseiten-Watchlist", "⚙️ Blacklist & Einstellungen"])

# ===================================================================== Firmen
with tab_firmen:
    if df.empty:
        st.info("Noch keine Daten vorhanden. Klicken Sie links auf **„Daten jetzt abrufen“** "
                "(dauert beim ersten Mal einige Minuten).")
    else:
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Firmen (gefiltert)", len(gefiltert))
        k2.metric("Offene IT-Stellen", int(gefiltert["Offene Stellen"].sum()))
        k3.metric("Firmen mit neuen Stellen", int((gefiltert["Neu"] != "").sum()))
        k4.metric("Erneut ausgeschrieben", int(gefiltert["Erneut ausgeschrieben"].sum()))

        anzeige = gefiltert.drop(columns=["firma_key", "Blacklist"])
        anzeige = anzeige[["Firma", "Neu"] + [c for c in anzeige.columns if c not in ("Firma", "Neu")]]

        def _hervorheben(zeile):
            if zeile["Neu"] == "NEU (Karriereseite)":
                farbe = "background-color: rgba(255, 196, 0, 0.30)"
            elif zeile["Neu"]:
                farbe = "background-color: rgba(0, 180, 90, 0.18)"
            else:
                farbe = ""
            return [farbe] * len(zeile)

        st.caption("Zeile anklicken, um Details zu sehen. Gelb = neue Stelle auf Karriereseite, "
                   "grün = neue Anzeige seit gestern.")
        auswahl = st.dataframe(
            anzeige.style.apply(_hervorheben, axis=1),
            key="firmen_tabelle", on_select="rerun", selection_mode="single-row",
            hide_index=True, width="stretch", height=min(560, 38 + 35 * max(len(anzeige), 1)),
            column_config={
                "Score": st.column_config.ProgressColumn("Score", format="%.0f", min_value=0,
                                                         max_value=max(1.0, float(df["Score"].max()))),
                "Erneut ausgeschrieben": st.column_config.CheckboxColumn("Erneut ausg."),
                "Regional": st.column_config.CheckboxColumn("Regional"),
                "Personaldienstleister?": st.column_config.CheckboxColumn("PDL?"),
                "Älteste Anzeige (Tage)": st.column_config.NumberColumn("Älteste (Tage)"),
                "Neu": st.column_config.TextColumn("Neu", width="medium"),
                "Firma": st.column_config.TextColumn("Firma", width="medium"),
            },
        )
        st.download_button(
            "📥 Tabelle als Excel exportieren", data=excel_bytes(gefiltert, CON),
            file_name=f"stellen-radar_{date.today():%Y-%m-%d}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

        zeilen = auswahl.selection.rows if auswahl and auswahl.selection else []
        if zeilen and zeilen[0] < len(gefiltert):
            st.session_state["firma_key"] = gefiltert.iloc[zeilen[0]]["firma_key"]
        key = st.session_state.get("firma_key")
        if key and key in set(df["firma_key"]):
            zeile = df[df["firma_key"] == key].iloc[0]
            firma = db.firma_laden(CON, key)
            st.divider()
            st.subheader(f"{zeile['Firma']}")
            st.caption(f"Score {zeile['Score']:g}  ({zeile['Score-Details']})  ·  "
                       f"{'Personaldienstleister-Verdacht · ' if zeile['Personaldienstleister?'] else ''}"
                       f"{'Auf der Blacklist · ' if zeile['Blacklist'] else ''}Quellen: {zeile['Quellen']}")

            # ---------- Anzeigen
            jobs = jobs_laden(CON, key)
            jobs = jobs.sort_values(["online", "veroeffentlicht"], ascending=[False, True])
            heute = date.today()
            tabelle = pd.DataFrame({
                "Titel": jobs["titel"],
                "Link": jobs["url"],
                "Status": jobs["online"].map({1: "online", 0: "offline"}),
                "Erneut ausg.": jobs["erneut_ausgeschrieben"].astype(bool),
                "Offen (Tage)": jobs["kette_start"].map(lambda d: (heute - _als_datum(d)).days if _als_datum(d) else None),
                "Ort": jobs["ort"].fillna("") + " " + jobs["plz"].fillna(""),
                "Veröffentlicht": jobs["veroeffentlicht"].map(_datum_de),
                "Quelle": jobs["quelle"],
                "Erstmals gesehen": jobs["erstmals_gesehen"].map(_datum_de),
                "Zuletzt gesehen": jobs["zuletzt_gesehen"].map(_datum_de),
                "Ref.-Nr.": jobs["refnr"],
            })
            st.markdown(f"**Anzeigen ({int(jobs['online'].sum())} online, "
                        f"{int((jobs['online'] == 0).sum())} offline)**")
            st.dataframe(tabelle, hide_index=True, width="stretch",
                         column_config={"Link": st.column_config.LinkColumn("Link", display_text="Anzeige öffnen")})

            # ---------- Pflegefelder
            st.markdown("**Kontakt & Status**")
            # Vorschlag für die Anschrift aus der Anzeige (Arbeitsort), falls noch leer
            mit_str = jobs.dropna(subset=["strasse"])
            vorschlag = (mit_str if not mit_str.empty else jobs).head(1).fillna("")
            with st.form(f"form_{key}"):
                c1, c2, c3 = st.columns([1, 2, 2])
                anreden = ["", "Herr", "Frau"]
                anrede = c1.selectbox("Anrede", anreden, index=anreden.index(firma.get("anrede") or "")
                                      if (firma.get("anrede") or "") in anreden else 0)
                person = c2.text_input("Name", firma.get("person") or "")
                position = c3.text_input("Position", firma.get("position") or "")
                c4, c5, c6 = st.columns([2, 1, 2])
                strasse = c4.text_input("Straße", firma.get("strasse") or
                                        (vorschlag["strasse"].iloc[0] if not vorschlag.empty else ""))
                plz = c5.text_input("PLZ", firma.get("plz") or (vorschlag["plz"].iloc[0] if not vorschlag.empty else ""))
                ort = c6.text_input("Ort", firma.get("ort") or (vorschlag["ort"].iloc[0] if not vorschlag.empty else ""))
                linkedin = st.text_input("LinkedIn-Link", firma.get("linkedin") or "")
                c7, c8 = st.columns(2)
                status_alt = firma.get("status") or "Neu"
                status = c7.selectbox("Status", STATUS_WERTE, index=STATUS_WERTE.index(status_alt)
                                      if status_alt in STATUS_WERTE else 0)
                aktion = c8.date_input("Datum der letzten Aktion", value=_als_datum(firma.get("letzte_aktion")),
                                       format="DD.MM.YYYY")
                notizen = st.text_area("Notizen", firma.get("notizen") or "", height=120)
                if st.form_submit_button("💾 Speichern", type="primary"):
                    if status != status_alt and aktion == _als_datum(firma.get("letzte_aktion")):
                        aktion = date.today()   # Statuswechsel -> Datum automatisch auf heute
                    db.firma_speichern(CON, key, dict(
                        anrede=anrede, person=person.strip(), position=position.strip(),
                        strasse=strasse.strip(), plz=plz.strip(), ort=ort.strip(), linkedin=linkedin.strip(),
                        status=status, letzte_aktion=aktion.isoformat() if aktion else None, notizen=notizen))
                    st.success("Gespeichert.")
                    st.rerun()
            if firma.get("linkedin"):
                st.link_button("LinkedIn öffnen", firma["linkedin"])

            # ---------- Brief
            with st.expander("✉️ Brief erstellen", expanded=False):
                b_vor, e_vor = briefe.vorschlag(CFG, str(zeile["Firma"]), jobs)
                if st.button("↺ Vorschlag neu laden", key=f"reset_{key}"):
                    st.session_state[f"betreff_{key}"] = b_vor
                    st.session_state[f"einstieg_{key}"] = e_vor
                betreff = st.text_input("Betreff", value=b_vor, key=f"betreff_{key}")
                einstieg = st.text_area("Einstiegssatz", value=e_vor, key=f"einstieg_{key}", height=110)
                st.caption("QR-Code führt zu: " + briefe.qr_link(CFG, str(zeile["Firma"])))
                if not (firma.get("strasse") and firma.get("ort")):
                    st.warning("Für den Fensterumschlag fehlt noch die Anschrift (Straße/Ort). "
                               "Bitte oben unter „Kontakt & Status“ eintragen und speichern.")
                if st.button("📄 Brief erstellen", type="primary", key=f"brief_{key}"):
                    try:
                        pdf = briefe.brief_erstellen(CFG, firma, str(zeile["Firma"]), betreff, einstieg)
                    except Exception as e:  # noqa: BLE001
                        st.error(f"Brief konnte nicht erstellt werden: {e}")
                    else:
                        notiz = (firma.get("notizen") or "").rstrip()
                        notiz += ("\n" if notiz else "") + f"{date.today():%d.%m.%Y}: Brief erstellt – {betreff}"
                        db.firma_speichern(CON, key, {"status": "Brief raus",
                                                      "letzte_aktion": date.today().isoformat(),
                                                      "notizen": notiz})
                        st.session_state["letzter_brief"] = (key, str(pdf))
                        st.rerun()
                letzter_brief = st.session_state.get("letzter_brief")
                if letzter_brief and letzter_brief[0] == key and Path(letzter_brief[1]).exists():
                    pdf = Path(letzter_brief[1])
                    st.success(f"Brief erstellt und Status auf „Brief raus“ gesetzt. Gespeichert unter: {pdf}")
                    st.download_button("⬇️ PDF herunterladen", pdf.read_bytes(), file_name=pdf.name,
                                       mime="application/pdf", key=f"dl_{key}")

            if not zeile["Blacklist"]:
                if st.button("🚫 Firma auf die Blacklist setzen", key=f"bl_{key}"):
                    blacklist_hinzufuegen(FLT.blacklist_datei, str(zeile["Firma"]))
                    st.session_state.pop("firma_key", None)
                    st.rerun()
        else:
            st.info("👆 Wählen Sie oben eine Firma aus, um die Anzeigen zu sehen, Kontaktdaten zu pflegen "
                    "und einen Brief zu erstellen.")

# ===================================================================== Watchlist
with tab_watch:
    st.markdown("Tragen Sie Firmen mit ihrer **Karriereseiten-URL** ein. Das Tool erkennt das "
                "Bewerbermanagement-System (Personio, softgarden, JOIN, Recruitee …) und nutzt – wenn "
                "vorhanden – den öffentlichen Job-Feed. Seiten ohne Feed werden höchstens einmal täglich "
                "abgerufen, robots.txt wird beachtet.")
    with st.form("watch_neu", clear_on_submit=True):
        c1, c2, c3 = st.columns([2, 3, 1])
        w_firma = c1.text_input("Firma (wie sie in der Übersicht erscheinen soll)")
        w_url = c2.text_input("Karriereseiten-URL", placeholder="https://firma.jobs.personio.de")
        c3.write("")
        if c3.form_submit_button("➕ Hinzufügen") and w_firma and w_url:
            url = w_url.strip()
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
            if any(e["url"].rstrip("/") == url.rstrip("/") for e in db.watchlist_laden(CON)):
                st.warning("Diese Karriereseite steht schon auf der Watchlist.")
            else:
                wid = db.watchlist_hinzufuegen(CON, w_firma, url)
                with st.spinner("Erkenne System und rufe Stellen ab …"):
                    erg = watchlist.eintrag_abrufen(CON, CFG, FLT, wid, erzwingen=True)
                if erg.get("status") == "ok":
                    st.success(f"Hinzugefügt – {erg.get('meldung', '')}")
                else:
                    st.warning(f"Hinzugefügt, aber noch keine Stellen gelesen: {erg.get('meldung', '')}")

    eintraege = db.watchlist_laden(CON)
    if eintraege:
        wdf = pd.DataFrame(eintraege)
        it_stellen = {r[0]: r[1] for r in CON.execute(
            "SELECT watch_id, COUNT(*) FROM jobs WHERE quelle='Karriereseite' AND online=1 GROUP BY watch_id")}
        wdf["IT-Stellen"] = wdf["id"].map(it_stellen).fillna(0).astype(int)
        wdf["aktiv"] = wdf["aktiv"].astype(bool)
        wdf["system"] = [(f"{sy} (Feed)" if fu else sy) if sy else "noch nicht erkannt"
                         for sy, fu in zip(wdf["system"], wdf["feed_url"])]
        wdf["letzte_meldung"] = wdf["letzte_meldung"].fillna("")
        wdf["Löschen"] = False
        wdf["letzter_abruf"] = wdf["letzter_abruf"].map(lambda t: (_datum_de(t) + " " + t[11:16]) if t else "")
        bearbeitet = st.data_editor(
            wdf[["id", "firma", "url", "aktiv", "system", "IT-Stellen", "letzter_abruf", "letzte_meldung", "Löschen"]],
            key="watch_editor", hide_index=True, width="stretch",
            disabled=["id", "system", "IT-Stellen", "letzter_abruf", "letzte_meldung"],
            column_config={
                "id": None, "firma": "Firma", "url": st.column_config.LinkColumn("Karriereseite"),
                "aktiv": "Aktiv", "system": "System / Feed", "letzter_abruf": "Letzter Abruf",
                "letzte_meldung": "Meldung", "Löschen": st.column_config.CheckboxColumn("Löschen"),
            })
        c1, c2 = st.columns(2)
        if c1.button("💾 Änderungen speichern"):
            for _, r in bearbeitet.iterrows():
                if r["Löschen"]:
                    db.watchlist_loeschen(CON, int(r["id"]))
                else:
                    alt = next(e for e in eintraege if e["id"] == r["id"])
                    aenderung = {"firma": r["firma"], "url": r["url"], "aktiv": int(bool(r["aktiv"]))}
                    if r["url"] != alt["url"]:
                        aenderung.update(system=None, feed_url=None, seite_url=None, letzter_abruf=None,
                                         erstabruf_erledigt=0)   # neu erkennen
                    db.watchlist_aendern(CON, int(r["id"]), **aenderung)
            st.success("Gespeichert.")
            st.rerun()
        if c2.button("🔄 Alle Karriereseiten jetzt prüfen"):
            with st.spinner("Rufe Karriereseiten ab …"):
                erg = watchlist.alle_abrufen(CON, CFG, FLT, erzwingen=True)
            st.success(f"{erg.get('abgerufen', 0)} Seiten abgerufen, {erg.get('neu', 0)} neue IT-Stellen.")
            st.rerun()
    else:
        st.info("Die Watchlist ist noch leer.")

# ===================================================================== Einstellungen
with tab_einst:
    st.subheader("Blacklist")
    st.caption("Ein Arbeitgeber pro Zeile. Ohne Rechtsform (z. B. „Siemens“) passt der Eintrag auf alle "
               "Firmen mit diesem Wort, mit Rechtsform (z. B. „SAP SE“) nur auf genau diese Firma.")
    bl_text = FLT.blacklist_datei.read_text(encoding="utf-8") if FLT.blacklist_datei.exists() else ""
    neu_bl = st.text_area("blacklist.txt", bl_text, height=300, label_visibility="collapsed")
    if st.button("💾 Blacklist speichern"):
        FLT.blacklist_datei.write_text(neu_bl, encoding="utf-8")
        st.success("Blacklist gespeichert.")
        st.rerun()

    st.subheader("Einstellungen (config.yaml)")
    st.caption("Suchbegriffe, Region, Scoring-Gewichtung, Briefvorschläge. Achtung: Einrückungen beibehalten.")
    cfg_text = CONFIG_DATEI.read_text(encoding="utf-8")
    neu_cfg = st.text_area("config.yaml", cfg_text, height=500, label_visibility="collapsed")
    if st.button("💾 Einstellungen speichern"):
        try:
            yaml.safe_load(neu_cfg)
        except yaml.YAMLError as e:
            st.error(f"Formatfehler – nicht gespeichert:\n\n{e}")
        else:
            CONFIG_DATEI.write_text(neu_cfg, encoding="utf-8")
            st.success("Einstellungen gespeichert.")
            st.rerun()

    st.subheader("Letzte Abrufe")
    laeufe = pd.read_sql_query(
        "SELECT quelle AS Quelle, start AS Start, ende AS Ende, "
        "CASE erfolgreich WHEN 1 THEN 'ja' ELSE 'nein' END AS Erfolgreich, anfragen AS Anfragen, "
        "gefunden AS Gefunden, neu AS Neu, offline AS Offline, erneut AS 'Erneut ausg.', meldungen AS Meldungen "
        "FROM laeufe ORDER BY id DESC LIMIT 20", CON)
    st.dataframe(laeufe, hide_index=True, width="stretch")
