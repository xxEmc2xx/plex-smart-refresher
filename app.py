import streamlit as st


# --- Session State Defaults (robust) ---
def _ensure_session_defaults():
    defaults = {
        "scan_running": False,
        "scan_stats": None,
        "scan_logs": [],
        "active_job_id": None,
        "auto_refresh": True,
        "cancel_notice": None,
        "authenticated": False,
        "login_attempts": 0,
        "lockout_until": None,
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

_ensure_session_defaults()

@st.cache_data(ttl=60)
def get_cached_statistics():
    """Cached Gesamtstatistiken aus der DB."""
    try:
        return logic.get_total_statistics()
    except Exception:
        return {"total_checked": 0, "total_fixed": 0, "total_failed": 0, "success_rate": 0}
import streamlit_authenticator as stauth
from auth import ensure_auth_config
import asyncio
import os
# --- LOGIN CONFIG (auto-fix) ---
PASSWORD = os.getenv("GUI_PASSWORD")
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

import datetime as dt
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logic
import threading
import time
import json

import jobs

@st.cache_resource
def _startup_cleanup_once():
    # Läuft 1x pro Streamlit-Prozess (nicht bei jedem Rerun)
    try:
        removed_logs = jobs.cleanup_old_logs()
        removed_runs = jobs.cleanup_old_scan_runs()
        if removed_logs or removed_runs:
            print(f"[CLEANUP] removed_logs={removed_logs} removed_scan_runs={removed_runs}")
    except Exception as e:
        print(f"[CLEANUP] error: {e}")
    return True

_startup_cleanup_once()

st.set_page_config(page_title="Plex Refresher", page_icon="🚀", layout="wide")

# --- CUSTOM CSS FÜR MOBILE + DESKTOP ---
st.markdown("""
<style>
    /* === GENERELL === */
    /* Größere Metrik-Zahlen */
    [data-testid="stMetricValue"] {
        font-size: 1.8rem !important;
        font-weight: 700 !important;
    }
    [data-testid="stMetricLabel"] {
        font-size: 0.9rem !important;
    }

    /* Buttons besser klickbar */
    .stButton > button {
        min-height: 2.8rem !important;
        font-size: 1rem !important;
    }

    /* === MOBILE (< 768px) === */
    @media (max-width: 768px) {
        /* Weniger Padding */
        .block-container {
            padding-left: 1rem !important;
            padding-right: 1rem !important;
            padding-top: 1rem !important;
        }

        /* Kleinere Metrik-Zahlen */
        [data-testid="stMetricValue"] {
            font-size: 1.4rem !important;
        }

        /* Tabs kompakter */
        .stTabs [data-baseweb="tab-list"] {
            gap: 0.5rem !important;
        }
        .stTabs [data-baseweb="tab"] {
            padding: 0.5rem 0.8rem !important;
            font-size: 0.85rem !important;
        }

        /* Größere Touch-Targets */
        .stButton > button {
            min-height: 3rem !important;
            width: 100% !important;
        }

        .stCheckbox label {
            font-size: 1rem !important;
            padding: 0.5rem 0 !important;
        }
    }

    /* === FARBEN FÜR STATUS === */
    /* Positive Metriken (Gefixt) leicht grün */
    div[data-testid="metric-container"]:nth-of-type(2) [data-testid="stMetricValue"] {
        color: #4ade80 !important;
    }

    /* Negative Metriken (Fehler) leicht rot */
    div[data-testid="metric-container"]:nth-of-type(4) [data-testid="stMetricValue"] {
        color: #f87171 !important;
    }
</style>
""", unsafe_allow_html=True)

# --- INITIALISIERUNG ---
load_dotenv()

# --- STARTUP: Orphaned running jobs markieren (einmal pro Prozess) ---
@st.cache_resource
def _startup_orphan_recovery():
    return jobs.mark_orphaned_jobs_interrupted()

_startup_orphan_recovery()

# --- STARTUP: Scheduler-Thread starten (einmal pro Prozess) ---
@st.cache_resource
def _start_scheduler_thread():
    """Startet den Hintergrund-Scheduler (einmal pro Prozess)."""
    t = threading.Thread(target=logic.run_scheduler_thread, daemon=True)
    t.start()
    logic.logger.info("⏰ Scheduler-Thread via app.py gestartet")
    return t

_start_scheduler_thread()


# --- BACKGROUND SCAN JOB RUNNER ---

def _run_scan_job(job_id: str, settings: dict):
    """
    Führt einen Scan als Background-Job aus und beachtet cancel_requested aus der DB.
    """
    import datetime as _dt
    import json as _json
    import traceback as _tb
    from pathlib import Path as _Path
    def _cancel_check() -> bool:
        try:
            return bool(jobs.is_cancel_requested(job_id))
        except Exception:
            try:
                j = jobs.get_job(job_id) or {}
                return bool(j.get("cancel_requested"))
            except Exception:
                return False

    def _append_log(msg: str):
        try:
            job = jobs.get_job(job_id)
            lp = (job or {}).get("log_path")
            if not lp:
                return
            ts = _dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            _Path(lp).parent.mkdir(parents=True, exist_ok=True)
            with open(lp, "a", encoding="utf-8") as f:
                f.write(f"{ts} {msg}\n")
        except Exception:
            pass
        return _cancel_check()

    def job_log(msg: str):
        # bei jedem Log einmal cancel_requested checken
        _append_log(msg)

    try:
        # Scan laufen lassen (wichtig: cancel_flag wird übergeben!)
        stats = logic.start_scan(
            settings,
            progress_bar=None,
            log_callback=job_log,
            cancel_flag=_cancel_check,
            source="manual",
            mark_run_date=False,
        )

        if _cancel_check():
            jobs.set_job_status(job_id, status="cancelled", stats=stats, error="cancelled")
            _append_log("🛑 Job beendet (cancelled).")
        else:
            jobs.set_job_status(job_id, status="success", stats=stats, error=None)
            _append_log("✅ Job erfolgreich beendet.")

    except Exception as e:
        try:
            jobs.set_job_status(job_id, status="failed", stats=None, error=str(e))
        except Exception:
            pass
        _append_log(f"❌ Job failed: {e}")
        _append_log(_tb.format_exc())
def require_auth() -> None:
    config = ensure_auth_config()
    authenticator = stauth.Authenticate(
        config["credentials"],
        config["cookie"]["name"],
        config["cookie"]["key"],
        config["cookie"]["expiry_days"],
    )

    authenticator.login(
        location="main",
        max_login_attempts=MAX_LOGIN_ATTEMPTS,
        key="Login",
        fields={
            "Form name": "Login",
            "Username": "Benutzername",
            "Password": "Passwort",
            "Login": "Anmelden",
        },
    )

    if st.session_state.get("authentication_status") is True:
        authenticator.logout("Logout", location="sidebar", key="Logout")
        st.sidebar.caption(f"Eingeloggt als: {st.session_state.get('username')}")
        return

    if st.session_state.get("authentication_status") is False:
        st.error("❌ Benutzername/Passwort ist falsch.")
    else:
        st.info("Bitte einloggen.")
        st.caption("Standard-Benutzername ist „admin“ (PSR_AUTH_USERNAME).")
    st.stop()



@st.cache_data(ttl=300)
def get_cached_library_names():
    """Cached Plex-Library-Namen (TTL 5 Minuten)."""
    try:
        return logic.get_library_names()
    except Exception:
        return []


def main():
    require_auth()

    current_settings = logic.load_settings()

    st.title("🚀 Plex Smart Refresher")

    # --- SCHEDULER STATUS BADGE ---
    schedule_active = current_settings.get("schedule_active", False)
    schedule_time = current_settings.get("schedule_time", "04:00")

    if schedule_active:
        # Letzten Scan-Zeitpunkt aus run_state holen
        last_run = logic.load_run_state().get("last_run_date", "Noch nie")
        st.caption(f"⏰ Zeitplan aktiv: täglich um **{schedule_time}** Uhr · Letzter Lauf: **{last_run}**")
    else:
        st.caption("⏸️ Zeitplan deaktiviert · Nur manuelle Scans")

    # --- TABS FÜR BESSERE ÜBERSICHT ---
    tab1, tab2, tab3 = st.tabs(["🏠 Dashboard", "📊 Statistiken", "⚙️ Einstellungen"])
    
    # --- TAB 1: DASHBOARD ---
    with tab1:
        # Bestätigungs-Dialog
        with st.expander("ℹ️ Scan-Information", expanded=False):
            lib_count = len(current_settings.get("libraries", []))
            st.info(f"Es werden **{lib_count} Bibliotheken** gescannt mit maximal **{current_settings.get('max_items', 50)} Items** pro Bibliothek.")
        
        # Scan-Button mit Bestätigung
        col1, col2 = st.columns([1, 3])

        # Live-Status VOR den Buttons setzen (damit 'Scan abbrechen' sofort erscheint)
        running_now = jobs.get_running_job()
        st.session_state.scan_running = bool(running_now)

        
        confirm = col1.checkbox("Scan bestätigen", key="confirm_scan")

        # DB-Status VOR den Buttons bestimmen (wichtig für Safari/UI)
        running = jobs.get_running_job()
        is_running = bool(running)
        st.session_state.scan_running = is_running

        scan_button = col1.button(
            "▶️ JETZT SCANNEN",
            type="primary",
            disabled=(is_running or not confirm),
            width="stretch"
        )

        # Abbrechen-Button während Scan (DB-basiert, Safari-safe)
        if is_running:
            if col2.button("⏹️ SCAN ABBRECHEN", type="secondary"):
                jobs.request_cancel(running["job_id"])
                st.session_state.cancel_notice = running["job_id"]
                # kein sofortiges st.rerun(): sonst sieht man die Meldung oft nicht

        # Persistentes Feedback, falls Cancel gedrückt wurde
        if st.session_state.cancel_notice:
            st.warning(f"⚠️ Abbruch angefordert (Job {st.session_state.cancel_notice}).")
            # Wenn nichts mehr läuft, Notice zurücksetzen
            if not is_running:
                st.session_state.cancel_notice = None

        if scan_button:
            running = jobs.get_running_job()
            if running:
                st.warning(f"⚠️ Es läuft bereits ein Scan (Job {running['job_id']}).")
            else:
                job = jobs.create_scan_job(source="manual")
                st.session_state.active_job_id = job["job_id"]
                t = threading.Thread(target=_run_scan_job, args=(job["job_id"], current_settings), daemon=True)
                t.start()
                st.success(f"✅ Scan im Hintergrund gestartet (Job {job['job_id']}).")
            st.rerun()

        # --- METRIKEN MIT ERFOLGSRATE ---
        # --- Stats aus DB (letzter Job) laden, falls Session-Stats leer sind ---
        db_stats = None
        try:
            last_jobs = jobs.list_jobs(limit=1)
            if last_jobs and last_jobs[0].get("stats_json"):
                db_stats = json.loads(last_jobs[0]["stats_json"])
        except Exception:
            db_stats = None

        stats_to_show = st.session_state.scan_stats or db_stats

        # --- METRIKEN MIT ERFOLGSRATE ---
        stats_container = st.container()
        if stats_to_show:
            with stats_container:
                checked = stats_to_show.get('checked', 0)
                fixed = stats_to_show.get('fixed', 0)
                would_fix = stats_to_show.get('would_fix', 0)
                failed = stats_to_show.get('failed', 0)

                # Erfolgsrate berechnen (nur echte Fixes zählen)
                problems_found = fixed + failed
                if problems_found > 0:
                    success_rate = (fixed / problems_found * 100)
                    if success_rate >= 80:
                        rate_emoji = "🟢"
                    elif success_rate >= 50:
                        rate_emoji = "🟡"
                    else:
                        rate_emoji = "🔴"
                    rate_text = f"{rate_emoji} {success_rate:.1f}%"
                else:
                    rate_text = "✨ Alles OK"

                # Reihe 1: Geprüft, Gefixt, Würde fixen
                c1, c2, c3 = st.columns(3)
                c1.metric("Geprüft", checked)
                c2.metric("Gefixt", fixed)
                c3.metric("Würde fixen", would_fix)

                # Reihe 2: Fehler, Erfolgsrate
                c4, c5 = st.columns(2)
                c4.metric("Fehler", failed)
                c5.metric("Erfolgsrate", rate_text)
        else:
            with stats_container:
                # Reihe 1
                c1, c2, c3 = st.columns(3)
                c1.metric("Geprüft", "-")
                c2.metric("Gefixt", "-")
                c3.metric("Würde fixen", "-")

                # Reihe 2
                c4, c5 = st.columns(2)
                c4.metric("Fehler", "-")
                c5.metric("Erfolgsrate", "-")

        # --- SCAN LOGIK (Background Job) ---
        running = jobs.get_running_job()
        if running:
            st.session_state.scan_running = True
            st.info(f"🔄 Scan läuft im Hintergrund (Job {running['job_id']}).")
        else:
            st.session_state.scan_running = False

        # --- JOB STATUS + PERSISTENTES LOG (aus Datei) ---
        st.divider()
        running = jobs.get_running_job()
        last_jobs = jobs.list_jobs(limit=1)
        last_job = last_jobs[0] if last_jobs else None

        # active_job_id merken (Recovery nach Reload)
        if "active_job_id" not in st.session_state:
            st.session_state.active_job_id = None
        if running:
            st.session_state.active_job_id = running["job_id"]
        elif not st.session_state.active_job_id and last_job:
            st.session_state.active_job_id = last_job["job_id"]

        with st.expander("📜 Job Log (persistent)", expanded=bool(running)):
            # Auto-Refresh (nur sinnvoll wenn running)
            if "auto_refresh" not in st.session_state:
                st.session_state.auto_refresh = True

            # Job-Auswahl: letzte 20 Jobs
            job_list = jobs.list_jobs(limit=20)
            options = []
            for j in job_list:
                started = (j.get("started_at") or "")[:19].replace("T", " ")
                options.append(f"{started} | {j.get('status')} | {j.get('job_id')}")
            selected = None
            if options:
                default_idx = 0
                # wenn active_job_id existiert, passenden Eintrag vorwählen
                if st.session_state.active_job_id:
                    for i, opt in enumerate(options):
                        if st.session_state.active_job_id in opt:
                            default_idx = i
                            break
                selected = st.selectbox("Letzte Jobs", options, index=default_idx)
                # job_id aus dem String extrahieren (letztes Feld)
                st.session_state.active_job_id = selected.split("|")[-1].strip()

            # Auto-Refresh Toggle
            if running:
                st.session_state.auto_refresh = st.toggle("🔁 Auto-Refresh (alle 2s)", value=st.session_state.auto_refresh)
            else:
                st.session_state.auto_refresh = False
            job = running or (jobs.get_job(st.session_state.active_job_id) if st.session_state.active_job_id else None) or last_job

            if not job:
                st.info("Noch kein Job vorhanden. Starte einen Scan.")
            else:
                # Kompakte Status-Zeile
                status_emoji = {"running": "🔄", "success": "✅", "failed": "❌", "cancelled": "🛑", "interrupted": "⚠️"}.get(job['status'], "⏸️")
                job_id_short = job['job_id'][:8]
                st.markdown(f"{status_emoji} **{job['status'].upper()}** · Job `{job_id_short}...`")

                # Zeit-Info kompakt
                if job.get("started_at") and job.get("finished_at"):
                    start = job['started_at'][11:19] if len(job['started_at']) > 19 else job['started_at']
                    end = job['finished_at'][11:19] if len(job['finished_at']) > 19 else job['finished_at']
                    st.caption(f"⏱️ {start} → {end}")
                elif job.get("started_at"):
                    start = job['started_at'][11:19] if len(job['started_at']) > 19 else job['started_at']
                    st.caption(f"⏱️ Gestartet: {start}")

                # Button volle Breite
                if st.button("🔄 Log aktualisieren", use_container_width=True):
                    st.rerun()


                # Tail anzeigen
                tail = jobs.tail_job_log(job["job_id"], n=200)
                if tail.strip():
                    st.text_area("Letzte 200 Zeilen", tail, height=320)
                else:
                    st.info("Log ist noch leer oder Logfile nicht gefunden.")

                # Auto-Refresh (nur wenn Job läuft)
                if running and st.session_state.get("auto_refresh"):
                    time.sleep(2)
                    st.rerun()
    
    # --- TAB 2: STATISTIKEN ---
    with tab2:
        st.header("📊 Gesamtstatistiken")
        
        # Gesamtstatistiken abrufen
        total_stats = get_cached_statistics()
        
        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Total Geprüft", total_stats["total_checked"])
        col2.metric("Total Gefixt", total_stats["total_fixed"])
        col3.metric("Total Fehler", total_stats["total_failed"])
        
        total_rate = total_stats["success_rate"]
        if total_rate >= 80:
            rate_emoji = "🟢"
        elif total_rate >= 50:
            rate_emoji = "🟡"
        else:
            rate_emoji = "🔴"
        col4.metric("Gesamterfolgsrate", f"{rate_emoji} {total_rate:.1f}%")
        
        st.divider()
        
        # --- HISTORIE MIT SUCHFUNKTION ---
        st.subheader("📊 Ergebnis-Historie")
        
        # Suchfilter
        col1, col2, col3 = st.columns([2, 1, 1])
        
        # Check if filters changed and reset page
        search_title = col1.text_input("🔍 Titel suchen", placeholder="Suche nach Titel...", key="search_title")
        status_filter = col2.selectbox("Status Filter", ["Alle", "Fixed", "Failed", "Dry Run"], key="status_filter")
        
        # Reset page if filters changed
        if "last_search" not in st.session_state:
            st.session_state.last_search = ""
        if "last_status" not in st.session_state:
            st.session_state.last_status = "Alle"
        
        if (st.session_state.last_search != search_title or 
            st.session_state.last_status != status_filter):
            st.session_state.history_page = 0
            st.session_state.last_search = search_title
            st.session_state.last_status = status_filter
        
        # Pagination
        items_per_page = 20
        if "history_page" not in st.session_state:
            st.session_state.history_page = 0
        
        if col3.button("🔄 Aktualisieren"):
            get_cached_statistics.clear()
            st.rerun()
        
        # Daten abrufen
        rows = logic.get_last_report(limit=500, only_fixed=False)
        
        if rows:
            data = []
            for r in rows:
                # Filter anwenden
                if search_title and search_title.lower() not in r['title'].lower():
                    continue
                    
                if status_filter != "Alle":
                    if status_filter.lower() != r['state']:
                        continue
                
                symbol = "✅" if r['state'] == 'fixed' else "❌" if r['state'] == 'failed' else "🧪"
                ts = r['updated_at']
                try:
                    dt_obj = dt.datetime.fromisoformat(ts)
                    ts = dt_obj.strftime("%d.%m. %H:%M")
                except: 
                    pass
                
                data.append({
                    "S": symbol,
                    "Zeit": ts,
                    "Bibliothek": r['library'],
                    "Titel": r['title'],
                    "Meldung": r['note']
                })
            
            # Pagination
            start_idx = st.session_state.history_page * items_per_page
            end_idx = start_idx + items_per_page
            page_data = data[start_idx:end_idx]
            
            if page_data:
                st.dataframe(
                    pd.DataFrame(page_data), 
                    width="stretch", 
                    hide_index=True,
                    column_config={
                        "S": st.column_config.TextColumn("Status", width="small"),
                        "Zeit": st.column_config.TextColumn("Zeit", width="small"),
                        "Meldung": st.column_config.TextColumn("Details")
                    }
                )
                
                # Pagination Controls
                col1, col2, col3 = st.columns([1, 2, 1])
                total_pages = (len(data) - 1) // items_per_page + 1
                
                if col1.button("⬅️ Vorherige", disabled=st.session_state.history_page == 0):
                    st.session_state.history_page -= 1
                    st.rerun()
                
                col2.write(f"Seite {st.session_state.history_page + 1} von {total_pages}")
                
                if col3.button("Nächste ➡️", disabled=st.session_state.history_page >= total_pages - 1):
                    st.session_state.history_page += 1
                    st.rerun()
            else:
                st.info("Keine Ergebnisse für die gewählten Filter.")
        else:
            st.info("Die Datenbank ist noch leer. Starte einen Scan!")
    
    # --- TAB 3: EINSTELLUNGEN ---
    with tab3:
        st.header("⚙️ Einstellungen")
        
        # Plex Einstellungen
        st.subheader("📚 Plex Bibliotheken")
        avail = get_cached_library_names()
        default_libs = [l for l in current_settings["libraries"] if l in avail]
        sel_libs = st.multiselect("Bibliotheken", avail, default=default_libs)
        
        st.divider()
        
        # Scan-Einstellungen
        st.subheader("🔧 Scan-Parameter")
        col1, col2 = st.columns(2)
        s_days = col1.slider("📅 Zeit-Filter (Tage)", 1, 365, current_settings["days"])
        s_max = col2.slider("🔢 Mengen-Limit", 10, 500, current_settings["max_items"])
        s_dry = st.toggle("🧪 Simulation (Dry Run)", value=current_settings["dry_run"])
        
        st.divider()
        
        # Zeitplaner
        st.subheader("🕒 Zeitplaner")
        try:
            saved_time = dt.datetime.strptime(current_settings["schedule_time"], "%H:%M").time()
        except ValueError:
            saved_time = dt.time(4, 0)
            
        s_time = st.time_input("Startzeit", value=saved_time)
        s_active = st.checkbox("Automatisch ausführen", value=current_settings["schedule_active"])
        
        if s_active:
            st.caption(f"✅ Täglich um {s_time.strftime('%H:%M')} Uhr.")
        
        st.divider()
        
        # Telegram Einstellungen
        st.subheader("📱 Telegram Benachrichtigungen")
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN", "")
        telegram_chat = os.getenv("TELEGRAM_CHAT_ID", "")
        
        if telegram_token and telegram_chat and telegram_token != "YOUR_BOT_TOKEN":
            st.success("✅ Telegram ist konfiguriert")
            st.caption(f"Chat-ID: {telegram_chat}")
        else:
            st.warning("⚠️ Telegram nicht konfiguriert")
            st.caption("Konfiguriere TELEGRAM_BOT_TOKEN und TELEGRAM_CHAT_ID in der .env Datei")
        
        # Autosave
        new_settings = {
            "libraries": sel_libs,
            "days": s_days,
            "max_items": s_max,
            "dry_run": s_dry,
            "schedule_active": s_active,
            "schedule_time": s_time.strftime("%H:%M")
        }
        if new_settings != current_settings:
            logic.save_settings(new_settings)
            st.success("✅ Einstellungen gespeichert")

if __name__ == "__main__":
    main()
