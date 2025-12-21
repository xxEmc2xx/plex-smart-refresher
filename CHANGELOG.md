# Changelog

## v2.1.1 (Dezember 2025)

### Bugfixes
- **Encoding-Fix**: Sonderzeichen in Titeln führen nicht mehr zum Crash
- **Robuste Fehlerbehandlung**: Try/Except pro Item, ein defekter Eintrag stoppt nicht den gesamten Scan
- **Notification Restore**: Benachrichtigungen werden nach Absturz wiederhergestellt
- **Endlosschleifen verhindert**: Defekte Dateien brechen Verarbeitung nicht mehr ab

## v2.1.0 (Dezember 2025)

### Performance & Stabilität
- **Batch-Refresh**: Zurückgerollt auf sequentielle Verarbeitung (asyncio.gather blockierte)
- **Plex-Reconnect-Logik**: Automatischer Health-Check alle 5 Minuten, Reconnect bei verlorener Verbindung
- **SQLite Context Manager**: Sauberes Connection-Handling mit automatischem Schließen
- **Robusterer Scheduler**: 2-Minuten-Zeitfenster statt exaktem String-Vergleich

### Code-Qualität
- Logging vereinheitlicht (print() durch logger ersetzt)
- Cleanup ungenutzter Code

## v2.0.0 (Dezember 2025)

### Features
- **Telegram-Benachrichtigungen**: Push-Notifications nach jedem Scan mit Statistiken
- **Erfolgsrate-Anzeige**: Farbcodiert (grün >80%, gelb >50%, rot <50%)
- **GUI mit Tabs**: Dashboard, Statistik, Einstellungen
- **Login-Sicherheit**: Max. 5 Versuche, 15 Min. Sperrzeit
- **Suchfunktion**: Historie nach Titeln durchsuchen, Status-Filter

### Performance
- Connection Pooling (Singleton-Pattern für Plex)
- Caching (5 Min. Bibliotheken, 1 Min. Statistiken)
- Pagination (20 Einträge pro Seite)

### Neue Dateien
- `notifications.py` - Telegram-Integration
- `.gitignore`
- `CHANGELOG.md`
