# Verbindliche Regeln für den Coding-Agenten

## Arbeitsweise

1. **Vor jeder Coding-Aufgabe** zuerst den aktuellen Projektstand und vorhandene Dateien prüfen.
2. **Bevor ein Tool erstellt wird**, immer `search_knowledge` und anschließend `list_knowledge` verwenden. Wenn ein passendes Tool bereits existiert, muss es wiederverwendet und nicht neu erfunden werden.
3. **Ein Werkzeug pro Schritt:** Keine langen Ketten von Folgeaufrufern erzeugen. Ein Tool-Aufruf, ein Ergebnis, dann die nächste bewusste Aktion.
4. **Bei jeder Fehlermeldung sofort auswerten.** Nicht denselben Aufruf wiederholen. Bei unbekanntem Pfad, falscher URL oder fehlendem Tool eine korrigierte, strukturierte Alternative verwenden.
5. **Nach zwei identischen Werkzeugfehlern oder drei aufeinanderfolgenden Fehlern aufhören** und eine kurze verständliche Fehlermeldung an den Nutzer geben. Keine weiteren Werkzeugschleifen starten.
6. **Keine rohen Shell-Strings als Standard verwenden.** `run_coding_command` mit `program` und `args` ist die bevorzugte API; `execute_command` ist nur die eingeschränkte Kompatibilitäts-API.
7. **Shell-Syntax niemals aus Modellausgaben erraten.** Pipes und Eingaben werden als strukturierte Pipeline-Schritte angegeben. `stdin`, `stderr` und `redirect_stdout` gehören in das jeweilige Schema.
8. **Schreibpfade** auf `FREDTUX_SHELL_WRITE_ROOT` innerhalb des Projekts begrenzen. Niemals `/tmp`, `~/.fredtux-2.0` oder andere externe Pfade als Schreibziel angeben. Ausnahme: Backups gehören nach `~/BACKUP/fredtux-2.0-backups/` (über `FREDTUX_SHELL_EXTRA_ROOTS` freigegeben); `/dev/null` ist als Umleitungsziel erlaubt.
9. **Bestehende Dateien nicht blind überschreiben.** Vor Änderungen lesen, diff/Status prüfen, gezielt schreiben und danach testen.
10. **Nach erfolgreicher Implementierung** genau einen RAG-Eintrag mit `save_knowledge` erstellen. Nicht mehrfach denselben Eintrag speichern.
11. **RAG ist Dokumentation, kein Ausführungsort.** Für Dateien und Skripte immer die Projektdateien verwenden.
12. **Tagesschau:** Der gültige RSS-Feed ist `https://www.tagesschau.de/index~rss2.xml`. Redirects mit `curl -L` folgen; die alte `/rss2/`-URL nicht verwenden.
13. **Nach Aufräumarbeiten** nur kurz das Ergebnis melden. Keine weitere Recherche oder Wiederholung, wenn die Aufgabe erledigt ist.
14. **Regeländerungen sofort wirksam machen:** Nach jeder Änderung an `CODING_AGENT.md` `reload_rules` aufrufen, sonst gelten die neuen Regeln erst in der nächsten Sitzung.
15. **Immer abschließend berichten:** Nach jedem Task eine klare Abschlussmeldung mit Ergebnis, ausgeführten Prüfungen und offenen Punkten senden. Bei Fehlern oder Abbruch immer den konkreten Grund, den letzten Zustand und den nächsten sicheren Schritt nennen; niemals ohne Rückmeldung enden.

## Wichtig

Wenn eine Anweisung bereits erfüllt ist, nicht erneut ausführen. Wenn ein Tool nicht verfügbar ist, nicht raten und nicht in eine Schleife fallen, sondern die konkrete Einschränkung melden.

Diese Datei ist das Regelwerk des Agenten. Wird sie mit `write_file` geändert, lädt `reload_rules` den neuen Stand in die laufende Sitzung.
