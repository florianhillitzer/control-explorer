# Control Explorer

Desktop-GUI zur Untersuchung eines SISO-Standardregelkreises mit optionalem Vorfilter, getrennt definierbarem Regler `K(s)` und Strecke `G(s)`, Nyquist-Ortskurve, Bode-Diagramm, Wurzelortskurve, Sprungantwort und Störaufschaltung.

Der linke Eingabebereich zeigt den Regelkreis als Blockdiagramm. Vorfilter und Regler können einzeln aktiviert oder deaktiviert werden; die Strecke bleibt das zentrale Anlagenmodell. Frequenz- und Stabilitätsplots verwenden den offenen Kreis `L(s)=K(s)G(s)`, während Sprungantwort und Führungsfrequenzgang bei aktivem Vorfilter `Y(s)/W(s)=V(s)L(s)/(1+L(s))` auswerten.

Der Tab `Störaufschaltung` simuliert eine additive Störung wahlweise als `d_u` am Streckeneingang oder als `d_y` am Streckenausgang. Amplitude, Startzeit, Ausregel-Toleranz, Störort und Komponentenanzeige liegen unter `Einstellungen > Störung`. Angezeigt werden Ausgang `y(t)`, Reglerausgang `u_R(t)`, Störsignal und der resultierende Streckeneingang `u(t)` inklusive einer einfachen Ausregelzeit-Schätzung nach dem Störsprung.

Die Wurzelortskurve zeigt die geschlossenen Pole von `1 + K_WOK L_0(s) = 0` für einen einstellbaren Verstärkungsbereich, wobei `L_0(s)` der offene Kreis mit `K_WOK = 1` ist. Richtungspfeile, offene Pole und Nullstellen, markierte geschlossene Pole für den ausgewählten Gain, Stabilitätsauswertung, Hover-Daten, Dämpfungslinien und eine optionale Padé-Approximation der Totzeit sind integriert. Fehlt `K_WOK`, fragt der Explorer, ob der Faktor ergänzt werden soll. Der markierte Entwurfswert kann im WOK-Tab eingegeben und mit Enter übernommen oder durch Klick auf die WOK ausgewählt werden.

## Direkt aus Python starten

```powershell
python control_explorer_gui.py
```

Benötigte Laufzeitpakete stehen in `requirements-build.txt`. PyInstaller wird nur für das Erzeugen einer eigenständigen Windows- oder Linux-Anwendung benötigt.

## Projektdateien

Wichtige Dateien, die beim Paketieren mit ausgeliefert werden:

- `control_explorer_gui.py`: Hauptprogramm
- `control_explorer.spec`: gemeinsamer PyInstaller-Build für Windows und Linux
- `control_explorer_icon.png` und `control_explorer.ico`: Programmicon
- `mrm_logo.png`: Logo für Hilfe-/Lizenzfenster
- `toolbar_icons/`: eigene Toolbar-Icons für Zoom-Schaltflächen
- `docs/help.md` und `docs/legal.md`: Gebrauchsanweisung und Lizenz-/Hinweistext
- `VERSION`, `LICENSE`, `NOTICE`: Versions- und Lizenzinformationen

Die Datei `control_explorer.spec` ist der maßgebliche Build-Einstieg. Sie bündelt neben den Python-Paketen auch Bilder, Logos, Toolbar-Icons, Dokumentation und Lizenzdateien.

## Windows-Anwendung bauen

Voraussetzungen auf dem Build-Rechner:

- Windows 10 oder 11
- Python 3.13
- Internetzugang für die einmalige Installation der Build-Pakete

Im Projektverzeichnis ausführen:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

Das Skript:

1. erstellt die isolierte Umgebung `.venv-build`,
2. installiert die festgelegten Abhängigkeiten,
3. baut die Anwendung mit PyInstaller und `control_explorer.spec`,
4. schreibt das Ergebnis nach `dist\ControlExplorer`.

Die fertige Anwendung liegt unter:

```text
dist\ControlExplorer\ControlExplorer.exe
```

Zum Verteilen muss der gesamte Ordner `dist\ControlExplorer` als ZIP-Datei weitergegeben werden. Auf dem Zielrechner sind weder Python noch die Python-Pakete erforderlich.

## Linux-Anwendung bauen

Voraussetzungen auf dem Build-Rechner:

- Linux-System mit Python 3.12 oder kompatibler Python-Version
- `python3-venv` für virtuelle Umgebungen
- Internetzugang für die einmalige Installation der Build-Pakete

Falls `python3-venv` noch fehlt, kann es unter Ubuntu/Debian zum Beispiel so installiert werden:

```bash
sudo apt update
sudo apt install python3-venv
```

Im Projektverzeichnis ausführen:

```bash
chmod +x ./build_linux.sh
./build_linux.sh
```

Das Skript:

1. erstellt die isolierte Umgebung `.venv-build-linux`,
2. installiert die festgelegten Abhängigkeiten,
3. baut die Anwendung mit PyInstaller und `control_explorer.spec`,
4. schreibt das Ergebnis nach `dist/ControlExplorer`.

