import os
import asyncio
import datetime as dt
import sqlite3
import gc
import time
import json
import threading
from typing import List, Optional, Tuple, Dict, Any
from plexapi.server import PlexServer
from dotenv import load_dotenv

load_dotenv()
PLEX_URL = os.getenv("PLEX_URL")
PLEX_TOKEN = os.getenv("PLEX_TOKEN")
try:
    PLEX_TIMEOUT = int(os.getenv("PLEX_TIMEOUT", "60"))
except:
    PLEX_TIMEOUT = 60

DB_PATH = "refresh_state.db"
SETTINGS_FILE = "settings.json"

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
    except:
        return default

def save_settings(settings):
    try:
        with open(SETTINGS_FILE, "w") as f:
            json.dump(settings, f, indent=4)
    except Exception as e:
        print(f"Fehler beim Speichern: {e}")

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

def get_library_names():
    try:
        plex = PlexServer(PLEX_URL, PLEX_TOKEN, timeout=10)
        return [s.title for s in plex.library.sections() if s.type in ['movie', 'show']]
    except:
        return []

# --- SCAN ENGINE ---
async def run_scan_engine(progress_bar, log_callback, settings):
    init_db()
    log_callback("Starte Scan...")
    
    try:
        plex = PlexServer(PLEX_URL, PLEX_TOKEN, timeout=PLEX_TIMEOUT)
    except Exception as e:
        log_callback(f"Verbindungsfehler: {e}")
        return None

    stats = {"checked": 0, "fixed": 0, "failed": 0}
    days = settings.get("days", 30)
    max_items = settings.get("max_items", 50)
    target_libs = settings.get("libraries", [])
    dry_run = settings.get("dry_run", False)
    
    cutoff = dt.datetime.now() - dt.timedelta(days=days)

    for lib_name in target_libs:
        log_callback(f"Analysiere: {lib_name}")
        try:
            lib = plex.library.section(lib_name)
            recent = lib.all(sort="addedAt:desc", limit=max_items)
            total = len(recent)

            for i, item in enumerate(recent):
                if progress_bar:
                    progress_bar.progress((i + 1) / total, text=f"{lib_name}: {item.title}")
                
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
    return stats

# --- SCHEDULER ---
def run_scheduler_thread():
    print("⏰ Hintergrund-Scheduler gestartet.")
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
                    print(f"⏰ ZEITPLAN AUSLÖSUNG: {current_time_str}")
                    def dummy_log(msg): print(f"[AUTO-SCAN] {msg}")
                    asyncio.run(run_scan_engine(None, dummy_log, settings))
                    last_run_date = current_date_str
            time.sleep(59)
        except Exception as e:
            print(f"Scheduler Fehler: {e}")
            time.sleep(60)
