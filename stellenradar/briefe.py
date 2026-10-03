"""Briefe: Vorschläge für Betreff/Einstieg, Platzhalter füllen, QR-Code, PDF erzeugen."""
from __future__ import annotations

import base64
import html
import io
import re
from collections import defaultdict
from datetime import date
from pathlib import Path
from urllib.parse import urlencode, urlsplit, urlunsplit

import pandas as pd

from .config import pfad
from .filter import titel_anzeige, titel_normal

MONATE = ["Januar", "Februar", "März", "April", "Mai", "Juni", "Juli", "August",
          "September", "Oktober", "November", "Dezember"]


def slug(text: str) -> str:
    t = (text or "").lower()
    for a, b in (("ä", "ae"), ("ö", "oe"), ("ü", "ue"), ("ß", "ss")):
        t = t.replace(a, b)
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:60] or "firma"


def qr_link(cfg: dict, firmenname: str) -> str:
    basis = (cfg.get("briefe") or {}).get("qr_basis_url", "https://www.ihre-website.de")
    teile = urlsplit(basis)
    query = (teile.query + "&" if teile.query else "") + urlencode(
        {"utm_source": "brief", "utm_campaign": slug(firmenname)})
    return urlunsplit((teile.scheme, teile.netloc, teile.path, query, teile.fragment))


