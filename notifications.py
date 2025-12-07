import os
import requests
from typing import Dict, Optional
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")


def send_telegram_message(message: str) -> bool:
    """
    Send a message via Telegram Bot API.
    
    Args:
        message: The message to send
        
    Returns:
        True if successfully sent, False on error
    """
    if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHAT_ID:
        print("⚠️ Telegram not configured (TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing)")
        return False
    
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        print("✅ Telegram-Nachricht erfolgreich gesendet")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Fehler beim Senden der Telegram-Nachricht: {e}")
        return False


def send_scan_completion_notification(stats: Dict[str, int]) -> bool:
    """
    Send a notification after scan completion with statistics.
    
    Args:
        stats: Dictionary with 'checked', 'fixed', 'failed' values
        
    Returns:
        True if successfully sent, False on error
    """
    if not stats:
        return False
    
    checked = stats.get('checked', 0)
    fixed = stats.get('fixed', 0)
    failed = stats.get('failed', 0)
    
    # Erfolgsrate berechnen
    problems_found = fixed + failed
    if problems_found > 0:
        success_rate = (fixed / problems_found * 100)
        rate_emoji = "🟢" if success_rate >= 80 else "🟡" if success_rate >= 50 else "🔴"
        rate_text = f"{rate_emoji} {success_rate:.1f}%"
    else:
        # Keine Probleme gefunden = perfekt!
        rate_text = "✨ Keine Probleme gefunden"
    
    message = f"""
🚀 <b>Plex Smart Refresher - Scan abgeschlossen</b>

📊 <b>Statistiken:</b>
• Geprüft: {checked}
• Gefixt: {fixed} ✅
• Fehler: {failed} ❌
• Ergebnis: {rate_text}
"""
    
    return send_telegram_message(message.strip())