Alternativ kann derselbe Build ohne Skript manuell ausgeführt werden:

```bash
python3 -m venv .venv-build-linux
.venv-build-linux/bin/python -m pip install --upgrade pip
.venv-build-linux/bin/python -m pip install -r requirements-build.txt
.venv-build-linux/bin/python -m PyInstaller --noconfirm --clean control_explorer.spec
```

Die fertige Linux-Anwendung liegt anschließend unter:

```text
dist/ControlExplorer/ControlExplorer
```

Gestartet wird sie mit:

```bash
./dist/ControlExplorer/ControlExplorer
```

Zum Verteilen muss der gesamte Ordner `dist/ControlExplorer` weitergegeben werden. Auf dem Zielsystem sind weder Python noch die Python-Pakete erforderlich, solange die Zielumgebung zur Build-Umgebung kompatibel ist.

### Linux-App-Menüeintrag erzeugen

Damit Control Explorer unter Linux wie ein normales Programm im App-Menü erscheint, kann eine `.desktop`-Datei erzeugt werden. Die folgenden Befehle legen sie für den aktuellen Benutzer unter `~/.local/share/applications` an:

```bash
APP_DIR="$(pwd)/dist/ControlExplorer"
EXEC_PATH="$APP_DIR/ControlExplorer"
ICON_SOURCE="$APP_DIR/_internal/control_explorer_icon.png"
ICON_TARGET="$HOME/.local/share/icons/hicolor/256x256/apps/control-explorer.png"
DESKTOP_FILE="$HOME/.local/share/applications/control-explorer.desktop"

mkdir -p "$HOME/.local/share/applications"
mkdir -p "$(dirname "$ICON_TARGET")"
chmod +x "$EXEC_PATH"
cp "$ICON_SOURCE" "$ICON_TARGET"

cat > "$DESKTOP_FILE" <<DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Control Explorer
Comment=Interactive control systems explorer
Exec=$EXEC_PATH
Icon=control-explorer
Path=$APP_DIR
Terminal=false
Categories=Education;Science;Engineering;
StartupNotify=true
StartupWMClass=ControlExplorer
DESKTOP_EOF

chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" || true
fi

if command -v gtk-update-icon-cache >/dev/null 2>&1; then
    gtk-update-icon-cache "$HOME/.local/share/icons/hicolor" || true
fi
```

Danach sollte `Control Explorer` im App-Menü der Desktop-Umgebung auffindbar sein. Falls der Eintrag oder das Icon nicht sofort erscheint, hilft meistens einmaliges Ab- und Anmelden. Für ein korrektes Taskleisten-Icon sollte die Anwendung über diesen Menüeintrag gestartet werden; der Desktop verknüpft das laufende Tk-Fenster über `StartupWMClass=ControlExplorer` mit dem installierten Icon.

## Warum kein einzelnes EXE-Archiv?

Die Anwendung verwendet große wissenschaftliche Bibliotheken wie NumPy, SciPy und Matplotlib. Der `onedir`-Build startet schneller, weil diese Dateien nicht bei jedem Programmstart aus einer einzelnen EXE entpackt werden müssen.

## Benutzerdaten

- Einstellungen: `%APPDATA%\ControlExplorer\settings.json` unter Windows, sonst `~/ControlExplorer/settings.json`
- Gespeicherte Beispiele: `Dokumente\Control Explorer Examples` beziehungsweise `~/Documents/Control Explorer Examples`

Diese Dateien liegen außerhalb des Programmordners und bleiben bei einem Programmupdate erhalten. Globale Anzeige- und Bedienvorlieben werden in `settings.json` gespeichert; Beispiele enthalten nur Modell- und Analyseparameter.

## Veröffentlichung

Vor einer Veröffentlichung:

1. `dist\ControlExplorer\ControlExplorer.exe` auf einem Windows-Rechner ohne Python testen.
2. `dist/ControlExplorer/ControlExplorer` auf einem Linux-Rechner ohne aktivierte Python-Umgebung testen.
3. Nyquist, Bode, Wurzelortskurve, Sprungantwort, Störaufschaltung, Hover sowie Beispiel-Speichern/Laden prüfen.
4. Prüfen, dass `docs`, `toolbar_icons`, `control_explorer_icon.png`, `mrm_logo.png`, `VERSION`, `LICENSE` und `NOTICE` im Build-Ordner unter `_internal` vorhanden sind.
5. Den vollständigen Ordner als ZIP- oder Tar-Archiv veröffentlichen, beispielsweise über GitHub Releases.
6. Für eine professionelle öffentliche Windows-Verteilung die EXE optional digital signieren. Ohne Signatur kann Windows SmartScreen bei unbekannten Downloads warnen.

Windows-Builds müssen unter Windows erstellt werden. Linux-Builds müssen unter Linux erstellt werden. Für macOS wird ein eigener Build auf macOS benötigt.
