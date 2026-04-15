"""Google Gemini API client — drop-in replacement for OllamaClient."""

import json
import os
import time
from typing import Optional

from loguru import logger


class GeminiClient:
    """Wraps the Google Gemini API with the same interface as OllamaClient."""

    def __init__(
        self,
        pipeline_model: str = "gemini-3.1-flash-lite-preview",
        synthesis_model: str = "gemini-3.1-flash-lite-preview",
        embed_model: str = "text-embedding-004",
        temperature: float = 0.1,
        timeout: int = 120,
        api_key: Optional[str] = None,
    ):
        self.pipeline_model = pipeline_model
        self.synthesis_model = synthesis_model
        self.embed_model = embed_model
        self.temperature = temperature
        self.timeout = timeout
        self._api_key = api_key or os.getenv("GEMINI_API_KEY", "")

    def _client(self):
        from google import genai
        return genai.Client(api_key=self._api_key)

    # ------------------------------------------------------------------
    # Core: chat
    # ------------------------------------------------------------------

    def chat(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        json_output: bool = False,
        retries: int = 2,
    ) -> str:
        """Send a chat message. Returns the assistant reply as a string."""
        from google.genai import types

        model = model or self.pipeline_model
        client = self._client()

        config_kwargs: dict = {
            "system_instruction": system,
            "temperature": self.temperature,
        }
        if json_output:
            config_kwargs["response_mime_type"] = "application/json"

        for attempt in range(retries + 1):
            try:
                response = client.models.generate_content(
                    model=model,
                    contents=user,
                    config=types.GenerateContentConfig(**config_kwargs),
                )
                return response.text
            except Exception as e:
                if attempt < retries:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"Gemini attempt {attempt+1} failed: {e} — retrying in {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"Gemini call failed after {retries+1} attempts: {e}")
                    raise

    # ------------------------------------------------------------------
    # Structured JSON helper
    # ------------------------------------------------------------------

    def chat_json(
        self,
        system: str,
        user: str,
        model: Optional[str] = None,
        retries: int = 2,
    ) -> dict:
        """Chat and parse the response as JSON. Raises ValueError on parse failure."""
        raw = self.chat(system, user, model=model, json_output=True, retries=retries)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Could not parse JSON from Gemini response: {raw[:200]}")

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return embedding vector for text (768-dim, same as nomic-embed-text)."""
        client = self._client()
        result = client.models.embed_content(
            model=self.embed_model,
            contents=text[:4096],
        )
        return result.embeddings[0].values

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[str]:
        return [self.pipeline_model, self.synthesis_model, self.embed_model]
