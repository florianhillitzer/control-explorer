# Gebrauchsanweisung

## Grundmodell

Der Control Explorer geht von einem Standardregelkreis mit Einheitsrückführung aus. Links werden Parameter, optionaler Vorfilter `V(s)`, Regler `K(s)`, Strecke `G(s)` und Totzeit definiert.

Der offene Kreis für Nyquist, Bode und Wurzelortskurve ist `L(s)=K(s)G(s)`. Der Vorfilter wirkt nur auf die Führungsgröße `w(t)` und damit auf Führungsfrequenzgang und Sprungantwort.

## Eingaben

- Parameter werden im Parameterfeld als Python-Code definiert, zum Beispiel `K_R = 2.0` oder `T_t = 0.16`.
- Die Variable `s` ist bereits als `ct.TransferFunction.s` vorbereitet.
- Übertragungsfunktionen können direkt als Ausdrücke wie `K_R * (1 + 1/(T_I*s))` oder `1/(s**2 + 2*s + 1)` eingegeben werden.
- Mathematische Funktionen aus `numpy` stehen über `np` zur Verfügung.
- Häufige Konstanten können direkt verwendet werden, zum Beispiel `pi`, `Pi`, `PI`, `tau`, `e`, `E`, `inf` und `nan`.

## Aktualisieren und Beispiele

Mit **Aktualisieren** werden die Darstellungen für den aktiven Tab neu berechnet. Bei aktivem Auto-Update geschieht das nach Eingabeänderungen automatisch verzögert.

Beispiele können über **Datei > Beispiel laden...** und **Datei > Beispiel speichern...** geöffnet oder abgelegt werden; der Standardordner ist `Control Explorer Examples` im Dokumente-Ordner. Ein Beispiel speichert das Modell und die dazugehörigen Analyseparameter, zum Beispiel Frequenzbereiche, Zeitbereich, Padé-Ordnung, Störsignal und gewählte Systempfade. Reine Anzeige- und Bedienvorlieben wie Grid, Auto-Update, Bode-Einheit oder Dämpfungslinien bleiben globale Programmeinstellungen.

Über **Datei > Als MATLAB-Skript exportieren...** kann das aktuelle Modell als `.m`-Datei exportiert werden. Das erzeugte Skript verwendet numerische `tf(...)`-Modelle und rekonstruiert Nyquist-Ortskurve, Bode-Diagramm, Wurzelortskurve, Sprungantwort und Störaufschaltung in MATLAB mit der Control System Toolbox.

## Hover und Zoom

Alle Analyseplots besitzen Hover-Informationen zum nächstliegenden Kurvenpunkt. Die Werkzeugleiste stellt die üblichen Matplotlib-Funktionen sowie eigene Zoom-In- und Zoom-Out-Schaltflächen bereit. Während Pan, Zoom oder Scroll-Interaktion aktiv ist, werden Hover-Markierungen ausgeblendet und anschließend wieder neu berechnet.

## Nyquist / Ortskurve

Der Tab zeigt wahlweise den offenen Kreis, die Führungsübertragung oder die Sensitivität. Für Stabilitätsbetrachtungen ist meist der offene Kreis mit kritischem Punkt `-1` relevant.

Richtungspfeile können unter **Einstellungen > Nyquist / Ortskurve** über `omega`-Werte gesetzt werden. Der normierte Ortskurvenmodus blendet Zahlen und Raster bewusst aus und eignet sich für eine reduzierte qualitative Darstellung.

## Frequenzgang / Bode

Bode-Grenzen und Frequenzeinheit werden unter **Einstellungen > Frequenz / Bode** gesetzt. Die Totzeit wird im Frequenzbereich exakt als `exp(-j omega T)` berücksichtigt. Amplituden- und Phasenreserve können im Bode-Tab eingeblendet werden.

Je nach Tab-Auswahl kann der offene Kreis, die Führungsübertragung oder die Sensitivität angezeigt werden.

## Wurzelortskurve

Die WOK basiert auf dem offenen Kreis ohne Vorfilter und verwendet den separaten Verstärkungsfaktor `K_WOK`. Für die Kurve wird `L_0(s)` mit `K_WOK = 1` gebildet; geplottet werden die geschlossenen Pole von `1 + K L_0(s) = 0`.

Falls `K_WOK` im Modell fehlt, fragt der Explorer, ob `K_WOK = 1` zum Parametercode ergänzt und als Faktor vor den Regler gesetzt werden soll. Der markierte Entwurfswert wird oben im WOK-Tab angezeigt. Er kann direkt eingegeben und mit Enter übernommen werden. Alternativ kann eine Stelle auf der WOK angeklickt werden; der passende Gain wird dann übernommen.

Unter **Einstellungen > Wurzelortskurve** werden Verstärkungsbereich, Anzahl der Punkte, logarithmische Abtastung, gleiche Achsenskalierung, Dämpfungslinien und die optionale Padé-Berücksichtigung der Totzeit eingestellt.

Mehrfachpole werden mit ihrer Vielfachheit gekennzeichnet. Offene Pole und Nullstellen, Richtungspfeile, der markierte Entwurfswert, Stabilitätshinweise und Hover-Daten sind direkt im Plot verfügbar.

## Sprungantwort

Die Sprungantwort nutzt Zeitachse, Sprungfaktor und Padé-Ordnung aus **Einstellungen > Sprungantwort**. Bei aktivem Vorfilter wird für die Führungsantwort `V(s)L(s)/(1+L(s))` verwendet.

Der Hover zeigt Zeitwert, Ausgang und Eingangssignal am nächstliegenden Punkt.

## Störaufschaltung

Die Störung kann als `d_u` additiv am Streckeneingang oder als `d_y` additiv am Streckenausgang wirken. Amplitude, Startzeit, optionale Endzeit, Toleranz, Störort und Komponentenanzeige liegen unter **Einstellungen > Störaufschaltung**.

Eine leere Endzeit bedeutet, dass die Störung bis zum Simulationsende aktiv bleibt. Angezeigt werden Ausgang `y(t)`, Reglerausgang `u_R(t)`, Störsignal und der resultierende Streckeneingang `u(t)`.

Wenn das Simulationsfenster zu kurz ist, um eine dauerhafte Rückkehr in die Toleranz zu belegen, wird die Ausregelzeit als undefiniert markiert. In diesem Fall sollte `t_max` erhöht oder die Zeitauflösung vergrößert werden.

## Hilfe und Lizenz

Die Einträge **Hilfe** und **Über / Lizenz** im Menü öffnen die mitgelieferten Markdown-Dokumente aus dem Ordner `docs`. In gebauten Paketen müssen `docs`, `VERSION`, `LICENSE`, `NOTICE`, die Logo-Dateien und die Toolbar-Icons mit ausgeliefert werden.

## Didaktischer Einsatz

Der Explorer soll Rechnen und Visualisieren beschleunigen, ersetzt aber nicht das Verständnis. Studierende sollten zu jeder Darstellung formulieren können:

- Welcher Übertragungspfad wird geplottet?
- Welche Annahmen gelten für Totzeit und Padé-Approximation?
- Welche Aussage erlaubt der Plot, und welche Aussage erlaubt er nicht?
- Wie würde dieselbe Analyse in Matlab oder Python-Control nachvollzogen werden?
