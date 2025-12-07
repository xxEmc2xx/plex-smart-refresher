import os
import asyncio
import datetime as dt
import sqlite3
import gc
import time
import json
import logging
import threading
from typing import List, Optional, Tuple, Dict, Any
from plexapi.server import PlexServer
from dotenv import load_dotenv
import notifications

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

load_dotenv()
PLEX_URL = os.getenv("PLEX_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
try:
    PLEX_TIMEOUT = int(os.getenv("PLEX_TIMEOUT", "60"))
except ValueError:
    PLEX_TIMEOUT = 60
    logger.warning("Invalid PLEX_TIMEOUT value, using default: 60")

DB_PATH = "refresh_state.db"
SETTINGS_FILE = "settings.json"

# Connection Pooling - Singleton Pattern
_plex_connection = None


def get_plex_connection():
    """
    Globale Plex-Verbindung als Singleton mit Auto-Reconnect.
    """
    global _plex_connection
    if _plex_connection is None:
        try:
            _plex_connection = PlexServer(PLEX_URL, PLEX_TOKEN, timeout=PLEX_TIMEOUT)
        except Exception as e:
            print(f"Fehler beim Herstellen der Plex-Verbindung: {e}")
            raise
    return _plex_connection

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

# --- DATABASE ---
def init_db():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute("""
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
    conn.close()

# Initialize database on module load to prevent "no such table" errors
init_db()

def save_result(rating_key, library, title, state, note):
    conn = sqlite3.connect(DB_PATH)
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
    """, (rating_key, library, title, now, state, note, now))
    conn.commit()
    conn.close()

def get_last_report(limit=100, only_fixed=False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = "SELECT * FROM media_state"
    if only_fixed:
        query += " WHERE state='fixed'"
    query += " ORDER BY last_scan DESC LIMIT ?"
    rows = conn.execute(query, (limit,)).fetchall()
    conn.close()
    return rows


def get_total_statistics():
    """
    Berechnet Gesamtstatistiken aus der Datenbank.
    
    Returns:
        Dictionary mit total_checked, total_fixed, total_failed, success_rate
    """
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    
    # Zähle alle Einträge
    total_checked = c.execute("SELECT COUNT(*) FROM media_state").fetchone()[0]
    total_fixed = c.execute("SELECT COUNT(*) FROM media_state WHERE state='fixed'").fetchone()[0]
    total_failed = c.execute("SELECT COUNT(*) FROM media_state WHERE state='failed'").fetchone()[0]
    
    conn.close()
    
    success_rate = (total_fixed / (total_fixed + total_failed) * 100) if (total_fixed + total_failed) > 0 else 0
    
    return {
        "total_checked": total_checked,
        "total_fixed": total_fixed,
        "total_failed": total_failed,
        "success_rate": success_rate
    }

# --- PLEX LOGIC ---
def needs_refresh(item) -> bool:
    if not item.guids: return True
    if not item.thumb: return True
    if not item.summary: return True
    return False

async def smart_refresh_item(item, status_callback=None) -> Tuple[bool, str]:
    try:
        item.refresh()
    except Exception as e:
        return False, f"API Fehler: {str(e)}"

    max_attempts = 12
    for attempt in range(1, max_attempts + 1):
        await asyncio.sleep(5)
        try:
            item.reload()
            if not needs_refresh(item):
                return True, f"Gefixt nach {attempt * 5}s"
        except:
            pass
    return False, "Timeout (60s)"


async def batch_refresh_items(items, batch_size=5, log_callback=None):
    """
    Mehrere Items parallel refreshen mit asyncio.gather für bessere Performance.
    
    Args:
        items: Liste von Items zum Refreshen
        batch_size: Anzahl gleichzeitiger Refresh-Operationen
        log_callback: Optional callback für Logging
        
    Returns:
        Liste von Tuples (success, message) für jedes Item
    """
    results = []
    total_items = len(items)
    
    for i in range(0, total_items, batch_size):
        batch = items[i:i+batch_size]
        if log_callback:
            log_callback(f"Batch {i//batch_size + 1}: Verarbeite {len(batch)} Items parallel...")
        
        batch_results = await asyncio.gather(
            *[smart_refresh_item(item) for item in batch],
            return_exceptions=True
        )
        results.extend(batch_results)
    
    return results

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

    stats = {"checked": 0, "fixed": 0, "failed": 0}
    days = settings.get("days", 30)
    max_items = settings.get("max_items", 50)
    target_libs = settings.get("libraries", [])
    dry_run = settings.get("dry_run", False)
    
    cutoff = dt.datetime.now() - dt.timedelta(days=days)
    start_time = time.time()
    
    # Calculate total items for better ETA
    all_items = []
    total_items = 0
    for lib_name in target_libs:
        try:
            lib = plex.library.section(lib_name)
            recent = lib.all(sort="addedAt:desc", limit=max_items)
            all_items.append((lib_name, recent))
            total_items += len(recent)
        except Exception as e:
            log_callback(f"Fehler beim Laden von {lib_name}: {e}")

    items_processed = 0
    for lib_name, items in all_items:
        # Prüfe Abbruch-Flag
        if cancel_flag and cancel_flag.get("cancelled", False):
            log_callback("⚠️ Scan abgebrochen!")
            break
            
        log_callback(f"Analysiere: {lib_name}")
        try:
            total = len(items)

            for i, item in enumerate(items):
                # Prüfe Abbruch-Flag
                if cancel_flag and cancel_flag.get("cancelled", False):
                    log_callback("⚠️ Scan abgebrochen!")
                    break
                    
                if progress_bar:
                    # Berechne geschätzte Restzeit basierend auf allen Items
                    elapsed = time.time() - start_time
                    if stats["checked"] > 0:
                        avg_time_per_item = elapsed / stats["checked"]
                        items_remaining = total_items - items_processed - 1
                        eta_seconds = avg_time_per_item * items_remaining
                        eta_str = f" (ETA: {int(eta_seconds)}s)"
                    else:
                        eta_str = ""
                    
                    progress_bar.progress(
                        (items_processed + 1) / total_items, 
                        text=f"{lib_name}: {item.title} ({items_processed+1}/{total_items}){eta_str}"
                    )
                
                items_processed += 1
                
                if item.addedAt < cutoff:
                    continue
                
                stats["checked"] += 1
                
                if needs_refresh(item):
                    if dry_run:
                        log_callback(f"-> [SIM] Würde fixen: {item.title}")
                        save_result(item.ratingKey, lib_name, item.title, "dry_run", "Simulation")
                        stats["fixed"] += 1
                    else:
                        log_callback(f"-> Fixe: {item.title}...")
                        ok, msg = await smart_refresh_item(item)
                        if ok:
                            log_callback(f"✅ {item.title}: {msg}")
                            save_result(item.ratingKey, lib_name, item.title, "fixed", msg)
                            stats["fixed"] += 1
                        else:
                            log_callback(f"❌ {item.title}: {msg}")
                            save_result(item.ratingKey, lib_name, item.title, "failed", msg)
                            stats["failed"] += 1
                del item
            gc.collect()
        except Exception as e:
            log_callback(f"Fehler in {lib_name}: {e}")

    log_callback("Fertig.")
    
    # Telegram-Benachrichtigung senden
    if stats and stats.get("checked", 0) > 0:
        notifications.send_scan_completion_notification(stats)
    
    return stats

# --- SCHEDULER ---
def run_scheduler_thread():
    logger.info("⏰ Hintergrund-Scheduler gestartet.")
    last_run_date = None

    while True:
        try:
            settings = load_settings()
            if settings.get("schedule_active"):
                target_time_str = settings.get("schedule_time", "04:00")
                now = dt.datetime.now()
                current_time_str = now.strftime("%H:%M")
                current_date_str = now.strftime("%Y-%m-%d")

                if current_time_str == target_time_str and last_run_date != current_date_str:
                    logger.info(f"⏰ ZEITPLAN AUSLÖSUNG: {current_time_str}")
                    def dummy_log(msg): logger.info(f"[AUTO-SCAN] {msg}")
                    asyncio.run(run_scan_engine(None, dummy_log, settings))
                    last_run_date = current_date_str
            time.sleep(59)
        except Exception as e:
            logger.error(f"Scheduler Fehler: {e}")
            time.sleep(60)

# Initialize database on module load to prevent "no such table" errors
init_db()
