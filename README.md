# Control Explorer

Desktop-GUI zur Untersuchung eines SISO-Standardregelkreises mit optionalem Vorfilter, getrennt definierbarem Regler `K(s)` und Strecke `G(s)`, Nyquist-Ortskurve, Bode-Diagramm, Wurzelortskurve, Sprungantwort, Stoeraufschaltung und `python-control` SISO Tool.

Der linke Eingabebereich zeigt den Regelkreis als Blockdiagramm. Vorfilter und Regler koennen einzeln aktiviert oder deaktiviert werden; die Strecke bleibt das zentrale Anlagenmodell. Frequenz- und Stabilitaetsplots verwenden den offenen Kreis `L(s)=K(s)G(s)`, waehrend Sprungantwort und Fuehrungsfrequenzgang bei aktivem Vorfilter `Y(s)/W(s)=V(s)L(s)/(1+L(s))` auswerten.

Der Tab `Stoeraufschaltung` simuliert eine additive Stoerung am Streckeneingang. Angezeigt werden Ausgang `y(t)`, Reglerausgang `u_R(t)`, Stoersignal `d(t)` und der resultierende Streckeneingang `u(t)` inklusive einer einfachen Ausregelzeit-Schaetzung nach dem Stoersprung.

Die Wurzelortskurve zeigt die geschlossenen Pole von `1 + K L_0(s) = 0` fuer einen einstellbaren Verstaerkungsbereich, wobei `L_0(s)` der offene Kreis ohne den gerade markierten WOK-Gain ist. Richtungspfeile, offene Pole und Nullstellen, markierte geschlossene Pole fuer den ausgewaehlten Gain, Stabilitaetsauswertung, Hover-Daten, Daempfungslinien und eine optionale Pade-Approximation der Totzeit sind integriert. Ein Modellhinweis zeigt direkt im Plot, ob eine vorhandene Totzeit ignoriert oder mit welcher Pade-Ordnung sie approximiert wird. Ein Klick auf die Wurzelortskurve uebernimmt den gewaehlten Gain in den erkannten Verstaerkungsparameter des Parametercodes und aktualisiert damit alle Darstellungen.

## Direkt aus Python starten

```powershell
python control_explorer_gui.py
```

Benoetigte Laufzeitpakete stehen in `requirements-build.txt`. PyInstaller wird nur fuer das Erzeugen der eigenstaendigen Windows- oder Linux-Anwendung benoetigt.

## Windows-Anwendung bauen

Voraussetzungen auf dem Build-Rechner:

- Windows 10 oder 11
- Python 3.13
- Internetzugang fuer die einmalige Installation der Build-Pakete

Im Projektverzeichnis ausfuehren:

```powershell
PowerShell -ExecutionPolicy Bypass -File .\build_windows.ps1
```

Das Skript:

1. erstellt die isolierte Umgebung `.venv-build`,
2. installiert die festgelegten Abhaengigkeiten,
3. baut die Anwendung mit PyInstaller,
4. schreibt das Ergebnis nach `dist\ControlExplorer`.

Die fertige Anwendung liegt unter:

```text
dist\ControlExplorer\ControlExplorer.exe
```

Zum Verteilen muss der **gesamte Ordner** `dist\ControlExplorer` als ZIP-Datei weitergegeben werden. Auf dem Zielrechner sind weder Python noch die Python-Pakete erforderlich.

## Linux-Anwendung bauen

Voraussetzungen auf dem Build-Rechner:

- Linux-System mit Python 3.12 oder kompatibler Python-Version
- `python3-venv` fuer virtuelle Umgebungen
- Internetzugang fuer die einmalige Installation der Build-Pakete

Falls `python3-venv` noch fehlt, kann es unter Ubuntu/Debian zum Beispiel so installiert werden:

```bash
sudo apt update
sudo apt install python3-venv
```

Im Projektverzeichnis eine isolierte Build-Umgebung erstellen und aktivieren:

```bash
python3 -m venv .venv-build-linux
source .venv-build-linux/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements-build.txt
```

