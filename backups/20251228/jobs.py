import json
import os
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "refresh_state.db"
LOG_DIR = BASE_DIR / "logs"


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    # etwas bessere Concurrency (wir bleiben trotzdem single process)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=5000;")
    return conn


def mark_orphaned_jobs_interrupted(grace_minutes: int | None = None) -> int:
    """
    Markiert 'running' Jobs als 'interrupted', wenn sie als orphaned gelten.
    Orphaned = Job ist running, aber der Streamlit-Prozess wurde neu gestartet.

    Grace-Window (sanfter):
      - nur Jobs, die älter als grace_minutes sind, werden umgestellt

    Default grace_minutes:
      Env PSR_ORPHAN_GRACE_MINUTES oder 10
    """
    if grace_minutes is None:
        try:
            grace_minutes = int(os.getenv("PSR_ORPHAN_GRACE_MINUTES", "10"))
        except Exception:
            grace_minutes = 10
    if grace_minutes < 0:
        grace_minutes = 0

    now_utc = dt.datetime.now(dt.timezone.utc)
    cutoff = now_utc - dt.timedelta(minutes=grace_minutes)

    updated = 0
    try:
        with get_db_connection() as conn:
            cur = conn.cursor()
            cur.execute(
                """
                UPDATE scan_runs
                SET status='interrupted',
                    finished_at=?,
                    error=COALESCE(error, 'Process restarted (orphan recovery)')
                WHERE status='running'
                  AND started_at < ?
                """,
                (now_utc.isoformat(timespec="seconds"), cutoff.isoformat(timespec="seconds")),
            )
            updated = cur.rowcount if cur.rowcount is not None else 0
            conn.commit()
    except Exception:
        return 0

    return updated

def create_scan_job(source: str = "manual") -> dict[str, Any]:
    """
    Legt einen neuen Job an und reserviert den Log-Pfad.
    """
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    job_id = uuid.uuid4().hex
    started_at = _utcnow_iso()
    log_path = str(LOG_DIR / f"scan_{job_id}.log")

    with get_db_connection() as conn:
        conn.execute(
            """
            INSERT INTO scan_runs(job_id, status, started_at, log_path, stats_json, error, cancel_requested)
            VALUES (?, 'running', ?, ?, NULL, NULL, 0)
            """,
            (job_id, started_at, log_path),
        )
        conn.commit()

    append_job_log_path(log_path, f"[JOB {job_id}] started (source={source})")
    return {"job_id": job_id, "status": "running", "started_at": started_at, "log_path": log_path}


def request_cancel(job_id: str) -> None:
    with get_db_connection() as conn:
        conn.execute("UPDATE scan_runs SET cancel_requested=1 WHERE job_id=? AND status='running'", (job_id,))
        conn.commit()


def is_cancel_requested(job_id: str) -> bool:
    with get_db_connection() as conn:
        row = conn.execute("SELECT cancel_requested FROM scan_runs WHERE job_id=?", (job_id,)).fetchone()
    return bool(row["cancel_requested"]) if row else False


def set_job_status(
    job_id: str,
    status: str,
    *,
    finished: bool = False,
    stats: Optional[dict[str, Any]] = None,
    error: Optional[str] = None,
) -> None:
    auto_finished = finished or (status != "running")
    finished_at = _utcnow_iso() if auto_finished else None
    stats_json = json.dumps(stats, ensure_ascii=False) if stats is not None else None

    with get_db_connection() as conn:
        conn.execute(
            """
            UPDATE scan_runs
               SET status=?,
                   finished_at=COALESCE(?, finished_at),
                   stats_json=COALESCE(?, stats_json),
                   error=COALESCE(?, error)
             WHERE job_id=?
            """,
            (status, finished_at, stats_json, error, job_id),
        )
        conn.commit()


def get_running_job() -> Optional[dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT * FROM scan_runs WHERE status='running' ORDER BY started_at DESC LIMIT 1"
        ).fetchone()
    return dict(row) if row else None


