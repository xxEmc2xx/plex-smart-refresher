🚀 Plex Smart Refresher (GUI Edition)
Ein leichtgewichtiges, ressourcenschonendes Tool mit Web-Oberfläche, um fehlende Metadaten in Plex (Poster, Zusammenfassungen, GUIDs) zuverlässig zu reparieren.
🧐 Warum dieses Tool?
Der Standard-"Refresh" von Plex hat oft ein Problem: Er sendet den Befehl "Metadaten laden", prüft aber nicht, ob das auch wirklich geklappt hat. Besonders bei API-Timeouts oder langsamen Verbindungen bleiben Filme dann ohne Poster zurück.
Dieses Tool macht es besser:
• Smart-Wait Logik: Es "feuert" nicht nur Befehle ab, sondern wartet geduldig (bis zu 60 Sekunden) und prüft in einer Schleife, ob Plex die Daten erfolgreich geladen hat.
• Kein Docker-Zwang: Läuft nativ ("Bare Metal") auf Linux und verbraucht extrem wenig RAM (~100 MB).
• Web-GUI: Eine moderne, dunkle Oberfläche zur Steuerung – kein Terminal notwendig.
• Gefilterter Scan: Prüft auf Wunsch nur die Inhalte der letzten X Tage, statt die ganze Bibliothek zu scannen.
✨ Features
• 🖥️ Web-Dashboard: Start/Stopp, Live-Protokoll und Statistik im Browser.
• 🔒 Sicherheit: Einfacher Passwortschutz für die Oberfläche.
• 📊 Detaillierte Berichte: Zeigt genau an, welcher Film gefixt wurde und welcher nicht.
• 🧪 Dry Run (Simulation): Teste, was passieren würde, ohne Daten zu ändern.
• ⏰ Zeitplaner: Integrierter Scheduler für automatische nächtliche Scans.
• 🎨 Design: Dark Mode mit goldenen Akzenten (Plex-Style).


🛠️ Installation
Diese Anleitung geht von einem Debian/Ubuntu System aus.
1. Voraussetzungen installieren

sudo apt update
sudo apt install -y python3-venv python3-pip git


2. Projekt klonen & Ordner erstellen

# Ordner erstellen (oder git clone nutzen)
mkdir -p /opt/plex_gui
cd /opt/plex_gui

# (Hier Dateien hinkopieren: app.py, logic.py, requirements.txt, .env)

3. Virtuelle Umgebung einrichten
Wir nutzen eine isolierte Umgebung, um das System sauber zu halten.

python3 -m venv venv
source venv/bin/activate

# Abhängigkeiten installieren
pip install streamlit plexapi python-dotenv requests pandas

4. Konfiguration (.env)
Bearbeite die Datei namens .env im Hauptverzeichnis und passe die Werte an

nano .env

Starten & Autostart
Manueller Start (zum Testen)

source venv/bin/activate
streamlit run app.py --server.port 8501 --server.address 0.0.0.0

Die GUI ist nun erreichbar unter: http://DEINE-IP:8501

Einrichtung als Systemdienst (24/7 Betrieb)
Damit das Tool immer läuft (auch nach Neustart), richten wir einen Systemd-Service ein.
1. Datei erstellen: sudo nano /etc/systemd/system/plexgui.service
2. Inhalt einfügen

Dienst aktivieren und starten:
sudo systemctl daemon-reload
sudo systemctl enable plexgui
sudo systemctl start plexgui

Nutzung
1. Öffne http://DEINE-SERVER-IP:8501 im Browser.
2. Gib dein Passwort ein.
3. Einstellungen (Links):
• Wähle die Bibliotheken (Filme, Serien).
• Stelle den Zeit-Filter ein (z.B. "Nur Filme der letzten 30 Tage").
• Aktiviere bei Bedarf den Zeitplaner für automatische Scans.
4. Scan: Klicke auf "JETZT SCANNEN".
5. Bericht: Nach dem Scan siehst du unten eine Tabelle mit allen gefixten Items.






