"""OpenAI API client — drop-in replacement for OllamaClient."""

import json
import os
import time
from typing import Optional

from loguru import logger


class OpenAIClient:
    """Wraps the OpenAI API with the same interface as OllamaClient."""

    def __init__(
        self,
        pipeline_model: str = "gpt-5-mini",
        synthesis_model: str = "gpt-5-mini",
        embed_model: str = "text-embedding-3-small",
        temperature: float = 0.1,
        timeout: int = 120,
        api_key: Optional[str] = None,
    ):
        self.pipeline_model = pipeline_model
        self.synthesis_model = synthesis_model
        self.embed_model = embed_model
        self.temperature = temperature
        self.timeout = timeout
        self._api_key = api_key or os.getenv("OPENAI_API_KEY", "")

    def _client(self):
        from openai import OpenAI
        return OpenAI(api_key=self._api_key, timeout=self.timeout)

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
        model = model or self.pipeline_model
        client = self._client()

        kwargs: dict = {}
        if json_output:
            kwargs["response_format"] = {"type": "json_object"}

        for attempt in range(retries + 1):
            try:
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system},
                        {"role": "user", "content": user},
                    ],
                    # temperature omitted — newer OpenAI models (gpt-5-mini, o-series)
                    # only support the default value and reject explicit temperature params
                    **kwargs,
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt < retries:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"OpenAI attempt {attempt+1} failed: {e} — retrying in {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"OpenAI call failed after {retries+1} attempts: {e}")
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
            raise ValueError(f"Could not parse JSON from OpenAI response: {raw[:200]}")

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return 768-dim embedding vector (matches nomic-embed-text dimensions)."""
        client = self._client()
        response = client.embeddings.create(
            model=self.embed_model,
            input=text[:8191],
            dimensions=768,
        )
        return response.data[0].embedding

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[str]:
        return [self.pipeline_model, self.synthesis_model, self.embed_model]
