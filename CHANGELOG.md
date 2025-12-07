# Changelog - Plex Smart Refresher v2.0

## 🎉 Neue Features

### 1. 📱 Telegram Benachrichtigungen
- Automatische Push-Benachrichtigungen nach jedem Scan
- Statistiken werden direkt an Telegram gesendet
- Farbcodierte Erfolgsrate in Nachrichten
- Optional - funktioniert auch ohne Telegram-Konfiguration

### 2. 📊 Erfolgsrate-Anzeige
- Neue vierte Metrik zeigt Erfolgsrate an
- Farbcodierung: Grün (>80%), Gelb (>50%), Rot (<50%)
- Gesamtstatistiken über alle Scans
- Erfolgsrate im Dashboard und Statistik-Tab

### 3. 🎨 GUI-Optimierungen mit Tabs
- **Dashboard-Tab**: Scan-Steuerung, Metriken, Live-Protokoll
- **Statistik-Tab**: Detaillierte Statistiken und Historie mit Suchfunktion
- **Einstellungen-Tab**: Alle Konfigurationen an einem Ort

### 4. 🔍 Erweiterte Historie-Verwaltung
- Textsuche nach Titeln
- Status-Filter (Alle, Fixed, Failed, Dry Run)
- Pagination (20 Einträge pro Seite)
- "Mehr laden" Funktionalität

### 5. ⚡ Performance-Optimierungen
- **Connection Pooling**: Singleton-Pattern für Plex-Verbindung
- **Caching**: 5 Minuten Cache für Bibliotheksnamen, 1 Minute für Statistiken
- **Batch Processing**: Vorbereitet für parallele Item-Verarbeitung
- **Lazy Loading**: Pagination für Historie reduziert Speicherverbrauch

### 6. 🔐 Sicherheits-Features
- Begrenzung der Login-Versuche (Standard: 5 Versuche)
- Automatische Sperrung nach zu vielen Fehlversuchen
- Konfigurierbare Sperrzeit (Standard: 15 Minuten)
- Countdown-Anzeige bis zur Entsperrung

### 7. 🛠️ Verbesserte Scan-Steuerung
- Bestätigungs-Checkbox vor Scan-Start
- Info-Box zeigt Anzahl der zu scannenden Bibliotheken
- Abbrechen-Button während laufendem Scan
- Geschätzte Restzeit (ETA) während des Scans
- Detaillierter Fortschritt: "X von Y Items"

## 📝 Geänderte Dateien

### Neue Dateien:
- `notifications.py` - Telegram-Integration
- `.gitignore` - Git-Konfiguration
- `CHANGELOG.md` - Dieses Dokument

### Aktualisierte Dateien:
- `app.py` - Komplette GUI-Überarbeitung mit Tabs und Sicherheit
- `logic.py` - Performance-Optimierungen und Telegram-Integration
- `requirements.txt` - requests Bibliothek hinzugefügt
- `.env` - Neue Umgebungsvariablen für Telegram und Sicherheit
- `README.md` - Dokumentation aller neuen Features

## 🔧 Neue Umgebungsvariablen

```ini
# Telegram (optional)
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN
TELEGRAM_CHAT_ID=YOUR_CHAT_ID

# Sicherheit
MAX_LOGIN_ATTEMPTS=5
LOGIN_LOCKOUT_MINUTES=15
```

## 🚀 Upgrade-Anleitung

1. Code aktualisieren (git pull)
2. Dependencies installieren: `pip install -r requirements.txt`
3. .env Datei aktualisieren (siehe oben)
4. Service neu starten: `systemctl restart plexgui`

## ✅ Tests durchgeführt

- ✅ Python-Syntax validiert
- ✅ Alle Importe erfolgreich
- ✅ Notification-Modul getestet
- ✅ Logic-Modul Funktionen getestet
- ✅ Sicherheits-Features validiert
- ✅ Tab-Navigation implementiert
- ✅ Erfolgsrate-Berechnung korrekt
- ✅ Caching-Funktionen integriert
