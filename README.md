# 📘 System-Dokumentation: Plex Smart Refresher (GUI Edition)

**Version:** 1.0
**Status:** Stable

Ein ressourcenschonendes Python-Tool mit Web-Oberfläche, um fehlende Metadaten in Plex (fehlende Poster, keine Match-ID, unvollständige Infos) zu erkennen und intelligent zu reparieren.

---

## ✨ Features

* **Smart-Wait Logik:** Das Tool "feuert" nicht nur Befehle ab, sondern wartet geduldig (Polling bis zu 60s) und prüft, ob Plex die Metadaten wirklich geladen hat.
* **Ressourcensparend:** Läuft nativ ("Bare Metal") auf Linux. Ersetzt schwere Docker-Container und verbraucht nur ca. 100 MB RAM.
* **Web-Dashboard:** Moderne, dunkle Oberfläche (Dark Mode) mit goldenen Akzenten zur Steuerung.
* **Zeitplaner:** Integrierter Scheduler für automatische Scans im Hintergrund (z.B. nachts).
* **Intelligente Filter:** Scannt auf Wunsch nur Inhalte, die in den letzten X Tagen hinzugefügt wurden.
* **Detaillierte Berichte:** Zeigt genau an, welcher Film gefixt wurde und speichert eine Historie.

---

## 📂 Projektstruktur

Das Tool wird standardmäßig unter `/opt/plex_gui` installiert.

* `app.py`: Die grafische Oberfläche (Streamlit Dashboard).
* `logic.py`: Die Backend-Logik (Plex-Verbindung, Smart-Wait, Datenbank).
* `plexgui.service`: Konfiguration für den System-Autostart.
* `requirements.txt`: Liste der Python-Abhängigkeiten.
* `.env`: **WICHTIG** - Beinhaltet Passwörter und Tokens (wird lokal erstellt).
* `settings.json`: Speichert automatisch die Einstellungen aus der GUI.
* `refresh_state.db`: Lokale SQLite-Datenbank für die Historie.

---

## 🛠️ Installationsanleitung

Diese Schritte gelten für ein frisches Debian/Ubuntu System (VPS).

### 1. Voraussetzungen installieren
Führen Sie folgende Befehle aus, um Python und Pip zu installieren:

sudo apt update
sudo apt install -y python3-venv python3-pip

### 2. Verzeichnis erstellen & Dateien anlegen
Wir erstellen den Zielordner und legen die Skripte manuell an.

A. Ordner erstellen:
mkdir -p /opt/plex_gui
cd /opt/plex_gui

B. Dateien erstellen:
Kopieren Sie den jeweiligen Quellcode (aus Ihrem Backup oder GitHub) und fügen Sie ihn in die Dateien ein.

Datei 1: Die Benutzeroberfläche
nano app.py
# [Hier den Inhalt von app.py einfügen]
# Speichern: STRG+O -> Enter -> STRG+X

Datei 2: Die Logik
nano logic.py
# [Hier den Inhalt von logic.py einfügen]
# Speichern: STRG+O -> Enter -> STRG+X

Datei 3: Die Abhängigkeiten
nano requirements.txt
# [Inhalt einfügen:]
# streamlit
# plexapi
# python-dotenv
# requests
# pandas
# Speichern: STRG+O -> Enter -> STRG+X

Datei 4: Der Autostart-Dienst
nano plexgui.service
# [Hier den Inhalt der .service Datei einfügen]
# Speichern: STRG+O -> Enter -> STRG+X

### 3. Virtuelle Umgebung (Venv) einrichten
Wir installieren die benötigten Pakete isoliert:

python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

### 4. Konfiguration (.env)
Erstelle eine Datei namens .env. Diese Datei enthält sensible Daten und darf nicht öffentlich geteilt werden.

nano .env

Inhalt:
PLEX_URL=http://localhost:32400
PLEX_TOKEN=DEIN_ECHTER_PLEX_TOKEN
PLEX_TIMEOUT=60
GUI_PASSWORD=DEIN_GEWUENSCHTES_PASSWORT
(Speichern mit STRG+O, Beenden mit STRG+X)

### 5. Autostart einrichten (Systemd)
Damit das Tool immer läuft (24/7) und automatisch startet:

Kopiere die Service-Datei an den System-Ort:
sudo cp plexgui.service /etc/systemd/system/

Aktiviere den Dienst:
sudo systemctl daemon-reload
sudo systemctl enable plexgui
sudo systemctl start plexgui
(Hinweis: Der Service-Befehl erzwingt den Dark Mode und die Akzentfarbe).

---

## 🖥️ Bedienung

Öffne deinen Browser: http://DEINE-SERVER-IP:8501
Logge dich mit dem Passwort aus der .env Datei ein.

### Dashboard Funktionen
* **Bibliotheken:** Wähle aus, welche Mediatheken gescannt werden.
* **Zeit-Filter:** Begrenze den Scan auf neue Inhalte (spart Ressourcen).
* **Simulation (Dry Run):** Teste den Scan, ohne Änderungen vorzunehmen.
* **Zeitplaner:** Aktiviere automatische Scans zu einer bestimmten Uhrzeit.
* **Live Protokoll:** Verfolge den Scan in Echtzeit.
* **Bericht:** Siehe dir die Historie aller gefixten Items an (Tabelle unten).

---

## ❓ Wartung & Befehle

Status prüfen (RAM Verbrauch & Laufzeit):
systemctl status plexgui

Logs live ansehen (Fehlersuche):
journalctl -u plexgui -f

Tool neu starten (nach Updates oder Config-Änderung):
systemctl restart plexgui
