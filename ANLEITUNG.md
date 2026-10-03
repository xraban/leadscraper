# Stellen-Radar – Anleitung

Stellen-Radar sucht täglich IT-Stellenanzeigen bei der Bundesagentur für Arbeit und auf
Karriereseiten Ihrer Wunschfirmen. Daraus baut es eine nach Score sortierte Firmenliste,
in der Sie Ansprechpartner pflegen, den Status verfolgen und per Klick Anschreiben als PDF
erstellen.

Alles läuft **lokal auf Ihrem Rechner**. Die Daten liegen in einer Datei im Programmordner
(`daten/stellenradar.db`), es gibt keine Cloud und kein Konto.

---

## 1. Einmalig: Python installieren

Stellen-Radar ist in der Programmiersprache Python geschrieben. Python muss einmal
installiert werden (kostenlos, ca. 5 Minuten).

### Windows
1. <https://www.python.org/downloads/> öffnen und auf **„Download Python 3.x“** klicken.
2. Die heruntergeladene Datei starten.
3. **Wichtig:** Unten im ersten Fenster das Häkchen bei **„Add python.exe to PATH“** setzen.
4. Auf **„Install Now“** klicken und warten, bis „Setup was successful“ erscheint.

### Mac
1. <https://www.python.org/downloads/> öffnen und auf **„Download Python 3.x“** klicken.
2. Die heruntergeladene `.pkg`-Datei öffnen und durch die Installation klicken.

---

## 2. Programm herunterladen und entpacken

1. Auf GitHub das Repository **xraban/leadscraper** öffnen. Falls die Änderungen noch nicht
   im Hauptzweig sind: oben links den Zweig **`claude/stellen-radar-tool-ysmlq4`** auswählen.
2. Auf den grünen Knopf **„Code“** → **„Download ZIP“** klicken.
3. Die ZIP-Datei entpacken und den Ordner umbenennen in **`Stellen-Radar`**.
4. Den Ordner an einen festen Ort legen:
   - **Windows:** z. B. `C:\Users\<IhrName>\Stellen-Radar`
   - **Mac:** **direkt in Ihren Benutzerordner** (Finder → Gehe zu → Benutzerordner),
     also `/Users/<IhrName>/Stellen-Radar`. Nicht in „Dokumente“, „Schreibtisch“ oder
     „Downloads“, denn dort blockiert macOS den automatischen täglichen Abruf.

---

## 3. Einmalig: Installieren

### Windows
Im Ordner `Stellen-Radar` doppelklicken auf **`1_Installieren_Windows.bat`**.
Es öffnet sich ein schwarzes Fenster, das einige Minuten Pakete lädt. Am Ende steht „Fertig!“.

> Falls Windows „Der Computer wurde durch Windows geschützt“ meldet:
> auf **„Weitere Informationen“** → **„Trotzdem ausführen“** klicken.

### Mac
Rechtsklick (oder Control-Klick) auf **`1_Installieren_Mac.command`** → **„Öffnen“** →
im Dialog nochmals **„Öffnen“**. Das Terminal-Fenster lädt einige Minuten Pakete.

> Klappt der Doppelklick nicht („kann nicht geöffnet werden“): Programm **Terminal** öffnen,
> `bash ` eintippen (mit Leerzeichen), die Datei ins Terminal-Fenster ziehen und Enter drücken.
> Das funktioniert genauso für alle anderen `.command`-Dateien.

---

## 4. Dashboard starten

- **Windows:** Doppelklick auf **`2_Dashboard_starten_Windows.bat`**
- **Mac:** Doppelklick auf **`2_Dashboard_starten_Mac.command`**

