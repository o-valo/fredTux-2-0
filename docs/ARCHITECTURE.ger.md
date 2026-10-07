# Architektur und Betriebsgrenzen

> Sprache: Deutsch | [English](ARCHITECTURE.md)

## Komponenten

### `fredtux.config.Config`

Liest die Laufzeitkonfiguration aus Umgebungsvariablen und legt die Datenverzeichnisse
an. `FREDTUX_HOME` ist die einzige zentrale Laufzeitwurzel.

### `fredtux.llm.LLMClient`

Kapselt zwei Rollen:

1. OpenAI-kompatibler Chat-Endpunkt (`/v1/chat/completions`)
2. Native Ollama-Diagnose (`/api/version`, `/api/tags`, `/api/ps`)

Die Diagnose verwendet bewusst die native API, weil sie auch dann Modelle und
Dienstzustand prüfen kann, wenn die OpenAI-kompatible Route nicht erreichbar ist.

### `fredtux.interfaces.api`

Der HTTP-Server stellt `/health`, `/v1/models` und `/v1/chat/completions` bereit. Er
verwendet `AgentCore` unter einem prozessinternen Lock, akzeptiert eine optionale
`session_id` und bindet standardmäßig an `0.0.0.0:8765`. Die virtuelle API-Modell-ID
ist `fredtux-2-0`; `fredtux-2.0` bleibt als Kompatibilitätsalias akzeptiert. Bei
`stream: true` werden OpenAI-SSE-Chunks mit `data: [DONE]` gesendet. Es gibt noch
keine Authentifizierung oder CORS-Policy.

### `fredtux.core.AgentCore`

Hält den Systemprompt, die Nachrichtenhistorie, den Session-Speicher und die
Tool-Registry. Der Systemprompt lädt `CODING_AGENT.md` mit den verbindlichen
Anti-Loop- und Coding-Regeln. Nach einer Tool-Antwort wird die nächste LLM-Anfrage
ausgeführt; die Schleifengrenzen `FREDTUX_MAX_IDLE_ROUNDS` und `FREDTUX_MAX_TOTAL_ROUNDS`
verhindern Endlosschleifen.

### `fredtux.sessions.SessionStore`

Schreibt menschenlesbare Markdown-Dateien. Eine JSON-Sidecar-Datei bewahrt
Tool-Call-IDs und exakte Nachrichtenobjekte. `fcntl.flock` serialisiert Zugriffe
zwischen mehreren lokalen Prozessen.

### `fredtux.tools`

`ToolRegistry` stellt JSON-Schemas für das Modell bereit und dispatcht Aufrufe an
lokale Python-Funktionen. `knowledge.py` implementiert das dateibasierte RAG.
`ShellTools` ergänzt `read_file`, `write_file`, `change_permissions`,
`run_coding_command` und die eingeschränkte Kompatibilitäts-API `execute_command`
mit den Modi `allowlist`, `standard`, `coding` und `yolo`. `run_coding_command`
nimmt strukturierte argv-Schritte entgegen und führt Pipelines ohne `shell=True` aus.
`stdin` wird nur an den ersten Schritt gereicht; danach verbindet FredTux die stdout-
Streams. `stderr` kann als `capture` oder `discard` gesteuert werden. Die Validierung
des Legacy-Strings liegt gekapselt in `fredtux.tools.coding`.
Im normalen Modus wird niemals eine Shell-Zeichenkette interpretiert.

## Datenfluss einer Nachricht

1. CLI nimmt Text und Session-ID entgegen.
2. `AgentCore.ask` fügt die Nutzernachricht an und protokolliert sie.
3. `LLMClient.chat` sendet History plus Tool-Schemas an das Modell.
4. Bei Tool-Call wird das Ergebnis lokal ausgeführt und als Tool-Nachricht gespeichert.
5. Die nächste Modellrunde liefert die sichtbare Antwort; diese wird gespeichert.

## Sicherheitsgrenzen

- Im `allowlist`-/Standardmodus führt der Agent keine beliebigen Shell-Kommandos aus.
- Der `coding`-Modus ist bewusst keine uneingeschränkte YOLO-Shell: nur definierte
  Entwicklungsbefehle, keine Kommando-Substitution, kein Verlassen des Projektbereichs.
- Werkzeugparameter werden als JSON-Objekt validiert.
- Session-IDs werden auf sichere Dateinamen geprüft.
- RAG-Dateien liegen unter `FREDTUX_HOME` und nicht im Repository.
- Ein API-Key wird nur als `Authorization`-Header verwendet, nie ausgegeben.

## Noch nicht implementiert

- authentifizierte Netzwerk-Schnittstelle
- TUI/GUI und fließender Wechsel zwischen Netzwerk-Interfaces
- MCP-/Plugin-Lifecycle
- Dokumenten-/Bild-/Audio-Interfaces
- produktionsreifes Rechtemanagement für Session-Dateien
