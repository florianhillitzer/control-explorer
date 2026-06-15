# Control Explorer

Desktop-GUI zur Untersuchung von SISO-Uebertragungsfunktionen mit Nyquist-Ortskurve, Bode-Diagramm, Wurzelortskurve, Sprungantwort und `python-control` SISO Tool.

Die Wurzelortskurve zeigt die geschlossenen Pole von `1 + K G_0(s) = 0` fuer einen einstellbaren Verstaerkungsbereich. Richtungspfeile, offene Pole und Nullstellen, optional markierbare geschlossene Pole, Stabilitaetsauswertung, Hover-Daten, Daempfungslinien und eine optionale Pade-Approximation der Totzeit sind integriert.

## Direkt aus Python starten

```powershell
python control_explorer_gui.py
```

Benoetigte Laufzeitpakete stehen in `requirements-build.txt`. PyInstaller wird nur fuer das Erzeugen der Windows-Anwendung benoetigt.

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

## Warum kein einzelnes EXE-Archiv?

Die Anwendung verwendet grosse wissenschaftliche Bibliotheken wie NumPy, SciPy und Matplotlib. Der `onedir`-Build startet schneller, weil diese Dateien nicht bei jedem Programmstart aus einer einzelnen EXE entpackt werden muessen.

## Benutzerdaten

- Einstellungen: `%APPDATA%\ControlExplorer\settings.json`
- Gespeicherte Beispiele der gebauten Anwendung: `Dokumente\Control Explorer Examples`

Diese Dateien liegen ausserhalb des Programmordners und bleiben bei einem Programmupdate erhalten.

## Veroeffentlichung

Vor einer Veroeffentlichung:

1. `dist\ControlExplorer\ControlExplorer.exe` auf einem Windows-Rechner ohne Python testen.
2. Nyquist, Bode, Wurzelortskurve, Sprungantwort, Hover, SISO Tool sowie Beispiel-Speichern/Laden pruefen.
3. Den vollstaendigen Ordner als ZIP-Datei veroeffentlichen, beispielsweise ueber GitHub Releases.
4. Fuer eine professionelle oeffentliche Verteilung die EXE optional digital signieren. Ohne Signatur kann Windows SmartScreen bei unbekannten Downloads warnen.

Windows-Builds muessen unter Windows erstellt werden. Fuer macOS oder Linux wird jeweils ein eigener Build auf dem entsprechenden Betriebssystem benoetigt.
