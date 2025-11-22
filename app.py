import streamlit as st
import asyncio
import os
import datetime as dt
import pandas as pd
from dotenv import load_dotenv
import logic
import threading

st.set_page_config(page_title="Plex Refresher", page_icon="🚀", layout="wide")

# --- INITIALISIERUNG ---
load_dotenv()
PASSWORD = os.getenv("GUI_PASSWORD")

@st.cache_resource
def start_background_service():
    t = threading.Thread(target=logic.run_scheduler_thread, daemon=True)
    t.start()
    return t

start_background_service()

# Session State Initialisierung
if "scan_running" not in st.session_state:
    st.session_state.scan_running = False
if "scan_stats" not in st.session_state:
    st.session_state.scan_stats = None
if "scan_logs" not in st.session_state:
    st.session_state.scan_logs = []

# --- LOGIN ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False

def check_password():
    if not st.session_state.authenticated:
        pwd = st.text_input("🔑 Passwort eingeben:", type="password")
        if pwd == PASSWORD:
            st.session_state.authenticated = True
            st.rerun()
        return False
    return True

# --- HAUPTPROGRAMM ---
def main():
    if not check_password():
        return

    current_settings = logic.load_settings()

    st.title("🚀 Plex Smart Refresher")
    
    # --- SEITENLEISTE ---
    with st.sidebar:
        st.header("⚙️ Einstellungen")
        
        avail = logic.get_library_names()
        default_libs = [l for l in current_settings["libraries"] if l in avail]
        sel_libs = st.multiselect("Bibliotheken", avail, default=default_libs)
        
        st.divider()
        s_days = st.slider("📅 Zeit-Filter (Tage)", 1, 365, current_settings["days"])
        s_max = st.slider("🔢 Mengen-Limit", 10, 500, current_settings["max_items"])
        s_dry = st.toggle("🧪 Simulation (Dry Run)", value=current_settings["dry_run"])
        
        st.divider()
        st.subheader("🕒 Zeitplaner")
        try:
            saved_time = dt.datetime.strptime(current_settings["schedule_time"], "%H:%M").time()
        except:
            saved_time = dt.time(4, 0)
            
        s_time = st.time_input("Startzeit", value=saved_time)
        s_active = st.checkbox("Automatisch ausführen", value=current_settings["schedule_active"])
        
        if s_active:
            st.caption(f"✅ Täglich um {s_time.strftime('%H:%M')} Uhr.")

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

        st.divider()
        if st.button("🚪 Abmelden"):
            st.session_state.authenticated = False
            st.rerun()

    # --- BUTTONS ---
    col1, col2 = st.columns([1, 3])
    
    if col1.button("▶️ JETZT SCANNEN", type="primary", disabled=st.session_state.scan_running, use_container_width=True):
        st.session_state.scan_running = True
        st.rerun()

    # --- METRIKEN ---
    stats_container = st.container()
    if st.session_state.scan_stats:
        with stats_container:
            c1, c2, c3 = st.columns(3)
            c1.metric("Geprüft", st.session_state.scan_stats['checked'])
            c2.metric("Gefixt", st.session_state.scan_stats['fixed'])
            c3.metric("Fehler", st.session_state.scan_stats['failed'])
    else:
        with stats_container:
            c1, c2, c3 = st.columns(3)
            c1.metric("Geprüft", "-")
            c2.metric("Gefixt", "-")
            c3.metric("Fehler", "-")

    # --- SCAN LOGIK ---
    if st.session_state.scan_running:
        st.session_state.scan_logs = [] 
        progress_bar = st.progress(0)
        log_area = st.empty()
        
        def gui_logger(msg):
            st.session_state.scan_logs.insert(0, f"• {msg}")
            log_area.text("\n".join(st.session_state.scan_logs[:15]))

        with st.spinner("Scan läuft..."):
            stats = asyncio.run(logic.run_scan_engine(progress_bar, gui_logger, new_settings))
        
        st.session_state.scan_stats = stats
        st.session_state.scan_running = False
        st.rerun()

    # --- LOG & TABELLE ---
    st.divider()

    with st.expander("📜 Live Protokoll", expanded=st.session_state.scan_running):
        if st.session_state.scan_logs:
            st.text("\n".join(st.session_state.scan_logs[:50]))
        else:
            st.info("Warte auf Start...")

    st.subheader("📊 Ergebnis-Bericht (Historie)")
    
    if st.button("🔄 Tabelle aktualisieren"):
        st.rerun()

    rows = logic.get_last_report(limit=50, only_fixed=False)
    if rows:
        data = []
        for r in rows:
            symbol = "✅" if r['state'] == 'fixed' else "❌" if r['state'] == 'failed' else "🧪"
            ts = r['updated_at']
            try:
                dt_obj = dt.datetime.fromisoformat(ts)
                ts = dt_obj.strftime("%d.%m. %H:%M")
            except: pass
            
            data.append({
                "S": symbol,
                "Zeit": ts,
                "Bibliothek": r['library'],
                "Titel": r['title'],
                "Meldung": r['note']
            })
        
        st.dataframe(
            pd.DataFrame(data), 
            use_container_width=True, 
            hide_index=True,
            column_config={
                "S": st.column_config.TextColumn("Status", width="small"),
                "Zeit": st.column_config.TextColumn("Zeit", width="small"),
                "Meldung": st.column_config.TextColumn("Details")
            }
        )
    else:
        st.info("Die Datenbank ist noch leer. Starte einen Scan!")

if __name__ == "__main__":
    main()
