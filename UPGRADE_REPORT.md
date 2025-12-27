# UPGRADE_REPORT – Plex Smart Refresher GUI (Stand: 2025-12-27)

Dieses Dokument fasst zusammen, was sich im Projekt seit dem ursprünglichen GitHub-Stand geändert hat
und welche Dateien neu dazugekommen sind.

## Ziele des Umbaus

- Background Scan Jobs laufen stabil weiter (auch wenn Safari/iPhone die Session trennt).
- Cancel funktioniert zuverlässig über DB-Flag `cancel_requested` (auch während Phase 3 und Wait/Reload).
- UI/Session-State stabil; Auth künftig cookie-basiert statt Nginx Basic Auth.

## Neu hinzugekommene Dateien (im Repo)

### `jobs.py`
Job- und Status-Infrastruktur (SQLite `refresh_state.db`, Tabelle `scan_runs`):

- `create_scan_job()` erstellt einen Job und reserviert Log-Pfad.
- `request_cancel(job_id)` setzt `cancel_requested=1`.
- `is_cancel_requested(job_id)` prüft Cancel-Flag.
- `set_job_status(job_id, status, stats, error, ...)` schreibt Status + setzt `finished_at` automatisch bei non-running Status.
- `get_running_job() / get_job() / list_jobs()` für UI/Statusanzeige.
- `append_job_log()` + `tail_job_log()` (Logfile pro Job).
- Orphan-Recovery: `mark_orphaned_jobs_interrupted()` markiert alte `running` Jobs als `interrupted`.
- Cleanup/Retention:
  - `cleanup_old_logs()` (Default 30 Tage, Env `PSR_LOG_RETENTION_DAYS`)
  - `cleanup_old_scan_runs()` (Default 90 Tage / 500 Jobs, Env `PSR_SCAN_RUN_RETENTION_DAYS`, `PSR_SCAN_RUN_RETENTION_COUNT`)

### `auth.py`
Single-User Cookie-Login mit `streamlit-authenticator`:

- Nutzt `GUI_PASSWORD` (aus `.env` / Environment) als Initial-Passwort.
- Erstellt bei Bedarf `auth.yaml` (gehashtes Passwort + Cookie-Key) und setzt Dateirechte (600).
- Wichtige Umgebungsvariablen:
  - `PSR_AUTH_CONFIG` (Pfad zu `auth.yaml`, Default im Projektverzeichnis)
  - `PSR_AUTH_USERNAME` (Default: `admin`)
  - `PSR_COOKIE_NAME` (Default: `psr_auth`)
  - `PSR_COOKIE_EXPIRY_DAYS` (Default: 30)
  - `PSR_COOKIE_KEY` (optional; sonst wird bei Erststart generiert)

### `auth.yaml.example`
Vorlage ohne Secrets. Die echte `auth.yaml` wird lokal erstellt und ist per `.gitignore` ausgeschlossen.

## Geänderte Dateien (im Repo)

### `app.py`
Wesentliche Änderungen:

- Robuste Session-State Defaults (`_ensure_session_defaults()`).
- Background Scan Job Runner (`_run_scan_job(job_id, settings)`):
  - läuft im Thread
  - Log schreibt in `logs/scan_<jobid>.log`
  - Cancel via `_cancel_check()` (DB-basiert)
  - Finalisierung via `jobs.set_job_status(...)`
- Startup Maintenance:
  - `_startup_orphan_recovery()` markiert stale `running` Jobs
  - `_startup_cleanup_once()` führt Cleanup (Logs/scan_runs) 1x pro Prozess aus
- Login:
  - `require_auth()` über `streamlit-authenticator` (Cookie)
- UI:
  - Cancel-Button nicht mehr full-width (kein `width="stretch"`)

### `logic.py`
Wesentliche Änderungen:

- Cancel-Handling zentral: `_is_cancel_requested(cancel_flag)` unterstützt:
  - Callable (DB-check) **oder**
  - legacy Dict (`{"cancelled": bool}`)
- Plex-Connection unter Lock (`_plex_lock`) für mehr Thread-Safety.
- `smart_refresh_item(...)`:
  - `item.refresh` / `item.reload` via `asyncio.to_thread(...)`
  - Cancel-Check auch während Retry/Wait
  - Retry-Loop mit `await asyncio.sleep(wait_interval)`
- Scan-Engine:
  - `stats` erweitert um `would_fix`
  - Retry-Pool: failed Items aus DB zusätzlich prüfen (Limit `failed_retry_pool_limit`)
  - Backoff-Logs für recently failed Items (setting `failed_backoff_hours`)

### `requirements.txt`
Neu:
- `streamlit-authenticator`
- `PyYAML`

### `.gitignore`
Erweitert um lokale Secrets & Runtime-Artefakte:
- `auth.yaml`, `logs/`
- `refresh_state.db-*`, `refresh_state.db.bak*`
- `*.bak_*`, `app.py.bak*`, `jobs.py.bak*`

## Dateien, die bewusst NICHT im Repo sind (lokal)

- `auth.yaml` (enthält Cookie-Key + Passwort-Hash) → **Secret**
- `logs/scan_*.log` → Laufzeitlogs
- `refresh_state.db*` (inkl. `-wal`/`-shm`) → Laufzeit-DB
- `*.bak_*` → lokale Sicherungen

## Hinweise für Betrieb / Deployment

- Service läuft über `plexgui.service` (systemd).
- Streamlit bindet lokal auf `127.0.0.1:8501` (Proxy via Nginx empfohlen).
- Wenn UI „hängt“ (Scan läuft angeblich):
  - DB prüfen:
    - `SELECT * FROM scan_runs WHERE status='running' ORDER BY started_at DESC;`
  - Orphan-Recovery/Restart hilft in der Regel.

## Backup-Info (GitHub)
Falls GitHub-`main` irgendwann per Force-Push ersetzt wurde, wurde vorher eine Backup-Branch angelegt:
- `backup/origin-main-before-force-20251227`

