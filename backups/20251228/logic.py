import os
import asyncio
import datetime as dt
import sqlite3
import time
import json
import logging
import threading
from typing import List, Optional, Tuple, Dict, Any
from contextlib import contextmanager

from plexapi.server import PlexServer
from dotenv import load_dotenv

# Importiert notifications.py (Muss im selben Ordner liegen!)
import notifications

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PLEX_URL = os.getenv("PLEX_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
try:
    PLEX_TIMEOUT = int(os.getenv("PLEX_TIMEOUT", "60"))
except ValueError:
    PLEX_TIMEOUT = 60
    logger.warning("Invalid PLEX_TIMEOUT value, using default: 60")

DB_PATH = os.getenv("PSR_DB_PATH", os.path.join(BASE_DIR, "refresh_state.db"))
SETTINGS_FILE = os.getenv("PSR_SETTINGS_PATH", os.path.join(BASE_DIR, "settings.json"))
STATE_FILE = os.getenv("PSR_STATE_PATH", os.path.join(BASE_DIR, "run_state.json"))


# Connection Pooling - Singleton Pattern
_plex_connection = None
_plex_last_check = None
_run_state = None
_state_lock = threading.Lock()
scan_lock = threading.Lock()

def _is_cancel_requested(cancel_flag) -> bool:
    """cancel_flag kann dict (legacy) ODER callable (DB-check) sein."""
    try:
        if cancel_flag is None:
            return False
        if callable(cancel_flag):
            return bool(cancel_flag())
        return bool(cancel_flag.get("cancelled", False))
    except Exception:
        return False

_plex_lock = threading.Lock()


def get_plex_connection(force_reconnect=False):
    """
    Globale Plex-Verbindung als Singleton mit Auto-Reconnect.
    Prüft alle 5 Minuten ob die Verbindung noch lebt.
    """
    global _plex_connection, _plex_last_check
    
    now = time.time()
    check_interval = 300  # 5 Minuten
    
    # Reconnect wenn erzwungen oder Verbindung zu alt
    needs_reconnect = (
        force_reconnect or
        _plex_connection is None or
        _plex_last_check is None or
        (now - _plex_last_check) > check_interval
    )
    
    if needs_reconnect:
        with _plex_lock:
            # Verbindung testen oder neu aufbauen
            if _plex_connection is not None:
                try:
                    # Schneller Health-Check
                    _plex_connection.library.sections()
                    _plex_last_check = now
                    return _plex_connection
                except Exception:
                    logger.warning("Plex-Verbindung verloren, versuche Reconnect...")
                    _plex_connection = None
            
            # Neue Verbindung aufbauen
            try:
                _plex_connection = PlexServer(PLEX_URL, PLEX_TOKEN, timeout=PLEX_TIMEOUT)
                _plex_last_check = now
                logger.info("Plex-Verbindung hergestellt")
            except Exception as e:
                logger.error(f"Fehler beim Herstellen der Plex-Verbindung: {e}")
                _plex_connection = None
                raise
    
    return _plex_connection


def reset_plex_connection():
    """Erzwingt einen Reconnect beim nächsten Aufruf."""
    global _plex_connection, _plex_last_check
    _plex_connection = None
    _plex_last_check = None

# --- SETTINGS ---
def load_settings():
    default = {
        "libraries": [],
        "days": 30,
        "max_items": 50,
        "dry_run": False,
        "schedule_active": False,
        "schedule_time": "04:00"
    }
    if not os.path.exists(SETTINGS_FILE):
        return default
    try:
        with open(SETTINGS_FILE, "r") as f:
            data = json.load(f)
            return {**default, **data}
    except (json.JSONDecodeError, IOError) as e:
        logger.error(f"Error loading settings: {e}")
        return default

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        logger.error(f"Error saving settings: {e}")


def _read_state_file():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Error loading run state: {e}")
    return {"last_run_date": None}


def load_run_state():
    global _run_state
    with _state_lock:
        if _run_state is None:
            _run_state = _read_state_file()
        return dict(_run_state)


def update_last_run_date(date_str: str):
    global _run_state
    with _state_lock:
        if _run_state is None:
            _run_state = _read_state_file()
        _run_state["last_run_date"] = date_str
        try:
            with open(STATE_FILE, "w") as f:
                json.dump(_run_state, f, indent=4)
        except Exception as e:
            logger.error(f"Error saving run state: {e}")
    return date_str

# --- DATABASE ---

@contextmanager
def get_db_connection():
    """Context Manager für saubere DB-Verbindungen."""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA busy_timeout=30000;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db():
    with get_db_connection() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS media_state(
                rating_key TEXT PRIMARY KEY,
                library TEXT,
                title TEXT,
                updated_at TEXT,
                state TEXT,
                note TEXT,
                last_scan TEXT
            )
        """)
        conn.commit()


# Initialize database on module load
init_db()


def save_result(rating_key, library, title, state, note):
    """
    Speichert das Ergebnis in die DB. 
    Enthält jetzt Error-Handling und Encoding-Schutz für kaputte Titel.
    """
    try:
        # FIX: Titel bereinigen, falls er kaputte Zeichen enthält (z.B. ? statt Umlaute)
        safe_title = title
        if safe_title:
            try:
                # Versucht, Encoding-Fehler zu reparieren
                safe_title = str(title).encode('utf-8', 'replace').decode('utf-8')
            except Exception:
                safe_title = "Unknown Title (Encoding Error)"

        with get_db_connection() as conn:
            now = dt.datetime.now().isoformat(timespec="seconds")
            conn.execute("""
                INSERT INTO media_state(rating_key, library, title, updated_at, state, note, last_scan)
                VALUES(?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(rating_key) DO UPDATE SET
                    library=excluded.library,
                    title=excluded.title,
                    updated_at=excluded.updated_at,
                    state=excluded.state,
                    note=excluded.note,
                    last_scan=excluded.last_scan
            """, (rating_key, library, safe_title, now, state, note, now))
            conn.commit()
            
    except Exception as e:
        logger.error(f"DB-FEHLER beim Speichern von {rating_key}: {e}")
        # Wir crashen hier nicht mehr, damit der Loop weiterlaufen kann!


def get_last_report(limit=100, only_fixed=False):
    with get_db_connection() as conn:
        query = "SELECT * FROM media_state"
        if only_fixed:
            query += " WHERE state='fixed'"
        query += " ORDER BY last_scan DESC LIMIT ?"
        rows = conn.execute(query, (limit,)).fetchall()
        return rows


def get_total_statistics():
    """
    Berechnet Gesamtstatistiken aus der Datenbank.
    """
    with get_db_connection() as conn:
        c = conn.cursor()
        total_checked = c.execute("SELECT COUNT(*) FROM media_state").fetchone()[0]
        total_fixed = c.execute("SELECT COUNT(*) FROM media_state WHERE state='fixed'").fetchone()[0]
        total_failed = c.execute("SELECT COUNT(*) FROM media_state WHERE state='failed'").fetchone()[0]
    
    success_rate = (total_fixed / (total_fixed + total_failed) * 100) if (total_fixed + total_failed) > 0 else 0
    
    return {
        "total_checked": total_checked,
        "total_fixed": total_fixed,
        "total_failed": total_failed,
        "success_rate": success_rate
    }


def get_media_state_row(rating_key: str):
    """Liest den letzten gespeicherten Zustand für ein Item (media_state)."""
    try:
        with get_db_connection() as conn:
            return conn.execute(
                "SELECT state, last_scan, note FROM media_state WHERE rating_key=?",
                (rating_key,),
            ).fetchone()
    except Exception as e:
        logger.error(f"Fehler beim Lesen von media_state({rating_key}): {e}")
        return None


# --- PLEX LOGIC ---
def needs_refresh(item) -> bool:
    if not item.guids: return True
    if not item.thumb: return True
    if not item.summary: return True
    return False

async def smart_refresh_item(item, status_callback=None, settings=None, cancel_flag=None) -> Tuple[bool, str]:
    settings_from_args = settings if settings is not None else {}

    if settings is None:
        try:
            settings_from_args = load_settings() or {}
        except Exception as e:
            logger.error(f"Error loading fallback settings: {e}")
            settings_from_args = {}

    try:
        wait_total = int(settings_from_args.get("refresh_wait_total_seconds", 20))
    except (TypeError, ValueError):
        wait_total = 20

    try:
        wait_interval = int(settings_from_args.get("refresh_wait_interval_seconds", 4))
    except (TypeError, ValueError):
        wait_interval = 4

    wait_total = wait_total if wait_total > 0 else 20
    wait_interval = wait_interval if wait_interval > 0 else 4


    if _is_cancel_requested(cancel_flag):
        return False, "Abbruch angefordert"
    try:
        await asyncio.to_thread(item.refresh)
    except Exception as e:
        return False, f"API Fehler: {str(e)}"

    max_attempts = max(1, (wait_total + wait_interval - 1) // wait_interval)
    for attempt in range(1, max_attempts + 1):
        if _is_cancel_requested(cancel_flag):
            return False, "Abbruch angefordert"
        try:
            await asyncio.to_thread(item.reload)
            if not needs_refresh(item):
                return True, f"Gefixt nach {min(wait_total, attempt * wait_interval)}s"
        except Exception:
            pass
        if attempt < max_attempts:
            await asyncio.sleep(wait_interval)
    return False, f"Timeout ({wait_total}s)"


def get_library_names():
    try:
        plex = get_plex_connection()
        return [s.title for s in plex.library.sections() if s.type in ['movie', 'show']]
    except:
        return []

# --- SCAN ENGINE ---
async def run_scan_engine(progress_bar, log_callback, settings, cancel_flag=None):
    init_db()
    log_callback("Starte Scan...")
    
    try:
        plex = get_plex_connection()
    except Exception as e:
        log_callback(f"Verbindungsfehler: {e}")
        return None

    stats = {"checked": 0, "fixed": 0,
        "would_fix": 0, "failed": 0}
    days = settings.get("days", 30)
    max_items = settings.get("max_items", 50)
    target_libs = settings.get("libraries", [])
    dry_run = settings.get("dry_run", False)
    
    cutoff = dt.datetime.now() - dt.timedelta(days=days)
    
    # Phase 1: Alle Items sammeln
    log_callback("Phase 1: Sammle Items...")
    all_items = []
    items_to_refresh = []
    retry_keys = set()
    
    for lib_name in target_libs:
        if _is_cancel_requested(cancel_flag):
            break
        try:
            lib = plex.library.section(lib_name)
            recent = lib.all(sort="addedAt:desc", limit=max_items)
            all_items.append((lib_name, recent))
        except Exception as e:
            log_callback(f"Fehler beim Laden von {lib_name}: {e}")


    # Retry-Pool: zuletzt fehlgeschlagene Items aus der DB zusätzlich prüfen (auch wenn alt)
    try:
        retry_limit = int(settings.get("failed_retry_pool_limit", 50))
    except Exception:
        retry_limit = 50

    if retry_limit > 0:
        try:
            # all_items -> dict, damit wir einfach Items hinzufügen können
            items_by_lib = {ln: list(itms) for ln, itms in all_items}
            existing_keys = set()
            for ln, itms in items_by_lib.items():
                for it in itms:
                    rk = getattr(it, "ratingKey", None)
                    if rk is not None:
                        existing_keys.add(str(rk))

            with get_db_connection() as conn:
                rows = conn.execute(
                    """SELECT rating_key, library, last_scan
                        FROM media_state
                        WHERE state='failed'
                        ORDER BY last_scan DESC
                        LIMIT ?""",
                    (retry_limit,),
                ).fetchall()

            added = 0
            for r in rows:
                rk = r["rating_key"]
                lib = r["library"]
                if rk is None:
                    continue
                rk_s = str(rk)

                # nur innerhalb der aktuell ausgewählten Libraries
                if target_libs and lib and lib not in target_libs:
                    continue

                # nicht doppelt, wenn schon in den "neuesten" Items enthalten
                if rk_s in existing_keys:
                    continue

                try:
                    item = await asyncio.to_thread(plex.fetchItem, int(rk))
                except Exception:
                    continue

                # Library bestimmen (DB-Wert bevorzugen)
                lib_name = lib or getattr(item, "librarySectionTitle", None) or "Unbekannt"
                if target_libs and lib_name not in target_libs:
                    continue

                items_by_lib.setdefault(lib_name, []).append(item)
                retry_keys.add(rk_s)
                existing_keys.add(rk_s)
                added += 1

            if added > 0:
                log_callback(f"🔁 Retry-Pool: +{added} failed Items aus DB hinzugefügt (Limit={retry_limit})")

            # zurück zu all_items in stabiler Reihenfolge
            all_items = [(ln, items_by_lib.get(ln, [])) for ln in target_libs if ln in items_by_lib]
        except Exception as e:
            logger.error(f"Retry-Pool Fehler: {e}")

    # Phase 2: Items analysieren
    log_callback("Phase 2: Analysiere Items...")
    total_items = sum(len(items) for _, items in all_items)
    items_processed = 0
    
    for lib_name, items in all_items:
        if _is_cancel_requested(cancel_flag):
            log_callback("⚠️ Scan abgebrochen!")
            break
            
        log_callback(f"Analysiere: {lib_name}")
        
        for item in items:
            if _is_cancel_requested(cancel_flag):
                break
                
            items_processed += 1
            
            if progress_bar:
                try:
                    progress_bar.progress(
                        items_processed / total_items * 0.3,
                        text=f"Analysiere: {item.title} ({items_processed}/{total_items})"
                    )
                except:
                    pass
            
            added_at = getattr(item, "addedAt", None) or getattr(item, "updatedAt", None)
            if added_at is None:
                log_callback(f"⚠️ {item.title}: addedAt/updatedAt fehlt → übersprungen")
                continue

            
            rk_s = str(getattr(item, "ratingKey", ""))

            # Cutoff (days) gilt NICHT für Retry-Pool Items
            if rk_s not in retry_keys:
                if isinstance(added_at, dt.datetime) and added_at < cutoff:
                    continue
            
            stats["checked"] += 1
            
            if needs_refresh(item):
                if dry_run:
                    log_callback(f"-> [SIM] Würde fixen: {item.title}")
                    save_result(item.ratingKey, lib_name, item.title, "dry_run", "Simulation")
                    stats["would_fix"] += 1
                else:
                    # Backoff: failed Items nicht innerhalb von 24h erneut versuchen
                    backoff_hours = 24
                    try:
                        backoff_hours = int(settings.get("failed_backoff_hours", 24))
                    except Exception:
                        backoff_hours = 24

                    row = get_media_state_row(str(item.ratingKey))
                    if row and row["state"] == "failed" and row["last_scan"]:
                        try:
                            last = dt.datetime.fromisoformat(row["last_scan"])
                            now = dt.datetime.now(last.tzinfo) if getattr(last, "tzinfo", None) else dt.datetime.now()
                            age = now - last
                            backoff = dt.timedelta(hours=backoff_hours)
                            if age < backoff:
                                remaining = backoff - age
                                mins = int(remaining.total_seconds() // 60)
                                log_callback(f"⏳ Backoff: {item.title} (failed vor {int(age.total_seconds()//60)} min) → überspringe noch ~{mins} min")
                                continue
                        except Exception:
                            # Wenn Parsing fehlschlägt, kein Backoff anwenden
                            pass

                    items_to_refresh.append((item, lib_name))
    
    # Phase 3: Sequentielle Verarbeitung
    if items_to_refresh and not dry_run:
        total_to_fix = len(items_to_refresh)
        log_callback(f"Phase 3: Fixe {total_to_fix} Items...")
        
        for idx, (item, lib_name) in enumerate(items_to_refresh):
            if _is_cancel_requested(cancel_flag):
                log_callback("⚠️ Scan abgebrochen!")
                break
            
            # FIX: Einzelnes Try/Except pro Item, damit der ganze Prozess nicht stirbt
            try:
                log_callback(f"-> Fixe ({idx+1}/{total_to_fix}): {item.title}...")
                
                if progress_bar:
                    try:
                        progress_bar.progress(
                            0.3 + ((idx + 1) / total_to_fix * 0.7),
                            text=f"Fixe {idx+1}/{total_to_fix}: {item.title}"
                        )
                    except:
                        pass
                
                ok, msg = await smart_refresh_item(item, settings=settings, cancel_flag=cancel_flag)
                if ok:
                    log_callback(f"✅ {item.title}: {msg}")
                    save_result(item.ratingKey, lib_name, item.title, "fixed", msg)
                    stats["fixed"] += 1
                else:
                    log_callback(f"❌ {item.title}: {msg}")
                    # Auch Failed muss gespeichert werden, sonst Endlosschleife!
                    save_result(item.ratingKey, lib_name, item.title, "failed", msg)
                    stats["failed"] += 1
            
            except Exception as e:
                # Fataler Fehler bei einem Item (z.B. Encoding Crash)
                logger.error(f"CRASH bei Item {item.title if hasattr(item, 'title') else 'Unknown'}: {e}")
                log_callback(f"⚠️ Überspringe defektes Item: {e}")
                # Wir versuchen es als Failed zu speichern, damit es nicht wiederkommt
                try:
                    save_result(item.ratingKey, lib_name, "ERROR_ITEM", "failed", str(e))
                except:
                    pass
                stats["failed"] += 1

    if progress_bar:
        try:
            progress_bar.progress(1.0, text="Fertig!")
        except:
            pass
    
    log_callback("Fertig.")
    
    # Benachrichtigung senden (nur wenn notifications importiert wurde)
    try:
        if stats and stats.get("checked", 0) > 0:
            if 'notifications' in globals():
                notifications.send_scan_completion_notification(stats)
    except Exception as e:
        logger.error(f"Fehler beim Senden der Benachrichtigung: {e}")
    
    return stats


def start_scan(settings, progress_bar=None, log_callback=None, cancel_flag=None, source="manual", mark_run_date=True):
    """Synchroner Einstiegspunkt für manuelle und geplante Scans mit globaler Sperre."""
    log = log_callback or (lambda msg: logger.info(msg))

    if not scan_lock.acquire(blocking=False):
        log("⚠️ Ein anderer Scan läuft bereits. Überspringe.")
        return None

    try:
        if mark_run_date:
            today_str = dt.datetime.now().strftime("%Y-%m-%d")
            update_last_run_date(today_str)
        return asyncio.run(run_scan_engine(progress_bar, log, settings, cancel_flag))
    finally:
        scan_lock.release()

# --- SCHEDULER ---
def run_scheduler_thread():
    """
    Hintergrund-Scheduler mit robusterem Zeitfenster-Check.
    Prüft alle 30 Sekunden und verwendet ein 2-Minuten-Fenster.
    """
    logger.info("⏰ Hintergrund-Scheduler gestartet.")

    while True:
        try:
            settings = load_settings()
            if settings.get("schedule_active"):
                target_time_str = settings.get("schedule_time", "04:00")
                now = dt.datetime.now()
                current_date_str = now.strftime("%Y-%m-%d")
                last_run_date = load_run_state().get("last_run_date")
                
                # Parse target time
                try:
                    target_hour, target_minute = map(int, target_time_str.split(":"))
                    target_time = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
                except ValueError:
                    logger.error(f"Ungültiges Zeitformat: {target_time_str}")
                    time.sleep(60)
                    continue
                
                # Zeitfenster-Check: 2 Minuten Toleranz
                time_diff = abs((now - target_time).total_seconds())
                in_window = time_diff <= 120  # 2 Minuten Fenster
                
                if in_window and last_run_date != current_date_str:
                    logger.info(f"⏰ ZEITPLAN AUSLÖSUNG: {now.strftime('%H:%M:%S')}")
                    update_last_run_date(current_date_str)

                    def dummy_log(msg):
                        logger.info(f"[AUTO-SCAN] {msg}")

                    try:
                        result = start_scan(
                            settings,
                            progress_bar=None,
                            log_callback=dummy_log,
                            cancel_flag=None,
                            source="scheduler",
                            mark_run_date=False,
                        )
                        if result is not None:
                            logger.info("⏰ Geplanter Scan abgeschlossen.")
                        else:
                            logger.info("⏭️ Geplanter Scan übersprungen (Scan läuft bereits).")
                    except Exception as scan_error:
                        logger.error(f"Fehler beim geplanten Scan: {scan_error}")

            time.sleep(30)  # Alle 30 Sekunden prüfen statt 59
        except Exception as e:
            logger.error(f"Scheduler Fehler: {e}")
            time.sleep(60)

