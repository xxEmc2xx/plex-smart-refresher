import streamlit as st
import asyncio
import os
import datetime as dt
import pandas as pd
from datetime import datetime, timedelta
from dotenv import load_dotenv
import logic
import threading

st.set_page_config(page_title="Plex Refresher", page_icon="🚀", layout="wide")

# --- INITIALISIERUNG ---
load_dotenv()
PASSWORD = os.getenv("GUI_PASSWORD")
MAX_LOGIN_ATTEMPTS = int(os.getenv("MAX_LOGIN_ATTEMPTS", "5"))
LOGIN_LOCKOUT_MINUTES = int(os.getenv("LOGIN_LOCKOUT_MINUTES", "15"))

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
if "cancel_scan" not in st.session_state:
    st.session_state.cancel_scan = {"cancelled": False}
if "login_attempts" not in st.session_state:
    st.session_state.login_attempts = 0
if "lockout_until" not in st.session_state:
    st.session_state.lockout_until = None

# --- LOGIN SICHERHEIT ---
if "authenticated" not in st.session_state:
    st.session_state.authenticated = False


def check_login_lockout():
    """Prüfe ob Login gesperrt ist"""
    if st.session_state.lockout_until:
        if datetime.now() < st.session_state.lockout_until:
            remaining = int((st.session_state.lockout_until - datetime.now()).total_seconds() // 60)
            st.error(f"🔒 Login gesperrt. Versuche es in {remaining} Minuten erneut.")
            return False
        else:
            # Lockout abgelaufen
            st.session_state.lockout_until = None
            st.session_state.login_attempts = 0
    return True


def handle_failed_login():
    """Behandle fehlgeschlagenen Login"""
    st.session_state.login_attempts += 1
    
    if st.session_state.login_attempts >= MAX_LOGIN_ATTEMPTS:
        st.session_state.lockout_until = datetime.now() + timedelta(minutes=LOGIN_LOCKOUT_MINUTES)
        st.error(f"🔒 Zu viele Versuche! Login für {LOGIN_LOCKOUT_MINUTES} Minuten gesperrt.")
    else:
        remaining = MAX_LOGIN_ATTEMPTS - st.session_state.login_attempts
        st.error(f"❌ Falsches Passwort! Noch {remaining} Versuche übrig.")


def check_password():
    if not st.session_state.authenticated:
        if not check_login_lockout():
            return False
            
        pwd = st.text_input("🔑 Passwort eingeben:", type="password", key="pwd_input")
        
        if st.button("Login", type="primary"):
            if pwd == PASSWORD:
                st.session_state.authenticated = True
                st.session_state.login_attempts = 0
                st.session_state.lockout_until = None
                st.rerun()
            else:
                handle_failed_login()
                st.rerun()
        return False
    return True


# Caching für bessere Performance
@st.cache_data(ttl=300)  # 5 Minuten Cache
def get_cached_library_names():
    return logic.get_library_names()


@st.cache_data(ttl=60)  # 1 Minute Cache
def get_cached_statistics():
    return logic.get_total_statistics()


# --- HAUPTPROGRAMM ---
def main():
    if not check_password():
        return

    current_settings = logic.load_settings()

    st.title("🚀 Plex Smart Refresher")
    
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
        
        confirm = col1.checkbox("Scan bestätigen", key="confirm_scan")
        scan_button = col1.button(
            "▶️ JETZT SCANNEN", 
            type="primary", 
            disabled=(st.session_state.scan_running or not confirm),
            use_container_width=True
        )
        
        # Abbrechen-Button während Scan
        if st.session_state.scan_running:
            if col2.button("⏹️ SCAN ABBRECHEN", type="secondary", use_container_width=True):
                st.session_state.cancel_scan["cancelled"] = True
                st.warning("Abbruch wird verarbeitet...")
        
        if scan_button:
            st.session_state.scan_running = True
            st.session_state.cancel_scan = {"cancelled": False}
            st.rerun()

        # --- METRIKEN MIT ERFOLGSRATE ---
        stats_container = st.container()
        if st.session_state.scan_stats:
            with stats_container:
                c1, c2, c3, c4 = st.columns(4)
                checked = st.session_state.scan_stats['checked']
                fixed = st.session_state.scan_stats['fixed']
                failed = st.session_state.scan_stats['failed']
                
                # Erfolgsrate berechnen
                problems_found = fixed + failed
                if problems_found > 0:
                    success_rate = (fixed / problems_found * 100)
                    # Farbe basierend auf Erfolgsrate
                    if success_rate >= 80:
                        rate_color = "normal"
                        rate_emoji = "🟢"
                    elif success_rate >= 50:
                        rate_color = "normal"
                        rate_emoji = "🟡"
                    else:
                        rate_color = "inverse"
                        rate_emoji = "🔴"
                    rate_text = f"{rate_emoji} {success_rate:.1f}%"
                else:
                    # Keine Probleme gefunden
                    rate_text = "✨ Alles OK"
                    rate_color = "normal"
                
                c1.metric("Geprüft", checked)
                c2.metric("Gefixt", fixed)
                c3.metric("Fehler", failed)
                c4.metric("Erfolgsrate", rate_text)
        else:
            with stats_container:
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("Geprüft", "-")
                c2.metric("Gefixt", "-")
                c3.metric("Fehler", "-")
                c4.metric("Erfolgsrate", "-")

        # --- SCAN LOGIK ---
        if st.session_state.scan_running:
            st.session_state.scan_logs = [] 
            progress_bar = st.progress(0)
            log_area = st.empty()
            
            def gui_logger(msg):
                st.session_state.scan_logs.insert(0, f"• {msg}")
                log_area.text("\n".join(st.session_state.scan_logs[:15]))

            with st.spinner("Scan läuft..."):
                stats = logic.start_scan(
                    current_settings,
                    progress_bar=progress_bar,
                    log_callback=gui_logger,
                    cancel_flag=st.session_state.cancel_scan,
                    source="manual",
                )
            
            st.session_state.scan_stats = stats
            st.session_state.scan_running = False
            st.session_state.cancel_scan = {"cancelled": False}
            st.rerun()

        # --- LIVE PROTOKOLL ---
        st.divider()
        with st.expander("📜 Live Protokoll", expanded=st.session_state.scan_running):
            if st.session_state.scan_logs:
                st.text("\n".join(st.session_state.scan_logs[:50]))
            else:
                st.info("Warte auf Start...")
    
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
                    use_container_width=True, 
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

        st.divider()
        if st.button("🚪 Abmelden"):
            st.session_state.authenticated = False
            st.rerun()

if __name__ == "__main__":
    main()
