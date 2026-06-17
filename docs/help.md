# Gebrauchsanweisung

## Grundmodell

Der Control Explorer geht von einem Standardregelkreis mit Einheitsrueckfuehrung aus. Links werden Parameter, optionaler Vorfilter `V(s)`, Regler `K(s)`, Strecke `G(s)` und Totzeit definiert.

Der offene Kreis fuer Nyquist, Bode und Wurzelortskurve ist `L(s)=K(s)G(s)`. Der Vorfilter wirkt nur auf die Fuehrungsgroesse `w(t)`.

## Eingaben

- Parameter werden im Parameterfeld als Python-Code definiert, zum Beispiel `K_R = 2.0` oder `T_t = 0.16`.
- Die Variable `s` ist bereits als `TransferFunction.s` vorbereitet.
- Uebertragungsfunktionen koennen direkt als Ausdruecke wie `K_R * (1 + 1/(T_I*s))` oder `1/(s**2 + 2*s + 1)` eingegeben werden.

## Aktualisieren und Beispiele

Mit **Aktualisieren** werden alle Darstellungen neu berechnet. Beispiele koennen gespeichert und geladen werden; der Standardordner ist `Control Explorer Examples` im Dokumente-Ordner.

## Nyquist / Ortskurve

Der Tab zeigt wahlweise den offenen Kreis, die Fuehrungsuebertragung oder die Sensitivitaet. Fuer Stabilitaetsbetrachtungen ist meist der offene Kreis mit kritischem Punkt `-1` relevant.

Richtungspfeile koennen in den Einstellungen ueber `omega`-Werte gesetzt werden.

## Frequenzgang / Bode

Bode-Grenzen und Frequenzeinheit werden unter **Einstellungen > Frequenz** gesetzt. Die Totzeit wird im Frequenzbereich exakt als `exp(-j omega T)` beruecksichtigt. Amplituden- und Phasenreserve koennen eingeblendet werden.

## Wurzelortskurve

Die WOK basiert auf dem offenen Kreis ohne Vorfilter. Ein Klick auf die Kurve uebernimmt den passenden Gain in den Parametercode bzw. in den markierten Gain-Parameter.

Mehrfachpole werden mit ihrer Vielfachheit gekennzeichnet. Totzeit kann optional ueber Pade approximiert werden.

## Sprungantwort

Die Sprungantwort nutzt Zeitachse, Sprungfaktor und Pade-Ordnung aus **Einstellungen > Sprung**. Bei aktivem Vorfilter wird fuer die Fuehrungsantwort `V(s)L(s)/(1+L(s))` verwendet.

## Stoeraufschaltung

Die Stoerung greift additiv am Streckeneingang an. Amplitude, Startzeit, optionale Endzeit, Toleranz und Komponentenanzeige liegen unter **Einstellungen > Stoerung**.

Eine leere Endzeit bedeutet, dass die Stoerung bis zum Simulationsende aktiv bleibt.

## Didaktischer Einsatz

Der Explorer soll Rechnen und Visualisieren beschleunigen, ersetzt aber nicht das Verstaendnis. Studierende sollten zu jeder Darstellung formulieren koennen:

- Welcher Uebertragungspfad wird geplottet?
- Welche Annahmen gelten fuer Totzeit und Pade-Approximation?
- Welche Aussage erlaubt der Plot, und welche Aussage erlaubt er nicht?
- Wie wuerde dieselbe Analyse in Matlab nachvollzogen werden?