Danach den Linux-Build mit PyInstaller erzeugen:

```bash
rm -rf build dist ControlExplorer.spec

python -m PyInstaller --noconfirm --clean --onedir \
  --name ControlExplorer \
  --add-data "control_explorer_icon.png:." \
  --collect-all control \
  --hidden-import=PIL.ImageTk \
  --hidden-import=PIL._tkinter_finder \
  control_explorer_gui.py
```

Die fertige Linux-Anwendung liegt anschliessend unter:

```text
dist/ControlExplorer/ControlExplorer
```

Gestartet wird sie aus dem Projektverzeichnis mit:

```bash
./dist/ControlExplorer/ControlExplorer
```

Zum Verteilen muss der **gesamte Ordner** `dist/ControlExplorer` weitergegeben werden. Auf dem Zielsystem sind weder Python noch die Python-Pakete erforderlich, solange die Zielumgebung zur Build-Umgebung kompatibel ist.

### Linux-App-Menueintrag erzeugen

Damit Control Explorer unter Linux wie ein normales Programm im App-Menue erscheint, kann eine `.desktop`-Datei erzeugt werden. Die folgenden Befehle legen sie fuer den aktuellen Benutzer unter `~/.local/share/applications` an:

```bash
APP_DIR="$(pwd)/dist/ControlExplorer"
EXEC_PATH="$APP_DIR/ControlExplorer"
ICON_PATH="$APP_DIR/control_explorer_icon.png"
DESKTOP_FILE="$HOME/.local/share/applications/control-explorer.desktop"

mkdir -p "$HOME/.local/share/applications"
chmod +x "$EXEC_PATH"

cat > "$DESKTOP_FILE" <<DESKTOP_EOF
[Desktop Entry]
Type=Application
Name=Control Explorer
Comment=Interactive control systems explorer
Exec=$EXEC_PATH
Icon=$ICON_PATH
Path=$APP_DIR
Terminal=false
Categories=Education;Science;Engineering;
StartupNotify=true
DESKTOP_EOF

chmod +x "$DESKTOP_FILE"

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$HOME/.local/share/applications" || true
fi
```

Danach sollte `Control Explorer` im App-Menue der Desktop-Umgebung auffindbar sein. Falls der Eintrag nicht sofort erscheint, hilft meistens einmaliges Ab- und Anmelden.

## Warum kein einzelnes EXE-Archiv?

Die Anwendung verwendet grosse wissenschaftliche Bibliotheken wie NumPy, SciPy und Matplotlib. Der `onedir`-Build startet schneller, weil diese Dateien nicht bei jedem Programmstart aus einer einzelnen EXE entpackt werden muessen.

## Benutzerdaten

- Einstellungen: `%APPDATA%\ControlExplorer\settings.json`
- Gespeicherte Beispiele: `Dokumente\Control Explorer Examples`

Diese Dateien liegen ausserhalb des Programmordners und bleiben bei einem Programmupdate erhalten.

## Veroeffentlichung

Vor einer Veroeffentlichung:

1. `dist\ControlExplorer\ControlExplorer.exe` auf einem Windows-Rechner ohne Python testen.
2. `dist/ControlExplorer/ControlExplorer` auf einem Linux-Rechner ohne aktivierte Python-Umgebung testen.
3. Nyquist, Bode, Wurzelortskurve, Sprungantwort, Stoeraufschaltung, Hover, SISO Tool sowie Beispiel-Speichern/Laden pruefen.
4. Den vollstaendigen Ordner als ZIP-Datei veroeffentlichen, beispielsweise ueber GitHub Releases.
5. Fuer eine professionelle oeffentliche Windows-Verteilung die EXE optional digital signieren. Ohne Signatur kann Windows SmartScreen bei unbekannten Downloads warnen.

Windows-Builds muessen unter Windows erstellt werden. Linux-Builds muessen unter Linux erstellt werden. Fuer macOS wird ein eigener Build auf macOS benoetigt.
