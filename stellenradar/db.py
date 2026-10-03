"""SQLite-Datenbank: Anzeigen, Firmen (mit eigenen Pflegefeldern), Watchlist, Abrufe."""
from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

SCHEMA = """
CREATE TABLE IF NOT EXISTS jobs (
    id                    TEXT PRIMARY KEY,   -- Ref.-Nr. (Arbeitsagentur) bzw. KS:<watch>:<id>
    quelle                TEXT NOT NULL,      -- 'Arbeitsagentur' | 'Karriereseite'
    refnr                 TEXT,
    titel                 TEXT,
    arbeitgeber           TEXT,
    firma_key             TEXT,
    ort                   TEXT,
    plz                   TEXT,
    strasse               TEXT,
    lat                   REAL,
    lon                   REAL,
    regional              INTEGER DEFAULT 0,
    fachbereiche          TEXT,
    veroeffentlicht       TEXT,               -- Datum laut Anzeige (JJJJ-MM-TT)
    erstmals_gesehen      TEXT,
    zuletzt_gesehen       TEXT,
    online                INTEGER DEFAULT 1,
    offline_seit          TEXT,
    erneut_ausgeschrieben INTEGER DEFAULT 0,
    vorgaenger_id         TEXT,
    kette_start           TEXT,               -- Datum der ersten Anzeige der Kette
    url                   TEXT,
    externe_url           TEXT,
    fundstellen           TEXT,               -- JSON: ["regional|DevOps Engineer", ...]
    erstimport            INTEGER DEFAULT 0,  -- beim allerersten Abruf gefunden
    watch_id              INTEGER
);
CREATE INDEX IF NOT EXISTS ix_jobs_firma ON jobs(firma_key);
CREATE INDEX IF NOT EXISTS ix_jobs_online ON jobs(online);

CREATE TABLE IF NOT EXISTS firmen (
    firma_key     TEXT PRIMARY KEY,
    name          TEXT,
    anrede        TEXT,
    person        TEXT,
    position      TEXT,
    strasse       TEXT,
    plz           TEXT,
    ort           TEXT,
    linkedin      TEXT,
    status        TEXT DEFAULT 'Neu',
    letzte_aktion TEXT,
    notizen       TEXT,
    aktualisiert  TEXT
);

CREATE TABLE IF NOT EXISTS watchlist (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    firma              TEXT NOT NULL,
    url                TEXT NOT NULL,
    system             TEXT,
    feed_url           TEXT,
    seite_url          TEXT,               -- erkannte Stellenseite des Systems
    aktiv              INTEGER DEFAULT 1,
    letzter_abruf      TEXT,
    letzter_erfolg     TEXT,
    letzte_meldung     TEXT,
    erstabruf_erledigt INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS laeufe (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    quelle         TEXT,
    start          TEXT,
    ende           TEXT,
    erfolgreich    INTEGER,
    anfragen       INTEGER,
    gefunden       INTEGER,
    neu            INTEGER,
    offline        INTEGER,
    erneut         INTEGER,
    meldungen      TEXT
);
"""

FIRMEN_FELDER = ["anrede", "person", "position", "strasse", "plz", "ort", "linkedin",
                 "status", "letzte_aktion", "notizen"]


def jetzt() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def verbinden(db_pfad: Path | str) -> sqlite3.Connection:
    db_pfad = Path(db_pfad)
    db_pfad.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(db_pfad), timeout=30)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA journal_mode=WAL")
    con.execute("PRAGMA foreign_keys=ON")
    con.executescript(SCHEMA)
    _migrieren(con)
    return con


def _migrieren(con: sqlite3.Connection) -> None:
    """Ergänzt Spalten, die in neueren Versionen hinzugekommen sind."""
    neu = {"watchlist": {"seite_url": "TEXT"}}
    for tabelle, spalten in neu.items():
        vorhanden = {r[1] for r in con.execute(f"PRAGMA table_info({tabelle})")}
        for name, typ in spalten.items():
            if name not in vorhanden:
                con.execute(f"ALTER TABLE {tabelle} ADD COLUMN {name} {typ}")
    con.commit()


# ---------------------------------------------------------------- Firmen
def firma_sicherstellen(con: sqlite3.Connection, firma_key: str, name: str) -> None:
    con.execute(
        "INSERT OR IGNORE INTO firmen(firma_key, name, status) VALUES (?, ?, 'Neu')",
        (firma_key, name),
    )


def firma_laden(con: sqlite3.Connection, firma_key: str) -> dict:
    row = con.execute("SELECT * FROM firmen WHERE firma_key=?", (firma_key,)).fetchone()
    return dict(row) if row else {}


def firma_speichern(con: sqlite3.Connection, firma_key: str, werte: dict) -> None:
    felder = {k: v for k, v in werte.items() if k in FIRMEN_FELDER}
    if not felder:
        return
    felder["aktualisiert"] = jetzt()
    sets = ", ".join(f"{k}=?" for k in felder)
    con.execute(f"UPDATE firmen SET {sets} WHERE firma_key=?", (*felder.values(), firma_key))
    con.commit()


# ---------------------------------------------------------------- Watchlist
def watchlist_laden(con: sqlite3.Connection, nur_aktiv: bool = False) -> list[dict]:
    sql = "SELECT * FROM watchlist" + (" WHERE aktiv=1" if nur_aktiv else "") + " ORDER BY firma"
    return [dict(r) for r in con.execute(sql)]


def watchlist_hinzufuegen(con: sqlite3.Connection, firma: str, url: str) -> int:
    cur = con.execute("INSERT INTO watchlist(firma, url) VALUES (?, ?)", (firma.strip(), url.strip()))
    con.commit()
    return cur.lastrowid


def watchlist_aendern(con: sqlite3.Connection, wid: int, **werte) -> None:
    erlaubt = {"firma", "url", "system", "feed_url", "seite_url", "aktiv", "letzter_abruf",
               "letzter_erfolg", "letzte_meldung", "erstabruf_erledigt"}
    werte = {k: v for k, v in werte.items() if k in erlaubt}
    if werte:
        sets = ", ".join(f"{k}=?" for k in werte)
        con.execute(f"UPDATE watchlist SET {sets} WHERE id=?", (*werte.values(), wid))
        con.commit()


def watchlist_loeschen(con: sqlite3.Connection, wid: int) -> None:
    con.execute("DELETE FROM jobs WHERE watch_id=? AND quelle='Karriereseite'", (wid,))
    con.execute("DELETE FROM watchlist WHERE id=?", (wid,))
    con.commit()


# ---------------------------------------------------------------- Läufe
def letzter_erfolgreicher_lauf(con: sqlite3.Connection, quelle: str) -> dict | None:
    row = con.execute(
        "SELECT * FROM laeufe WHERE quelle=? AND erfolgreich=1 ORDER BY id DESC LIMIT 1", (quelle,)
    ).fetchone()
    return dict(row) if row else None


def lauf_speichern(con: sqlite3.Connection, **werte) -> None:
    spalten = ", ".join(werte)
    fragen = ", ".join("?" for _ in werte)
    con.execute(f"INSERT INTO laeufe({spalten}) VALUES ({fragen})", tuple(werte.values()))
    con.commit()
