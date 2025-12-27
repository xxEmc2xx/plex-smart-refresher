# Plex Smart Refresher (Streamlit GUI)

Automatische Reparatur fehlender Plex-Metadaten (Poster/Match-IDs/Beschreibungen) über eine Streamlit-Web-GUI – mit Background-Jobs, persistenten Job-Logs, DB-basiertem Cancel und cookie-basiertem Login (Safari-friendly).

Wichtig: Secrets (PLEX_TOKEN, GUI_PASSWORD, Cookie-Key) gehören nicht ins Repo.
Lokale Secrets/Runtime-Artefakte werden via .gitignore ausgeschlossen (auth.yaml, logs/, refresh_state.db*, *.bak_*).

## Features (aktueller Stand)

- Background Scan Jobs (Thread) – unabhängig von Streamlit-Session/Browser-Reconnect
- Persistente Job-Logs: logs/scan_<job_id>.log + UI Log-Tail
- DB-basierter Cancel: cancel_requested=1 in SQLite, Worker bricht auch in Phase 3/Wait ab
- Orphan-Recovery: stale running Jobs werden beim Neustart als interrupted markiert
- Cleanup/Retention: automatische Bereinigung alter Logs und Scan-Runs (Env-basiert)
- Cookie-Login via streamlit-authenticator (Single-User)

## Projektstruktur

- app.py – UI, Background-Runner, Job-Ansicht, Auth, Startup (Orphan/Cleanup)
- logic.py – Scan-Engine (Analyse/Fix), Smart Refresh Wait, Cancel-Checks
- jobs.py – scan_runs Job-DB, Cancel, Log-Tailing, Orphan-Recovery, Cleanup
- auth.py – erzeugt/liest lokale auth.yaml (Single-User Cookie-Config)
- auth.yaml.example – Beispiel ohne Secrets

## Installation / Betrieb

Hinweis zu systemd: In der Unit steht standardmäßig `User=plexuser`. Ersetze das durch deinen Linux-User (z.B. `debian`, `ubuntu`, `pi`, …) oder lege `plexuser` an.

Reverse Proxy (Nginx) empfohlen: Streamlit sollte nur auf 127.0.0.1:8501 lauschen, Nginx published nach außen (HTTPS). Wichtig für Streamlit: WebSocket-Header (Upgrade/Connection) und ausreichend proxy_read_timeout.

Alle Befehle (Setup, Konfig, Service, Nginx, Update, Troubleshooting) sind absichtlich in genau EINEM Block, damit GitHub nichts unterteilt:

<pre>
# 0) System vorbereiten
sudo apt update
sudo apt install -y python3-venv python3-pip git nginx

# 1) Projekt installieren
sudo mkdir -p /opt/plex_gui
sudo chown -R "$USER":"$USER" /opt/plex_gui
cd /opt/plex_gui

git clone https://github.com/xxEmc2xx/plex-smart-refresher.git .

python3 -m venv venv
./venv/bin/pip install -r requirements.txt

# 2) Konfiguration (.env)
cat > /opt/plex_gui/.env <<'ENV'
# Plex
PLEX_URL=http://127.0.0.1:32400
PLEX_TOKEN=DEIN_PLEX_TOKEN
PLEX_TIMEOUT=60

# GUI Auth (Single-User)
GUI_PASSWORD=DEIN_GUTES_PASSWORT

# Optional: Cookie/Auth Settings
# PSR_AUTH_USERNAME=admin
# PSR_COOKIE_NAME=psr_auth
# PSR_COOKIE_EXPIRY_DAYS=30
# PSR_COOKIE_KEY=optional_fester_cookie_key

# Orphan/Retention
# PSR_ORPHAN_GRACE_MINUTES=10
# PSR_LOG_RETENTION_DAYS=30
# PSR_SCAN_RUN_RETENTION_DAYS=90
# PSR_SCAN_RUN_RETENTION_COUNT=500
ENV

# Sicherheit: Rechte für Secrets setzen (empfohlen)
chmod 600 /opt/plex_gui/.env || true
# auth.yaml wird beim ersten Start erzeugt; danach ebenfalls schützen:
# chmod 600 /opt/plex_gui/auth.yaml

# 3) systemd Service (Beispiel)
# Hinweis: Passe User/Group an und stelle sicher, dass Streamlit nur lokal bindet (127.0.0.1)
sudo tee /etc/systemd/system/plexgui.service >/dev/null <<'SERVICE'
[Unit]
Description=Plex Smart Refresher GUI
After=network.target

[Service]
Type=simple
User=plexuser
WorkingDirectory=/opt/plex_gui
EnvironmentFile=/opt/plex_gui/.env
ExecStart=/opt/plex_gui/venv/bin/streamlit run app.py --server.port 8501 --server.address 127.0.0.1 --theme.base=dark
Restart=always
RestartSec=3

[Install]
WantedBy=multi-user.target
SERVICE

sudo systemctl daemon-reload
sudo systemctl enable plexgui.service
sudo systemctl restart plexgui.service

# 4) Status prüfen
systemctl status plexgui.service --no-pager -l | sed -n '1,35p'

# 5) Öffnen (lokal / via Reverse Proxy)
# Lokal (Server): http://127.0.0.1:8501

# 6) Nginx Reverse Proxy (Beispiel)
# Ersetze DOMAIN.TLD und (optional) Zertifikate/SSL-Konfig.
# Wichtig: WebSocket Header + ausreichend Timeout.
sudo tee /etc/nginx/sites-available/plexgui >/dev/null <<'NGINX'
server {
    listen 80;
    server_name DOMAIN.TLD;

    # Optional: Wenn du TLS terminierst, leite HTTP auf HTTPS um
    # return 301 https://$host$request_uri;

    location / {
        proxy_pass http://127.0.0.1:8501;

        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        # WebSocket (Streamlit)
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";

        # Timeouts für längere Requests/Streams
        proxy_read_timeout 3600;
        proxy_send_timeout 3600;
    }
}
NGINX

sudo ln -sf /etc/nginx/sites-available/plexgui /etc/nginx/sites-enabled/plexgui
sudo nginx -t
sudo systemctl reload nginx

# 7) Update / Upgrade (vom GitHub-Repo)
cd /opt/plex_gui
git pull --ff-only origin main
./venv/bin/pip install -r requirements.txt
sudo systemctl restart plexgui.service

# 8) Troubleshooting

# a) Job-Status prüfen (DB)
sqlite3 /opt/plex_gui/refresh_state.db "SELECT job_id,status,started_at,finished_at,cancel_requested,error FROM scan_runs ORDER BY started_at DESC LIMIT 10;"

# b) Logs finden / ansehen
ls -1t /opt/plex_gui/logs/scan_*.log | head
tail -n 200 /opt/plex_gui/logs/scan_<jobid>.log

# c) Service Logs
sudo journalctl -u plexgui.service -n 200 --no-pager

# d) “UI sagt Scan läuft, aber nichts passiert”
# - Prüfe scan_runs (siehe a)
# - Prüfe Logfile (siehe b)
# - Neustart hilft bei orphaned Jobs (die werden beim Start als interrupted markiert)
</pre>
