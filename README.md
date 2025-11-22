SYSTEMDOKUMENTATION: PLEX SMART REFRESHER (GUI EDITION)
=======================================================
Stand: 21.11.2025
System: Debian 12
Installationspfad: /opt/plex_gui

1. ÜBERSICHT & FUNKTIONEN
-------------------------
Das Tool dient zur Verwaltung und Aktualisierung von Plex-Bibliotheken über eine Web-Oberfläche.
- Web-Dashboard: Steuerung über Browser (Passwortgeschützt, Dark Mode).
- Smart Refresh: Scannt Bibliotheken und erzwingt Metadaten-Updates bei Fehlern.
- Zeitplaner: Automatische Ausführung (Standard: 04:00 Uhr).
- Live-Logs: Echtzeit-Anzeige des Scan-Fortschritts.
- Historie: Speicherung der Ergebnisse in einer lokalen Datenbank.

2. WICHTIGE DATEIPFADE
----------------------
Hauptordner:           /opt/plex_gui
Virtuelle Umgebung:    /opt/plex_gui/venv
Datenbank:             /opt/plex_gui/refresh_state.db
Konfiguration (.env):  /opt/plex_gui/.env
Einstellungen (JSON):  /opt/plex_gui/settings.json
Autostart-Dienst:      /etc/systemd/system/plexgui.service

3. INSTALLATION (SCHRITT FÜR SCHRITT)
-------------------------------------

A) Vorbereitung
   Erstellen des Ordners im Terminal:
   mkdir -p /opt/plex_gui
   cd /opt/plex_gui

B) Dateien
   Die Dateien (app.py, logic.py, requirements.txt, etc.) müssen in diesen Ordner geladen werden.

C) Virtuelle Umgebung (Python) einrichten
   Befehle im Terminal ausführen:
   python3 -m venv venv
   /opt/plex_gui/venv/bin/pip install -r requirements.txt

D) Konfiguration (.env Datei)
   Erstelle die Datei "/opt/plex_gui/.env" mit folgendem Inhalt:
   PLEX_URL=http://localhost:32400
   PLEX_TOKEN=HIER_DEIN_PLEX_TOKEN
   PLEX_TIMEOUT=60
   GUI_PASSWORD=HIER_DEIN_WEB_PASSWORT

E) Autostart aktivieren
   Kopiere "plexgui.service" nach "/etc/systemd/system/".
   Aktiviere den Dienst:
   systemctl daemon-reload
   systemctl enable plexgui
   systemctl start plexgui

4. STEUERUNG & BEFEHLE
----------------------

A) Web-Oberfläche aufrufen
   Im Browser eingeben: http://DEINE-SERVER-IP:8501

B) Terminal-Befehle (Dienst steuern)
   Status prüfen:    systemctl status plexgui
   Neustart:         systemctl restart plexgui
   Stoppen:          systemctl stop plexgui
   Logs ansehen:     journalctl -u plexgui -f

5. FEHLERBEHEBUNG
-----------------
Sollte die Webseite nicht erreichbar sein:
1. Prüfe, ob der Dienst läuft ("systemctl status plexgui").
2. Prüfe die Logs auf Fehlermeldungen ("journalctl -u plexgui -f").
3. Stelle sicher, dass in der ".env" Datei das richtige Plex-Token steht.