def qr_data_uri(text: str) -> str:
    import qrcode

    qr = qrcode.QRCode(border=1, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(text)
    qr.make(fit=True)
    puffer = io.BytesIO()
    qr.make_image(fill_color="black", back_color="white").save(puffer, format="PNG")
    return "data:image/png;base64," + base64.b64encode(puffer.getvalue()).decode("ascii")


def _datum_lang(d: date) -> str:
    return f"{d.day}. {MONATE[d.month - 1]} {d.year}"


def vorschlag(cfg: dict, firmenname: str, jobs: pd.DataFrame, heute: date | None = None) -> tuple[str, str]:
    """Schlägt Betreff und Einstiegssatz anhand der offenen Stellen vor."""
    b = cfg.get("briefe") or {}
    heute = heute or date.today()
    online = jobs[jobs["online"] == 1].copy() if not jobs.empty else jobs
    if online.empty:
        online = jobs.copy()
    if online.empty:
        return "Ihre offenen IT-Positionen", ""
    online["_start"] = online["kette_start"].fillna(online["veroeffentlicht"]).fillna(online["erstmals_gesehen"])
    online = online.sort_values("_start")            # älteste zuerst
    # gleiche Stelle (z. B. alte + neu ausgeschriebene Anzeige) nur einmal zählen
    online = online.assign(_t=online["titel"].map(titel_normal))
    erneut_titel = set(online.loc[online["erneut_ausgeschrieben"] == 1, "_t"])
    online = online[~(online["_t"].isin(erneut_titel) & (online["erneut_ausgeschrieben"] != 1))]
    online = online.drop_duplicates("_t")
    erneut = online[online["erneut_ausgeschrieben"] == 1]
    haupt = (erneut if not erneut.empty else online).iloc[0]
    andere = online[online["id"] != haupt["id"]]
    try:
        tage = (heute - date.fromisoformat(str(haupt["_start"])[:10])).days
    except ValueError:
        tage = 0
    werte = defaultdict(str, {
        "titel": titel_anzeige(haupt["titel"]),
        "titel2": titel_anzeige(andere.iloc[0]["titel"]) if not andere.empty else "",
        "anzahl": str(len(online)),
        "wochen": str(max(1, round(tage / 7))),
        "firma": firmenname,
        "fachbereich": (haupt.get("fachbereiche") or "").split(",")[0].strip(),
    })
    if len(online) > 1:
        betreff = b.get("betreff_mehrere_stellen", "Ihre {anzahl} offenen IT-Positionen")
    else:
        betreff = b.get("betreff_eine_stelle", "Ihre Vakanz {titel}")
    if not erneut.empty:
        einstieg = b.get("einstieg_erneut", "")
    elif len(online) > 1:
        einstieg = b.get("einstieg_mehrere", "")
    elif tage >= int(b.get("lange_offen_ab_tagen", 42)):
        einstieg = b.get("einstieg_lange_offen", "")
    else:
        einstieg = b.get("einstieg_eine_stelle", "")
    return betreff.format_map(werte), einstieg.format_map(werte)


def briefanrede(anrede: str, person: str) -> str:
    nachname = (person or "").strip().split(" ")[-1] if person else ""
    if anrede == "Herr" and nachname:
        return f"Sehr geehrter Herr {nachname},"
    if anrede == "Frau" and nachname:
        return f"Sehr geehrte Frau {nachname},"
    return "Sehr geehrte Damen und Herren,"


def platzhalter_werte(cfg: dict, firma: dict, firmenname: str, betreff: str, einstieg: str,
                      heute: date | None = None) -> dict[str, str]:
    heute = heute or date.today()
    url = qr_link(cfg, firmenname)
    anrede = firma.get("anrede") or ""
    person = firma.get("person") or ""
    plz = firma.get("plz") or ""
    ort = firma.get("ort") or ""
    zeilen = [firmenname, " ".join(x for x in [anrede, person] if x), firma.get("strasse") or "",
              " ".join(x for x in [plz, ort] if x)]
    e = lambda s: html.escape(s or "")  # noqa: E731
    return {
        "firma": e(firmenname),
        "anrede": e(anrede),
        "person": e(person),
        "position": e(firma.get("position")),
        "strasse": e(firma.get("strasse")),
        "plz": e(plz),
        "nur_ort": e(ort),
        "ort": e(" ".join(x for x in [plz, ort] if x)),
        "anschrift": "<br/>".join(e(z) for z in zeilen if z.strip()),
        "briefanrede": e(briefanrede(anrede, person)),
        "betreff": e(betreff),
        "einstieg": e(einstieg).replace("\n", "<br/>"),
        "datum": e(_datum_lang(heute)),
        "datum_kurz": heute.strftime("%d.%m.%Y"),
        "absender_ort": e((cfg.get("briefe") or {}).get("absender_ort", "")),
        "qr_url": e(url),
        "qr_url_kurz": e((cfg.get("briefe") or {}).get("qr_basis_url", "").split("://")[-1].rstrip("/")),
        "qr_bild": qr_data_uri(url),
    }


def html_fuellen(vorlage: str, werte: dict[str, str]) -> str:
    # <img src="{qr_url}"> -> echtes QR-Bild einsetzen
    vorlage = re.sub(r"""(src\s*=\s*["']?)\{qr_url\}""", lambda m: m.group(1) + "{qr_bild}", vorlage)
    # nur bekannte Platzhalter ersetzen – CSS-Klammern { } bleiben unberührt
    return re.sub(r"\{([a-z_]+)\}", lambda m: werte.get(m.group(1), m.group(0)), vorlage)


def pdf_erzeugen(html_text: str, ziel: Path, basis_ordner: Path) -> None:
    from xhtml2pdf import pisa

    ziel.parent.mkdir(parents=True, exist_ok=True)
    with open(ziel, "wb") as f:
        ergebnis = pisa.CreatePDF(html_text, dest=f, encoding="utf-8",
                                  path=str(basis_ordner / "vorlage.html"))
    if ergebnis.err:
        raise RuntimeError(f"PDF konnte nicht erzeugt werden ({ergebnis.err} Fehler) – bitte Vorlage prüfen.")


def brief_erstellen(cfg: dict, firma: dict, firmenname: str, betreff: str, einstieg: str,
                    heute: date | None = None) -> Path:
    heute = heute or date.today()
    b = cfg.get("briefe") or {}
    vorlage_pfad = pfad(cfg, b.get("vorlage", "vorlagen/brief_vorlage.html"))
    if not vorlage_pfad.exists():
        raise FileNotFoundError(f"Briefvorlage nicht gefunden: {vorlage_pfad}")
    vorlage = vorlage_pfad.read_text(encoding="utf-8")
    html_text = html_fuellen(vorlage, platzhalter_werte(cfg, firma, firmenname, betreff, einstieg, heute))
    ordner = pfad(cfg, b.get("ausgabe_ordner", "briefe"))
    ziel = ordner / f"{heute:%Y-%m-%d}_{slug(firmenname)}.pdf"
    n = 2
    while ziel.exists():
        ziel = ordner / f"{heute:%Y-%m-%d}_{slug(firmenname)}_{n}.pdf"
        n += 1
    pdf_erzeugen(html_text, ziel, vorlage_pfad.parent)
    return ziel
