# Gebrauchsanweisung

## Grundmodell

Der Control Explorer geht von einem Standardregelkreis mit Einheitsrückführung aus. Links werden Parameter, optionaler Vorfilter `V(s)`, Regler `K(s)`, Strecke `G(s)` und Totzeit definiert.

Der offene Kreis für Nyquist, Bode und Wurzelortskurve ist `L(s)=K(s)G(s)`. Der Vorfilter wirkt nur auf die Führungsgröße `w(t)`.

## Eingaben

- Parameter werden im Parameterfeld als Python-Code definiert, zum Beispiel `K_R = 2.0` oder `T_t = 0.16`.
- Die Variable `s` ist bereits als `TransferFunction.s` vorbereitet.
- Übertragungsfunktionen können direkt als Ausdrücke wie `K_R * (1 + 1/(T_I*s))` oder `1/(s**2 + 2*s + 1)` eingegeben werden.

## Aktualisieren und Beispiele

Mit **Aktualisieren** werden alle Darstellungen neu berechnet. Beispiele können gespeichert und geladen werden; der Standardordner ist `Control Explorer Examples` im Dokumente-Ordner.

Ein Beispiel speichert das Modell und die dazugehörigen Analyseparameter, zum Beispiel Frequenzbereiche, Zeitbereich, Padé-Ordnung, Störsignal und gewählte Systempfade. Reine Anzeige- und Bedienvorlieben wie Grid, Auto-Update, Bode-Einheit oder Dämpfungslinien bleiben globale Programmeinstellungen.

## Nyquist / Ortskurve

Der Tab zeigt wahlweise den offenen Kreis, die Führungsübertragung oder die Sensitivität. Für Stabilitätsbetrachtungen ist meist der offene Kreis mit kritischem Punkt `-1` relevant.

Richtungspfeile können in den Einstellungen über `omega`-Werte gesetzt werden.

## Frequenzgang / Bode

Bode-Grenzen und Frequenzeinheit werden unter **Einstellungen > Frequenz** gesetzt. Die Totzeit wird im Frequenzbereich exakt als `exp(-j omega T)` berücksichtigt. Amplituden- und Phasenreserve können eingeblendet werden.

## Wurzelortskurve

Die WOK basiert auf dem offenen Kreis ohne Vorfilter. Ein Klick auf die Kurve übernimmt den passenden Gain in den Parametercode bzw. in den markierten Gain-Parameter.

Mehrfachpole werden mit ihrer Vielfachheit gekennzeichnet. Totzeit kann optional über Padé approximiert werden.

## Sprungantwort

Die Sprungantwort nutzt Zeitachse, Sprungfaktor und Padé-Ordnung aus **Einstellungen > Sprung**. Bei aktivem Vorfilter wird für die Führungsantwort `V(s)L(s)/(1+L(s))` verwendet.

## Störaufschaltung

Die Störung kann als `d_u` additiv am Streckeneingang oder als `d_y` additiv am Streckenausgang wirken. Amplitude, Startzeit, optionale Endzeit, Toleranz, Störort und Komponentenanzeige liegen unter **Einstellungen > Störung**.

Eine leere Endzeit bedeutet, dass die Störung bis zum Simulationsende aktiv bleibt.

## Didaktischer Einsatz

Der Explorer soll Rechnen und Visualisieren beschleunigen, ersetzt aber nicht das Verständnis. Studierende sollten zu jeder Darstellung formulieren können:

- Welcher Übertragungspfad wird geplottet?
- Welche Annahmen gelten für Totzeit und Padé-Approximation?
- Welche Aussage erlaubt der Plot, und welche Aussage erlaubt er nicht?
- Wie würde dieselbe Analyse in Matlab nachvollzogen werden?
