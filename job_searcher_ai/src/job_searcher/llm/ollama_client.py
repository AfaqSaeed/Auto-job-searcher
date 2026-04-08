"""Minimal Ollama client wrapper."""

from __future__ import annotations

import json
from typing import Any

import requests

from job_searcher.config import OllamaSettings


class OllamaClientError(RuntimeError):
    """Raised when the local Ollama service cannot satisfy a request."""


class OllamaClient:
    """Small wrapper around Ollama's generate endpoint."""

    def __init__(self, settings: OllamaSettings) -> None:
        self.settings = settings
        self.base_url = settings.host.rstrip("/")

    def generate(self, prompt: str, system: str | None = None, json_mode: bool = False) -> str:
        """Generate a response from the configured model."""

        payload: dict[str, Any] = {
            "model": self.settings.model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": self.settings.temperature},
        }
        if system:
            payload["system"] = system
        if json_mode:
            payload["format"] = "json"

        try:
            response = requests.post(
                f"{self.base_url}/api/generate",
                json=payload,
                timeout=self.settings.timeout_seconds,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise OllamaClientError(str(exc)) from exc

        data = response.json()
        return data.get("response", "").strip()

    def generate_json(self, prompt: str, system: str | None = None) -> dict[str, Any]:
        """Generate and parse a JSON response."""

        response = self.generate(prompt=prompt, system=system, json_mode=True)
        try:
            return json.loads(response)
        except json.JSONDecodeError as exc:
            raise OllamaClientError(f"Invalid JSON returned by Ollama: {response[:200]}") from exc
