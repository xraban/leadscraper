"""Nachbildung der BA-Jobsuche-API für Tests (Antwortformat wie pc/v4/app/jobs)."""
from __future__ import annotations

from datetime import date, timedelta

# (refnr, titel, arbeitgeber, plz, ort, lat, lon, tage_alt, suchbegriffe)
STANDARD = [
    ("10000-1001-S", "DevOps Engineer (m/w/d)", "Weinheimer Maschinenbau GmbH", "69469", "Weinheim", 49.548, 8.669, 75, ["DevOps Engineer", "Kubernetes"]),
    ("10000-1002-S", "Cloud Engineer Azure (m/w/d)", "Weinheimer Maschinenbau GmbH", "69469", "Weinheim", 49.548, 8.669, 40, ["Cloud Engineer"]),
    ("10000-1003-S", "SAP Basis Administrator (m/w/d)", "Weinheimer Maschinenbau GmbH", "69469", "Weinheim", 49.548, 8.669, 12, ["SAP Basis"]),
    ("10000-1004-S", "Junior DevOps Engineer (m/w/d)", "Weinheimer Maschinenbau GmbH", "69469", "Weinheim", 49.548, 8.669, 5, ["DevOps Engineer"]),
    ("10000-2001-S", "SAP Berater FI/CO (m/w/d)", "Bergstraße Logistik AG", "64625", "Bensheim", 49.681, 8.617, 120, ["SAP Berater"]),
    ("10000-2002-S", "SAP Berater FI/CO (m/w/d)", "Bergstraße Logistik AG", "64625", "Bensheim", 49.681, 8.617, 20, ["SAP Berater"]),
    ("10000-3001-S", "IT Security Engineer (m/w/d)", "Hays Professional Solutions GmbH", "68161", "Mannheim", 49.487, 8.466, 10, ["IT Security Engineer"]),
    ("10000-3002-S", "Data Engineer (m/w/d)", "Kurpfalz Personalservice GmbH", "69115", "Heidelberg", 49.398, 8.672, 8, ["Data Engineer"]),
    ("10000-4001-S", "Softwareentwickler Java (m/w/d)", "Hamburger Reederei Software GmbH", "20457", "Hamburg", 53.541, 9.984, 60, ["Softwareentwickler Java"]),
    ("10000-4002-S", "Werkstudent Softwareentwicklung (m/w/d)", "Hamburger Reederei Software GmbH", "20457", "Hamburg", 53.541, 9.984, 3, ["Softwareentwickler Java"]),
    ("10000-5001-S", "Embedded Softwareentwickler C/C++ (m/w/d)", "Odenwald Elektronik GmbH & Co. KG", "64711", "Erbach", 49.657, 8.994, 95, ["Embedded Softwareentwickler"]),
    ("10000-5002-S", "Systemadministrator Linux (m/w/d)", "Odenwald Elektronik GmbH", "64711", "Erbach", 49.657, 8.994, 30, ["Systemadministrator Linux"]),
    ("10000-6001-S", "Netzwerkadministrator (m/w/d)", "Stadtwerke Darmstadt Digital GmbH", "64283", "Darmstadt", 49.872, 8.651, 50, ["Netzwerkadministrator"]),
    ("10000-7001-S", "IT-Projektleiter (m/w/d)", "Münchner Versicherungs-IT AG", "80331", "München", 48.137, 11.575, 25, ["IT-Projektleiter"]),
    ("10000-8001-S", "Softwareentwickler .NET (m/w/d)", "SAP SE", "69190", "Walldorf", 49.293, 8.642, 15, ["Softwareentwickler .NET"]),
    ("10000-9001-S", "Ausbildung Fachinformatiker Systemintegration", "Odenwald Elektronik GmbH", "64711", "Erbach", 49.657, 8.994, 2, ["Systemadministrator Linux"]),
]

BIRKENAU = (49.5626, 8.7065)


def _km(lat, lon):
    from stellenradar.filter import entfernung_km
    return entfernung_km(lat, lon, *BIRKENAU)


class FakeResponse:
    def __init__(self, status, daten=None, headers=None):
        self.status_code = status
        self._daten = daten
        self.headers = headers or {}

    def json(self):
        if self._daten is None:
            raise ValueError("kein JSON")
        return self._daten


class FakeSession:
    """Simuliert die API. `stellen` kann zwischen Läufen verändert werden."""

    def __init__(self, stellen=None, heute=None, v4_status=200, fehler_bei=None):
        self.stellen = list(stellen if stellen is not None else STANDARD)
        self.heute = heute or date.today()
        self.v4_status = v4_status
        self.fehler_bei = fehler_bei or set()     # Suchbegriffe, die HTTP 500 liefern
        self.headers = {}
        self.aufrufe = []

    def get(self, url, params=None, timeout=None):
        self.aufrufe.append((url, dict(params)))
        assert self.headers.get("X-API-Key") == "jobboerse-jobsuche"
        if url.endswith("pc/v4/app/jobs") and self.v4_status != 200:
            return FakeResponse(self.v4_status)
        if params["was"] in self.fehler_bei:
            return FakeResponse(500)
        treffer = []
        for refnr, titel, ag, plz, ort, lat, lon, alt, begriffe in self.stellen:
            if params["was"] not in begriffe:
                continue
            if "wo" in params and _km(lat, lon) > int(params["umkreis"]):
                continue
            treffer.append({
                "beruf": titel.split(" (")[0], "titel": titel, "refnr": refnr, "arbeitgeber": ag,
                "aktuelleVeroeffentlichungsdatum": (self.heute - timedelta(days=alt)).isoformat(),
                "modifikationsTimestamp": "2026-01-01T10:00:00.000",
                "arbeitsort": {"plz": plz, "ort": ort, "region": "x", "land": "Deutschland",
                               "koordinaten": {"lat": lat, "lon": lon}},
            })
        size, page = int(params["size"]), int(params["page"])
        seite = treffer[(page - 1) * size: page * size]
        return FakeResponse(200, {"stellenangebote": seite, "maxErgebnisse": str(len(treffer)),
                                  "page": str(page), "size": str(size)})
