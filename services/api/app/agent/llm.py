"""Optional LLM client (OpenAI-compatible chat completions).

The demo runs without any key: ``settings.llm_provider`` defaults to
``deterministic`` and the orchestrator then uses the deterministic planner and
narrator. This module is only used when a real provider is configured, or when a
test injects a stub client.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.core.config import Settings


@dataclass
class LLMResponse:
    text: str
    model: str = "unknown"
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    latency_ms: float = 0.0


class LLMClient(Protocol):
    model_name: str

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> LLMResponse: ...


class OpenAICompatibleClient:
    """Minimal chat-completions client. Secrets stay in memory only."""

    def __init__(self, settings: Settings, client: httpx.Client | None = None):
        if not settings.llm_api_key:
            raise ValueError("RCA_LLM_API_KEY is not configured")
        self.settings = settings
        self.model_name = settings.llm_model or "gpt-4o-mini"
        self.base_url = (settings.llm_base_url or "https://api.openai.com/v1").rstrip("/")
        self._client = client or httpx.Client(timeout=settings.llm_timeout_seconds)

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> LLMResponse:
        payload: dict = {
            "model": self.model_name,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "max_tokens": self.settings.llm_max_output_tokens,
            "temperature": 0,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}
        started = time.perf_counter()
        response = self._client.post(
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.settings.llm_api_key}"},
            json=payload,
        )
        response.raise_for_status()
        body = response.json()
        latency_ms = (time.perf_counter() - started) * 1000.0
        usage = body.get("usage", {})
        return LLMResponse(
            text=body["choices"][0]["message"]["content"] or "",
            model=body.get("model", self.model_name),
            prompt_tokens=usage.get("prompt_tokens"),
            completion_tokens=usage.get("completion_tokens"),
            latency_ms=latency_ms,
        )


class StubLLMClient:
    """Deterministic offline client used by the evaluation suite.

    It returns whatever payload it was constructed with, which lets the tests
    drive both a well-behaved and a misbehaving "model".
    """

    def __init__(self, responses: list[str], model_name: str = "stub-llm"):
        self._responses = list(responses)
        self.model_name = model_name
        self.calls: list[dict] = []

    def complete(self, system: str, user: str, *, json_mode: bool = False) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "json_mode": json_mode})
        if not self._responses:
            raise RuntimeError("stub LLM has no queued response")
        return LLMResponse(text=self._responses.pop(0), model=self.model_name, latency_ms=1.0)


def build_llm_client(settings: Settings) -> LLMClient | None:
    """Return a live client only when a real provider is configured."""
    provider = (settings.llm_provider or "deterministic").lower()
    if provider in {"deterministic", "none", "local"}:
        return None
    if not settings.llm_api_key:
        return None
    try:
        return OpenAICompatibleClient(settings)
    except ValueError:
        return None


def parse_json_object(text: str) -> dict:
    """Tolerate fenced or chatty JSON responses."""
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.strip("`")
        if stripped.lower().startswith("json"):
            stripped = stripped[4:]
    start = stripped.find("{")
    end = stripped.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found in the model response")
    return json.loads(stripped[start : end + 1])