Nach ein paar Sekunden öffnet sich das Dashboard im Browser
(sonst <http://localhost:8501> im Browser aufrufen).
**Das schwarze Fenster bzw. Terminal offen lassen**, denn wenn Sie es schließen, wird das
Dashboard beendet.

### Der erste Abruf
Links auf **„🔄 Daten jetzt abrufen“** klicken. Der erste Abruf dauert einige Minuten,
weil das Tool zwischen den Anfragen absichtlich Pausen macht, um die Arbeitsagentur
nicht zu überlasten. Danach erscheint die Firmenliste.

---

## 5. Jeden Morgen automatisch abrufen

### Windows (empfohlen: per Doppelklick)
1. Doppelklick auf **`4_Taeglich_einrichten_Windows.bat`**.
2. Uhrzeit eingeben (z. B. `07:00`) und Enter drücken.

Fertig. Der Abruf läuft dann jeden Tag unsichtbar im Hintergrund. War der PC zu der Zeit
aus, holt Windows den Abruf beim nächsten Einschalten nach.
Entfernen: **`5_Taeglich_entfernen_Windows.bat`**.

<details>
<summary>Variante B: von Hand in der Windows-Aufgabenplanung einrichten</summary>

1. Startmenü → **„Aufgabenplanung“** eintippen und öffnen.
2. Rechts **„Einfache Aufgabe erstellen …“**.
3. Name: `Stellen-Radar Abruf` → Weiter.
4. Trigger: **Täglich** → Weiter → Uhrzeit (z. B. 07:00) → Weiter.
5. Aktion: **Programm starten** → Weiter.
6. **Programm/Skript:** `C:\Users\<IhrName>\Stellen-Radar\.venv\Scripts\pythonw.exe`
   **Argumente hinzufügen:** `abruf.py`
   **Starten in:** `C:\Users\<IhrName>\Stellen-Radar`
7. Weiter → Häkchen bei „Eigenschaften öffnen“ → Fertig stellen.
8. Reiter **„Einstellungen“** → Häkchen bei **„Aufgabe so schnell wie möglich nach einem
   verpassten Start ausführen“** → OK.
</details>

### Mac
1. Doppelklick auf **`4_Taeglich_einrichten_Mac.command`**.
2. Uhrzeit eingeben (z. B. `07:00`) und Enter drücken.

Der Mac führt den Abruf dann täglich aus. Schläft er um diese Zeit, wird der Abruf beim
Aufwachen nachgeholt. Entfernen: **`5_Taeglich_entfernen_Mac.command`**.

### Von Hand abrufen (ohne Dashboard)
`3_Datenabruf_Windows.bat` bzw. `3_Datenabruf_Mac.command`. Das Protokoll jedes Abrufs
steht im Ordner `logs`.

> Ein Abruf wird automatisch übersprungen, wenn der letzte erfolgreiche weniger als
> 6 Stunden her ist. Der Knopf im Dashboard ruft trotzdem ab.

---

## 6. Bedienung des Dashboards

### Reiter „🏢 Firmen“
- Die Tabelle ist **nach Score sortiert**. Eine Zeile anklicken öffnet die Details darunter.
- **Gelb** hinterlegt: neue IT-Stelle auf einer Watchlist-Karriereseite.
  **Grün** hinterlegt: neue Arbeitsagentur-Anzeige seit gestern.
- **Filter links:** Region, Fachbereich, Status, „Nur neue seit gestern“, „Nur erneut
  ausgeschriebene“, Personaldienstleister ausblenden, Blacklist-Firmen anzeigen.
- **„📥 Tabelle als Excel exportieren“** speichert die gefilterte Tabelle mit Kontaktdaten
  plus ein zweites Blatt mit allen Anzeigen.

**Details einer Firma:**
- Alle Anzeigen mit Link **„Anzeige öffnen“** (arbeitsagentur.de bzw. Karriereseite),
  Status online/offline und wie viele Tage sie schon offen sind.
- **Kontakt & Status:** Anrede, Name, Position, Anschrift, LinkedIn-Link, Status
  (Neu / Brief raus / LinkedIn angefragt / Antwort / Lead an Ben / Raus), Datum der letzten
  Aktion und Notizen. Mit **„💾 Speichern“** sichern. Wenn Sie den Status ändern, wird das
  Datum automatisch auf heute gesetzt. PLZ und Ort werden aus der Anzeige vorgeschlagen.
- **✉️ Brief erstellen:** Betreff und Einstiegssatz werden aus den offenen Stellen
  vorgeschlagen und können vorher geändert werden. Ein Klick auf **„📄 Brief erstellen“**
  erzeugt das PDF im Ordner `briefe`, bietet es zum Herunterladen an, setzt den Status auf
  **„Brief raus“** und vermerkt den Brief in den Notizen.
- **🚫 Firma auf die Blacklist setzen**, damit sie künftig ausgeblendet wird.

### Reiter „👀 Karriereseiten-Watchlist“
- Firmenname und Karriereseiten-URL eintragen → **„➕ Hinzufügen“**.
- Das Tool erkennt automatisch **Personio, Recruitee, Greenhouse, Lever, SmartRecruiters,
  Workable** (öffentlicher Job-Feed) sowie **softgarden** und **JOIN** (Seite wird gelesen).
  Auch eigene Karriereseiten funktionieren, in die eines dieser Systeme eingebunden ist.
  Ist kein System erkennbar, sucht es auf der Seite nach Links, die wie Stellenanzeigen aussehen.
- Nur **IT-Stellen** werden übernommen (erkannt über die Schlüsselwörter in `config.yaml`).
  Sie erscheinen in der Firmenübersicht mit Quelle **„Karriereseite“**.
- Den Firmennamen genauso schreiben wie in der Firmenübersicht, damit beide Quellen
  zusammengeführt werden. Rechtsformen wie „GmbH“ dürfen abweichen.
- Seiten **ohne Feed** werden höchstens einmal täglich abgerufen, und **robots.txt** wird
  beachtet. Verbietet eine Website den Abruf, steht das in der Spalte „Meldung“.
- In der Tabelle können Sie Name/URL ändern, Einträge deaktivieren oder löschen
  (Häkchen setzen → **„💾 Änderungen speichern“**).

### Reiter „⚙️ Blacklist & Einstellungen“
- **Blacklist:** ein Arbeitgeber pro Zeile.
  Ohne Rechtsform (`Siemens`) passt der Eintrag auf alle Firmen mit diesem Wort,
  mit Rechtsform (`SAP SE`) nur auf genau diese Firma.
  Blacklist-Firmen werden nicht gelöscht, sondern nur ausgeblendet.
- **Personaldienstleister** (Name enthält z. B. „Personal“, „Recruiting“, „Hays“, „Randstad“ …)
  werden automatisch **markiert** (Spalte „PDL?“) und bekommen einen Score-Abzug, aber sie
  werden nicht gelöscht.
- **Einstellungen (`config.yaml`):** Suchbegriffe, Region, Score-Gewichtung,
  Brief-Vorschläge. Sie können die Datei hier oder mit einem Texteditor bearbeiten.
  Einrückungen beibehalten!

---

## 7. Wie der Score entsteht

| Bestandteil | Standard | Einstellung in `config.yaml` → `scoring` |
|---|---|---|
| je offene IT-Stelle | 10 Punkte (max. 50) | `punkte_pro_stelle`, `max_punkte_stellen` |
| je Tag, den die älteste Anzeige offen ist | 0,5 Punkte (max. 30) | `punkte_pro_tag_offen`, `max_punkte_alter` |
| eine Stelle wurde erneut ausgeschrieben | +20 | `bonus_erneut_ausgeschrieben` |
| Firma/Stelle liegt in der Region | +25 | `bonus_regional` |
| Verdacht auf Personaldienstleister | −30 | `abzug_personaldienstleister` |

- **Erneut ausgeschrieben:** Dieselbe Firma hat eine sehr ähnliche Stelle (gleicher Ort) mit
  neuer Referenznummer veröffentlicht, und die alte war mindestens 14 Tage älter oder ist
  offline. Das „Offen seit“ zählt dann ab der ersten Anzeige.
- **Offline:** Eine Anzeige taucht beim Abruf nicht mehr auf. Das wird nur markiert, wenn
  alle zugehörigen Suchen fehlerfrei durchliefen, damit ein Netzwerkfehler keine Anzeigen
  fälschlich „offline“ setzt.
- **Region:** Umkreis von 80 km um Birkenau (einstellbar unter `region`), ersatzweise die
  PLZ-Bereiche 68, 69, 64, 67 … oder die von Ihnen gepflegte Firmenanschrift.
- Dieselbe Stelle aus Arbeitsagentur **und** Karriereseite zählt nur einmal.

---

## 8. Eigene Briefvorlage

Die Vorlage liegt unter **`vorlagen/brief_vorlage.html`**. Ersetzen Sie sie durch Ihre
eigene Datei (gleicher Name) oder passen Sie Absender und Text an (Datei mit einem
Texteditor öffnen, z. B. Notepad oder TextEdit).

Verfügbare Platzhalter:

| Platzhalter | Inhalt |
|---|---|
| `{firma}` | Firmenname |
| `{anrede}` | Herr / Frau |
| `{person}` | Name des Ansprechpartners |
| `{position}` | Position |
| `{strasse}` | Straße + Hausnummer |
| `{ort}` | PLZ + Ort (z. B. „69469 Weinheim“) |
| `{plz}`, `{nur_ort}` | PLZ bzw. Ort einzeln |
| `{anschrift}` | komplette Anschrift ohne Leerzeilen |
| `{briefanrede}` | „Sehr geehrter Herr Müller,“ bzw. „Sehr geehrte Damen und Herren,“ |
| `{betreff}`, `{einstieg}` | Betreff und Einstiegssatz aus dem Dashboard |
| `{datum}` / `{datum_kurz}` | „3. Oktober 2026“ / „03.10.2026“ |
| `{qr_url}` | Link mit `?utm_source=brief&utm_campaign=<firmenname>` |
| `<img src="{qr_url}">` | wird automatisch zum **QR-Code-Bild** |
| `{qr_url_kurz}` | Link ohne utm-Zusatz (zum Abdrucken als Text) |

Das Ziel des QR-Codes stellen Sie in `config.yaml` unter `briefe` → `qr_basis_url` ein.
Die Beispielvorlage ist für **Fensterumschläge nach DIN 5008 Form B** eingerichtet
(Anschriftfeld 45 mm von oben, 20 mm von links, mit Falz- und Lochmarken).

> Die PDF-Erzeugung versteht einfaches HTML/CSS (Tabellen, Schriften, Farben, Bilder).
> Für feste Positionen werden `@frame`-Bereiche benutzt (siehe Beispielvorlage).
> Sehr moderne Layouts (Flexbox/Grid) werden nicht unterstützt. Schicken Sie mir Ihre
> Vorlage, dann passe ich sie an.

---

## 9. Datensicherung

Alle Ihre Eingaben (Ansprechpartner, Status, Notizen, Watchlist) stecken in der Datei
**`daten/stellenradar.db`**. Kopieren Sie diese Datei ab und zu an einen sicheren Ort.
Zusätzlich sichern: `config.yaml`, `blacklist.txt` und `vorlagen/`.

---

## 10. Probleme und Lösungen

| Problem | Lösung |
|---|---|
| „Python wurde nicht gefunden“ | Python neu installieren, unter Windows dabei „Add python.exe to PATH“ ankreuzen. |
| Browser öffnet sich nicht | <http://localhost:8501> von Hand im Browser öffnen. |
| „Die Arbeitsagentur-API war nicht erreichbar“ | Internetverbindung prüfen, später erneut versuchen. Details im Ordner `logs`. |
| Dashboard zeigt „Formatfehler in config.yaml“ | Zuletzt geänderte Zeile prüfen: Einrückung mit Leerzeichen, Doppelpunkt nach dem Namen. |
| Mac: täglicher Abruf läuft nicht | Ordner in den Benutzerordner verschieben (nicht Dokumente/Schreibtisch) und `4_Taeglich_einrichten_Mac.command` erneut ausführen. |
| Abruf meldet „max_seiten erreicht“ | Ein Suchbegriff liefert sehr viele Treffer. In `config.yaml` → `arbeitsagentur` → `max_seiten` erhöhen. |
