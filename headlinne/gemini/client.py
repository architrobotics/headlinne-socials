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
                      GEMINI_TEMPERATURE, GEMINI_THINKING_LEVEL, SECRETS)
from ..logging_setup import get_logger

log = get_logger("gemini.client")

# Gemini returns a "retryDelay": "11s" hint inside a 429 body. Honouring it is
# far better than guessing with exponential backoff, because it is the server
# telling us exactly how long its quota window has left to run. Defined here
# rather than in tts.py, where they used to live, so the text and speech clients
# cannot drift apart on what counts as "out of quota".
_RETRY_DELAY = re.compile(r"'?retryDelay'?\s*:\s*'?(\d+(?:\.\d+)?)s")


def retry_after(exc: Exception) -> float | None:
    match = _RETRY_DELAY.search(str(exc))
    return float(match.group(1)) if match else None


def is_rate_limit(exc: Exception) -> bool:
    text = str(exc)
    return "429" in text or "RESOURCE_EXHAUSTED" in text


class GeminiError(RuntimeError):
    pass


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
    """The text model, with the fallback ladder config has always described.

    `GEMINI_FALLBACK_MODELS` has been in config, in .env.example and in the
    generate workflow's env block since the beginning, and nothing read it.
    Every text call went to one model and, when that model refused, retried the
    same model four times and gave up. Quota is counted per model, so the second
    model is a second daily allowance rather than another go at an empty one -
    which is exactly the reasoning the TTS client was already built around.

    The cost of not having it is not an error message. It is a format quietly
    missing for the day: the reel is one large call in the middle of the run, so
    it is the one that meets the quota wall first, and seven of thirty days went
    out with no reel at all while every other format on those days succeeded.
    """

    def __init__(self, api_key: str | None = None, model: str = GEMINI_MODEL,
                 fallback_models: tuple[str, ...] = GEMINI_FALLBACK_MODELS):
        # Order matters: best model first, each fallback its own quota.
        self.models = [model, *(m for m in fallback_models if m and m != model)]
        # Once a model starts refusing it keeps refusing for the rest of the
        # run, so remember where we got to instead of rediscovering it on every
        # call. The generate run makes eight or nine of these.
        self._model_index = 0
        self._api_key = api_key or SECRETS.gemini_api_key
        self._client = None

    @property
    def model(self) -> str:
        """The model currently in use."""
        return self.models[min(self._model_index, len(self.models) - 1)]

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
        for round_number in range(1, GEMINI_MAX_RETRIES + 1):
            waits: list[float] = []

            # One pass across every model still worth trying. A refusal from one
            # is not a reason to wait, because the next has its own quota, so we
            # move on immediately and only sleep once nothing is left.
            for index in range(self._model_index, len(self.models)):
                model = self.models[index]
                try:
                    resp = self._client.models.generate_content(
                        model=model, contents=attempt_prompt, config=config)
                    text = resp.text or ""
                    if not text.strip():
                        raise GeminiError("empty response")
                    data = _extract_json(text)
                    if index != self._model_index:
                        log.info("Gemini now using %s", model)
                        self._model_index = index
                    return data
                except Exception as exc:  # noqa: BLE001 - try the next model
                    last_err = exc

                # A model that answered with something unparseable is not out of
                # quota, and the next model would most likely do the same thing.
                # Nudge this one instead and let the next round use it.
                if isinstance(last_err, json.JSONDecodeError):
                    attempt_prompt = (
                        prompt
                        + "\n\nIMPORTANT: Respond with valid minified JSON only. "
                          "No commentary, no markdown fences."
                    )
                    break
                if is_rate_limit(last_err):
                    waits.append(retry_after(last_err) or 30.0)
                    if index + 1 < len(self.models):
                        log.info("%s is rate limited, trying %s",
                                 model, self.models[index + 1])
                    continue
                break  # a real error, not quota: another model will not help

            if round_number >= GEMINI_MAX_RETRIES:
                break

            # Everything available is refusing, so now the wait is worth it. Use
            # the shortest window any model offered rather than guessing.
            wait = (min(waits) + 1.0) if waits else min(2 ** round_number, 20)
            log.warning("Gemini round %d/%d failed (%s), waiting %.0fs: %s",
                        round_number, GEMINI_MAX_RETRIES,
                        "rate limited" if waits else "error", wait, last_err)
            time.sleep(wait)

        raise GeminiError(
            f"Gemini failed after {GEMINI_MAX_RETRIES} rounds across "
            f"{len(self.models)} model(s): {last_err}")
