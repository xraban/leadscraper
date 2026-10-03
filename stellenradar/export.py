"""Excel-Export der Firmentabelle (plus Blatt mit allen Anzeigen)."""
from __future__ import annotations

import io

import pandas as pd


def excel_bytes(firmen: pd.DataFrame, con) -> bytes:
    kontakte = pd.read_sql_query(
        "SELECT firma_key, anrede AS Anrede, person AS Name, position AS Position, "
        "strasse AS Straße, plz AS PLZ, ort AS Ort, linkedin AS LinkedIn, notizen AS Notizen "
        "FROM firmen", con)
    tabelle = firmen.drop(columns=["Ansprechpartner"], errors="ignore").merge(
        kontakte, on="firma_key", how="left")
    keys = list(firmen["firma_key"])
    anzeigen = pd.read_sql_query(
        "SELECT firma_key, arbeitgeber AS Arbeitgeber, titel AS Titel, quelle AS Quelle, "
        "ort AS Ort, plz AS PLZ, veroeffentlicht AS Veröffentlicht, erstmals_gesehen AS "
        "'Erstmals gesehen', zuletzt_gesehen AS 'Zuletzt gesehen', "
        "CASE online WHEN 1 THEN 'online' ELSE 'offline' END AS Status, "
        "CASE erneut_ausgeschrieben WHEN 1 THEN 'ja' ELSE '' END AS 'Erneut ausgeschrieben', "
        "refnr AS Referenznummer, url AS Link FROM jobs ORDER BY arbeitgeber, veroeffentlicht", con)
    anzeigen = anzeigen[anzeigen["firma_key"].isin(keys)]

    puffer = io.BytesIO()
    with pd.ExcelWriter(puffer, engine="openpyxl") as xl:
        for name, df in (("Firmen", tabelle), ("Anzeigen", anzeigen)):
            df = df.drop(columns=["firma_key"])
            for spalte in df.columns:
                if df[spalte].dtype == bool:
                    df[spalte] = df[spalte].map({True: "ja", False: ""})
            df.to_excel(xl, sheet_name=name, index=False)
            blatt = xl.sheets[name]
            blatt.freeze_panes = "B2"
            blatt.auto_filter.ref = blatt.dimensions
            for i, spalte in enumerate(df.columns, start=1):
                breite = max([len(str(spalte))] + [len(str(v)) for v in df[spalte].head(200)])
                blatt.column_dimensions[blatt.cell(1, i).column_letter].width = min(max(10, breite + 2), 60)
    return puffer.getvalue()
