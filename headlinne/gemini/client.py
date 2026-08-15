"""Thin wrapper around the Gemini 3.1 Flash-Lite API.

Uses the modern google-genai SDK. We ask the model for JSON (response_mime_type
= application/json) and describe the exact shape in the prompt, then parse and
validate ourselves. This is robust across SDK versions and works with the
model's thinking levels.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

from ..config import (GEMINI_FALLBACK_MODELS, GEMINI_MAX_RETRIES, GEMINI_MODEL,
                      GEMINI_TEMPERATURE,
                      GEMINI_THINKING_LEVEL, SECRETS)
from ..logging_setup import get_logger

log = get_logger("gemini.client")


class GeminiError(RuntimeError):
    pass


def _is_quota_error(exc: Exception) -> bool:
    """Gemini signals an exhausted allowance as 429 / RESOURCE_EXHAUSTED."""
    text = f"{exc}"
    return "429" in text or "RESOURCE_EXHAUSTED" in text


def _extract_json(text: str) -> Any:
    """Parse a JSON object/array from model text, tolerating code fences."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
    text = re.sub(r"\n?```$", "", text).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        # Grab the outermost {...} or [...] block.
        match = re.search(r"(\{.*\}|\[.*\])", text, re.DOTALL)
        if match:
            return json.loads(match.group(1))
        raise


class GeminiClient:
    def __init__(self, api_key: str | None = None, model: str = GEMINI_MODEL,
                 fallback_models: tuple[str, ...] = GEMINI_FALLBACK_MODELS):
        # Quota is counted per model, so each fallback is a fresh allowance
        # rather than a second try at the same one - the same reasoning the TTS
        # client already uses. Without this, exhausting the primary model's
        # daily cap fails the whole run even though other models are available.
        self.models = [model, *(m for m in fallback_models if m and m != model)]
        self._model_index = 0
        self._api_key = api_key or SECRETS.gemini_api_key
        self._client = None

    @property
    def model(self) -> str:
        """The model currently in use. Advances as allowances are exhausted."""
        return self.models[self._model_index]

    def _ensure_client(self):
        if self._client is not None:
            return
        if not self._api_key:
            raise GeminiError("GEMINI_API_KEY is not set.")
        try:
            from google import genai  # imported lazily
        except ImportError as exc:  # pragma: no cover
            raise GeminiError(
                "google-genai is not installed. Run: pip install google-genai"
            ) from exc
        self._client = genai.Client(api_key=self._api_key)

    def generate_json(
        self,
        *,
        system: str,
        prompt: str,
        temperature: float = GEMINI_TEMPERATURE,
        thinking_level: str = GEMINI_THINKING_LEVEL,
    ) -> Any:
        """Generate and return parsed JSON, retrying on transient/parse errors."""
        self._ensure_client()
        from google.genai import types

        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=temperature,
            response_mime_type="application/json",
            thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
        )

        last_err: Exception | None = None
        attempt_prompt = prompt
        for attempt in range(1, GEMINI_MAX_RETRIES + 1):
            try:
                resp = self._client.models.generate_content(
                    model=self.model,
                    contents=attempt_prompt,
                    config=config,
                )
                text = resp.text or ""
                if not text.strip():
                    raise GeminiError("empty response")
                return _extract_json(text)
            except Exception as exc:  # noqa: BLE001 - we want to retry broadly
                last_err = exc
                # A quota refusal will not clear by waiting: the window is a day,
                # not seconds. Move to the next model's allowance immediately and
                # retry without burning the backoff.
                if _is_quota_error(exc) and self._model_index + 1 < len(self.models):
                    self._model_index += 1
                    log.warning("Gemini quota exhausted, switching to %s",
                                self.model)
                    continue
                wait = min(2 ** attempt, 20)
                log.warning("Gemini attempt %d/%d failed: %s (retrying in %ss)",
                            attempt, GEMINI_MAX_RETRIES, exc, wait)
                # On a parse error, nudge the model to return valid JSON only.
                if isinstance(exc, json.JSONDecodeError):
                    attempt_prompt = (
                        prompt
                        + "\n\nIMPORTANT: Respond with valid minified JSON only. "
                          "No commentary, no markdown fences."
                    )
                time.sleep(wait)

        raise GeminiError(
            f"Gemini failed after {GEMINI_MAX_RETRIES} attempts across "
            f"{self._model_index + 1} model(s): {last_err}")
