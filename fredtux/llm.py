"""Small OpenAI-compatible chat-completions client."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Iterator

from .config import Config


class LLMError(RuntimeError):
    """Raised when the configured model endpoint cannot answer."""


REASONING_FIELDS = ("reasoning_content", "reasoning", "thinking")


def _reasoning_of(message: dict[str, Any]) -> str:
    """Holt die Denkausgabe aus einer Nachricht, egal wie der Server sie nennt."""
    for feld in REASONING_FIELDS:
        wert = message.get(feld)
        if isinstance(wert, str) and wert:
            return wert
        if isinstance(wert, list):  # manche Server schicken Blöcke statt Text
            teile = [str(t.get("text", "")) if isinstance(t, dict) else str(t) for t in wert]
            zusammen = "".join(teile)
            if zusammen:
                return zusammen
    return ""


class OllamaError(RuntimeError):
    """Raised when the local Ollama installation cannot be verified."""


@dataclass(frozen=True)
class OllamaStatus:
    url: str
    version: str
    model: str
    installed_models: tuple[str, ...]
    loaded_models: tuple[str, ...]

    def summary(self) -> str:
        loaded = ", ".join(self.loaded_models) if self.loaded_models else "kein Modell geladen"
        return f"Ollama {self.version} unter {self.url}; Modell {self.model} verfügbar; geladen: {loaded}"


@dataclass
class LLMClient:
    config: Config

    def check_ollama(self) -> OllamaStatus:
        """Prüft den lokalen Ollama-Dienst und das konfigurierte Modell.

        Die Prüfung nutzt bewusst die native Ollama-API aus der Freebuff-Doku:
        /api/version, /api/tags und /api/ps. Dadurch funktioniert sie auch,
        wenn die OpenAI-kompatible /v1-Schnittstelle nicht verfügbar ist.
        """
        version_data = self._ollama_get("/api/version")
        version = version_data.get("version")
        if not isinstance(version, str) or not version:
            raise OllamaError(f"Ungültige Antwort von {self.config.ollama_url}/api/version: kein Versionsfeld.")

        tags_data = self._ollama_get("/api/tags")
        installed = self._model_names(tags_data, "/api/tags")
        if not installed:
            raise OllamaError(
                f"Ollama unter {self.config.ollama_url} ist erreichbar, aber es sind keine Modelle installiert. "
                f"Installiere z. B. mit: OLLAMA_HOST={self.config.ollama_url} ollama pull {self.config.model}"
            )
        if not any(self._matches_model(self.config.model, name) for name in installed):
            available = ", ".join(installed)
            raise OllamaError(
                f"Das konfigurierte Modell {self.config.model!r} ist auf {self.config.ollama_url} nicht installiert.\n"
                f"Verfügbare Modelle: {available}\n"
                f"Installiere es mit: OLLAMA_HOST={self.config.ollama_url} ollama pull {self.config.model}"
            )

        ps_data = self._ollama_get("/api/ps")
        loaded = self._model_names(ps_data, "/api/ps")
        return OllamaStatus(
            url=self.config.ollama_url,
            version=version,
            model=self.config.model,
            installed_models=tuple(installed),
            loaded_models=tuple(loaded),
        )

    def _ollama_get(self, path: str) -> dict[str, Any]:
        url = f"{self.config.ollama_url}{path}"
        request = urllib.request.Request(url, headers={"Accept": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=self.config.ollama_timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
            if not isinstance(payload, dict):
                raise OllamaError(f"Ungültige Antwort von {url}: JSON-Objekt erwartet.")
            return payload
        except TimeoutError as exc:
            raise OllamaError(
                f"Zeitüberschreitung bei {url} nach {self.config.ollama_timeout:g} Sekunden. "
                "Der Ollama-Dienst ist erreichbar, antwortet aber nicht rechtzeitig genug."
            ) from exc
        except urllib.error.HTTPError as exc:
            raise OllamaError(f"HTTP-Fehler {exc.code} von {url}.") from exc
        except urllib.error.URLError as exc:
            reason = getattr(exc, "reason", exc)
            raise OllamaError(
                f"Ollama ist unter {self.config.ollama_url} nicht erreichbar ({reason}).\n"
                "Prüfe Netzwerk/SSH und den Ollama-Dienst auf dem Zielknoten."
            ) from exc
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise OllamaError(f"Ungültige JSON-Antwort von {url}: {exc}.") from exc
        except OSError as exc:
            raise OllamaError(f"Verbindung zu {url} fehlgeschlagen: {exc}.") from exc

    @staticmethod
    def _model_names(data: dict[str, Any], endpoint: str) -> list[str]:
        models = data.get("models")
        if not isinstance(models, list):
            raise OllamaError(f"Ungültige Antwort von Ollama /{endpoint.lstrip('/')}: models fehlt.")
        names = [item.get("name") for item in models if isinstance(item, dict) and isinstance(item.get("name"), str)]
        return names

    @staticmethod
    def _matches_model(configured: str, installed: str) -> bool:
        if ":" in configured:
            return configured == installed
        return configured == installed.split(":", 1)[0] or configured == installed


    def check_chat_endpoint(self, timeout: float = 10.0) -> str:
        """Prüft beim Start, ob unter base_url überhaupt ein Dienst antwortet.

        Abgefragt wird nur /models: Das kostet keine Rechenzeit und lädt kein
        Modell. Ein HTTP-Fehler (z. B. 404) belegt, dass der Dienst erreichbar
        ist – abgebrochen wird nur bei Verbindungsfehlern. Genau dieser Fall
        (config.nd zeigt auf einen Rechner ohne Modellserver) kostete bisher
        erst bei der ersten Eingabe Zeit.
        """
        url = f"{self.config.base_url}/models"
        request = urllib.request.Request(
            url, headers={"Accept": "application/json", **self._auth_header()}
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout):
                return f"Chat-Endpunkt erreichbar: {self.config.base_url}"
        except urllib.error.HTTPError:
            return f"Chat-Endpunkt erreichbar: {self.config.base_url} (ohne /models-Liste)"
        except TimeoutError as exc:
            raise LLMError(self._timeout_message(url, timeout)) from exc
        except urllib.error.URLError as exc:
            raise LLMError(self._unreachable_message(self.config.base_url, exc)) from exc
        except OSError as exc:
            raise LLMError(f"Verbindung zu {self.config.base_url} fehlgeschlagen: {exc}") from exc

    def _payload_options(self) -> dict[str, Any]:
        """Gibt serverseitige Inferenz-Optionen mit, falls konfiguriert.

        Ohne num_ctx nutzt Ollama seinen eigenen Default (oft 32k), wodurch
        längere Sessions mit HTTP 400 'exceeds the available context size'
        abbrechen. FREDTUX_NUM_CTX > 0 hebt das serverseitige Limit an.
        """
        if self.config.num_ctx <= 0:
            return {}
        return {"options": {"num_ctx": self.config.num_ctx}}

    def chat(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": False,
            **self._payload_options(),
        }
        if tools:
            payload["tools"] = tools
        url = f"{self.config.base_url}/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **self._auth_header()},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
            message = result["choices"][0]["message"]
            return {
                "content": message.get("content") or "",
                "reasoning": _reasoning_of(message),
                "tool_calls": message.get("tool_calls", []),
            }
        except urllib.error.HTTPError as exc:
            raise LLMError(self._http_message(url, exc)) from exc
        except TimeoutError as exc:
            raise LLMError(self._timeout_message(url, self.config.request_timeout)) from exc
        except urllib.error.URLError as exc:
            raise LLMError(self._unreachable_message(self.config.base_url, exc)) from exc
        except OSError as exc:
            raise LLMError(f"Verbindung zu {url} fehlgeschlagen: {exc}") from exc
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMError(f"Ungültige Antwort von {url}: {exc}") from exc

    def chat_stream(
        self, messages: list[dict[str, Any]], tools: list[dict[str, Any]] | None = None
    ) -> Iterator[dict[str, Any]]:
        """Liest OpenAI-SSE-Chunks und liefert Inhalt sowie ein Completion-Ende."""
        payload: dict[str, Any] = {
            "model": self.config.model,
            "messages": messages,
            "stream": True,
            **self._payload_options(),
        }
        if tools:
            payload["tools"] = tools
        url = f"{self.config.base_url}/chat/completions"
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json", **self._auth_header()},
            method="POST",
        )
        content_parts: list[str] = []
        tool_calls: dict[int, dict[str, Any]] = {}
        try:
            with urllib.request.urlopen(request, timeout=self.config.request_timeout) as response:
                for raw_line in response:
                    line = raw_line.decode("utf-8").strip()
                    if not line or not line.startswith("data:"):
                        continue
                    data = line[5:].strip()
                    if data == "[DONE]":
                        break
                    event = json.loads(data)
                    if "error" in event:
                        raise LLMError(f"Upstream-Streaming-Fehler: {event['error']}")
                    choices = event.get("choices", [])
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    # Denkausgabe zuerst: Modelle mit Reasoning (z. B. Qwen3 mit
                    # aktiviertem Denken) schicken sie unter reasoning_content,
                    # manche Server unter reasoning oder thinking. Sie wird
                    # mitgereicht, damit man dem Lauf zusehen kann.
                    reasoning = _reasoning_of(delta)
                    if reasoning:
                        yield {"type": "reasoning", "content": reasoning}
                    content = delta.get("content")
                    if content:
                        content_parts.append(str(content))
                        yield {"type": "content", "content": str(content)}
                    for call in delta.get("tool_calls", []):
                        index = call.get("index", 0)
                        item = tool_calls.setdefault(
                            index,
                            {"id": "", "type": "function", "function": {"name": "", "arguments": ""}},
                        )
                        if call.get("id"):
                            item["id"] = call["id"]
                        function = call.get("function") or {}
                        if function.get("name"):
                            item["function"]["name"] += function["name"]
                        if function.get("arguments"):
                            item["function"]["arguments"] += function["arguments"]
            yield {
                "type": "complete",
                "content": "".join(content_parts),
                "tool_calls": list(tool_calls.values()),
            }
        except urllib.error.HTTPError as exc:
            raise LLMError(self._http_message(url, exc)) from exc
        except TimeoutError as exc:
            raise LLMError(self._timeout_message(url, self.config.request_timeout)) from exc
        except urllib.error.URLError as exc:
            raise LLMError(self._unreachable_message(self.config.base_url, exc)) from exc
        except OSError as exc:
            raise LLMError(f"Verbindung zu {url} fehlgeschlagen: {exc}") from exc
        except (KeyError, IndexError, json.JSONDecodeError) as exc:
            raise LLMError(f"Ungültige Antwort von {url}: {exc}") from exc

    def _auth_header(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.config.api_key}"} if self.config.api_key else {}

    def _http_message(self, url: str, exc: urllib.error.HTTPError) -> str:
        return f"LLM-Endpunkt {url} antwortete mit HTTP {exc.code}{self._http_detail(exc)}"

    @staticmethod
    def _http_detail(exc: urllib.error.HTTPError) -> str:
        """Hängt die Fehlermeldung des Servers an (z. B. Ollamas 'model not found')."""
        try:
            body = exc.read().decode("utf-8", "replace").strip()
        except Exception:  # Der Body ist nur eine Zugabe, nie ein Abbruchgrund.
            return ""
        return f": {body[:200]}" if body else ""

    def _timeout_message(self, url: str, timeout: float) -> str:
        return (
            f"Zeitüberschreitung nach {timeout:g} Sekunden bei {url}. "
            "Beim ersten Aufruf lädt der Server das Modell – große oder kalte Modelle brauchen dann "
            "deutlich länger. Erhöhe in diesem Fall FREDTUX_TIMEOUT in config.nd (z. B. 600) "
            "und prüfe, ob der Modellserver ausgelastet ist."
        )

    def _unreachable_message(self, base_url: str, exc: BaseException) -> str:
        reason = getattr(exc, "reason", exc)
        return (
            f"LLM-Endpunkt {base_url} ist nicht erreichbar ({reason}). "
            f"FREDTUX_BASE_URL in config.nd zeigt auf {base_url} – dort muss ein OpenAI-kompatibler "
            "Dienst laufen (bei Ollama: OLLAMA_HOST=0.0.0.0 und passender Port). "
            "Zeigt der Wert auf den falschen Rechner, korrigiere ihn; "
            "mit --no-ollama-check lässt sich der Chat ohne Vorprüfung starten."
        )