def get_job(job_id: str) -> Optional[dict[str, Any]]:
    with get_db_connection() as conn:
        row = conn.execute("SELECT * FROM scan_runs WHERE job_id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def list_jobs(limit: int = 20) -> list[dict[str, Any]]:
    with get_db_connection() as conn:
        rows = conn.execute(
            "SELECT * FROM scan_runs ORDER BY started_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def append_job_log(job_id: str, message: str) -> None:
    job = get_job(job_id)
    if not job:
        return
    path = job.get("log_path")
    if not path:
        return
    append_job_log_path(path, message)


def append_job_log_path(log_path: str, message: str) -> None:
    LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = f"{ts} {message}\n"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line)


def tail_log_file(log_path: str, n: int = 200) -> str:
    """
    Gibt die letzten n Zeilen zurück (einfach/robust; für unsere Log-Größen ausreichend).
    """
    try:
        with open(log_path, "rb") as f:
            data = f.read()
        lines = data.splitlines()[-n:]
        return b"\n".join(lines).decode("utf-8", errors="replace")
    except FileNotFoundError:
        return ""
    except Exception as e:
        return f"[tail error] {e}"


def tail_job_log(job_id: str, n: int = 200) -> str:
    job = get_job(job_id)
    if not job or not job.get("log_path"):
        return ""
    return tail_log_file(job["log_path"], n=n)

# --- CLEANUP / MAINTENANCE ---
import os
import datetime as dt
from pathlib import Path

def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except Exception:
        return default

def cleanup_old_logs(log_dir: str | None = None, keep_days: int | None = None) -> int:
    """
    Löscht Job-Logfiles älter als keep_days.
    Default: 30 Tage oder Env PSR_LOG_RETENTION_DAYS
    """
    if keep_days is None:
        keep_days = _env_int("PSR_LOG_RETENTION_DAYS", 30)

    if log_dir is None:
        # LOG_DIR ist weiter oben in jobs.py definiert; fallback:
        log_dir = str(Path(__file__).resolve().parent / "logs")

    d = Path(log_dir)
    if not d.exists():
        return 0

    cutoff = dt.datetime.now().timestamp() - (keep_days * 86400)
    removed = 0

    for f in d.glob("scan_*.log"):
        try:
            if f.stat().st_mtime < cutoff:
                f.unlink()
                removed += 1
        except Exception:
            pass

    return removed

def cleanup_old_scan_runs(keep_last_n: int | None = None, keep_days: int | None = None) -> int:
    """
    Räumt scan_runs auf:
      - behält mindestens die letzten keep_last_n Jobs
      - löscht Jobs, die älter als keep_days sind UND nicht in den letzten keep_last_n sind

    Defaults:
      keep_last_n = 500 oder Env PSR_SCAN_RUN_RETENTION_COUNT
      keep_days   = 90  oder Env PSR_SCAN_RUN_RETENTION_DAYS
    """
    if keep_last_n is None:
        keep_last_n = _env_int("PSR_SCAN_RUN_RETENTION_COUNT", 500)
    if keep_days is None:
        keep_days = _env_int("PSR_SCAN_RUN_RETENTION_DAYS", 90)

    cutoff_dt = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=keep_days)
    cutoff_iso = cutoff_dt.isoformat(timespec="seconds")

    removed = 0
    try:
        with get_db_connection() as conn:
            row = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name='scan_runs'"
            ).fetchone()
            if not row:
                return 0

            cur = conn.cursor()
            cur.execute(
                """
                DELETE FROM scan_runs
                WHERE job_id NOT IN (
                    SELECT job_id FROM scan_runs ORDER BY started_at DESC LIMIT ?
                )
                AND started_at < ?
                """,
                (keep_last_n, cutoff_iso),
            )
            removed = cur.rowcount if cur.rowcount is not None else 0
            conn.commit()
    except Exception:
        return 0

    return removed
