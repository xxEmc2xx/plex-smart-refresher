# Plex Smart Refresher

Ressourcenschonendes Python-Tool mit Web-GUI zur automatischen Reparatur fehlender Plex-Metadaten (Poster, Match-IDs, Beschreibungen).

## Features

- **Smart-Wait Logik**: Wartet bis zu 60s und prüft, ob Plex Metadaten wirklich geladen hat
- **Web-Dashboard**: Moderne Dark-Mode GUI mit Tab-Navigation (Dashboard, Statistik, Einstellungen)
- **Zeitplaner**: Automatische Scans im Hintergrund (z.B. nachts)
- **Telegram-Benachrichtigungen**: Optionale Push-Notifications nach jedem Scan
- **Erfolgsrate-Anzeige**: Farbcodiert (grün >80%, gelb >50%, rot <50%)
- **Suchfunktion**: Historie nach Titeln durchsuchen, Status-Filter
- **Login-Sicherheit**: Max. 5 Versuche, automatische Sperrung
- **Intelligente Filter**: Nur neue Inhalte der letzten X Tage scannen
- **Performance-Optimiert**: Caching, Connection Pooling, Lazy Loading
- **Ressourcensparend**: ~100 MB RAM, läuft nativ ohne Docker

## Installation

### Voraussetzungen
- Debian 12 (oder kompatible Linux-Distribution)
- Python 3.11+
- Plex Media Server mit gültigem Token

### Setup
```bash
# 1. Python und Pip installieren
sudo apt update && sudo apt install -y python3-venv python3-pip

# 2. Verzeichnis erstellen
sudo mkdir -p /opt/plex_gui
cd /opt/plex_gui

# 3. Code herunterladen (Option A: Git)
git clone https://github.com/DEIN-REPO/plex_gui.git .

# Oder Option B: Manuell Dateien erstellen
# app.py, logic.py, notifications.py, requirements.txt, plexgui.service

# 4. Virtuelle Umgebung einrichten
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## Konfiguration

Erstelle `.env` Datei in `/opt/plex_gui`:

```ini
# Plex Server
PLEX_URL=http://localhost:32400
PLEX_TOKEN=DEIN_PLEX_TOKEN
PLEX_TIMEOUT=60

# GUI Passwort
GUI_PASSWORD=DEIN_PASSWORT

# Telegram (optional)
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID

# Sicherheit
MAX_LOGIN_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15
```

**Plex Token finden**: `Settings > Network > Show Advanced > Plex.tv Token`

## Empfehlung: Nginx Reverse Proxy mit Basic Auth

Für eine sichere Bereitstellung hinter einem Reverse Proxy empfiehlt sich Nginx mit HTTP-Basic-Auth.

- **Streamlit lokal binden**: Starte die App auf `127.0.0.1:8501`, damit sie nur lokal erreichbar ist.
- **Port 8501 nicht freigeben**: Öffne Port `8501` nicht in der Firewall; Anfragen sollen ausschließlich über Nginx laufen.
- **Kein doppelter Login**: Setze `GUI_PASSWORD` in der `.env` auf einen leeren Wert, wenn du Nginx Basic Auth nutzt, um zwei Logins zu vermeiden.

### Beispiel Nginx-Serverblock

```nginx
server {
    listen 443 ssl;
    server_name plex.example.com;

    # TLS-Konfiguration (Zertifikate anpassen)
    ssl_certificate /etc/letsencrypt/live/plex.example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/plex.example.com/privkey.pem;

    # Basic Auth
    auth_basic "Plex GUI";
    auth_basic_user_file /etc/nginx/.htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8501;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSockets für Streamlit
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts für lange Requests
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

### Autostart aktivieren
```bash
sudo cp plexgui.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable plexgui
sudo systemctl start plexgui
```

## Bedienung

Browser öffnen: `http://DEINE-SERVER-IP:8501`

- **Dashboard**: Bibliotheken auswählen, Zeit-Filter setzen, Scan starten
- **Statistik**: Erfolgsrate, Historie mit Suchfunktion
- **Einstellungen**: Zeitplaner, Dry Run, Telegram

## Update-Anleitung

### Variante 1: Git Pull (wenn ursprünglich gecloned)
```bash
cd /opt/plex_gui
git pull origin main
sudo systemctl restart plexgui
```

### Variante 2: Git Init (nachträglich Git nutzen)
```bash
cd /opt/plex_gui
git init
git remote add origin https://github.com/DEIN-REPO/plex_gui.git
git fetch
git reset --hard origin/main
sudo systemctl restart plexgui
```

### Variante 3: Wget (einzelne Dateien)
```bash
cd /opt/plex_gui
wget -O app.py https://raw.githubusercontent.com/DEIN-REPO/plex_gui/main/app.py
wget -O logic.py https://raw.githubusercontent.com/DEIN-REPO/plex_gui/main/logic.py
wget -O notifications.py https://raw.githubusercontent.com/DEIN-REPO/plex_gui/main/notifications.py
source venv/bin/activate && pip install -r requirements.txt
sudo systemctl restart plexgui
```

## Wartungsbefehle

```bash
# Status prüfen (RAM, Laufzeit)
systemctl status plexgui

# Logs live ansehen
journalctl -u plexgui -f

# Service neu starten
sudo systemctl restart plexgui

# Service stoppen
sudo systemctl stop plexgui
```

## Projektstruktur

| Datei | Beschreibung |
|-------|-------------|
| `app.py` | Web-Dashboard (Streamlit) |
| `logic.py` | Backend-Logik (Plex-API, Datenbank) |
| `notifications.py` | Telegram-Integration |
| `plexgui.service` | Systemd-Service für Autostart |
| `requirements.txt` | Python-Abhängigkeiten |
| `.env` | Konfiguration (nicht committen!) |
| `settings.json` | GUI-Einstellungen (automatisch) |
| `refresh_state.db` | SQLite-Datenbank (Historie) |
