"""DeepSeek API client — uses OpenAI-compatible API for chat, Ollama for embeddings.

DeepSeek does not provide an embedding API, so embed() falls back to the local
Ollama nomic-embed-text model (same model used by the default Ollama provider).
"""

import os
import time
import json
from typing import Optional

from loguru import logger


class DeepSeekClient:
    """DeepSeek chat via their OpenAI-compatible API; embeddings via local Ollama."""

    BASE_URL = "https://api.deepseek.com"
    OLLAMA_URL = "http://localhost:11434"
    EMBED_MODEL = "nomic-embed-text"

    def __init__(
        self,
        pipeline_model: str = "deepseek-v4-flash",
        synthesis_model: str = "deepseek-v4-flash",
        temperature: float = 0.1,
        timeout: int = 120,
        api_key: Optional[str] = None,
    ):
        self.pipeline_model = pipeline_model
        self.synthesis_model = synthesis_model
        self.temperature = temperature
        self.timeout = timeout
        self._api_key = api_key or os.getenv("DEEPSEEK_API_KEY", "")

    def _client(self):
        from openai import OpenAI
        return OpenAI(api_key=self._api_key, base_url=self.BASE_URL, timeout=self.timeout)

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
                    temperature=self.temperature,
                    **kwargs,
                )
                return response.choices[0].message.content
            except Exception as e:
                if attempt < retries:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"DeepSeek attempt {attempt+1} failed: {e} — retrying in {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"DeepSeek call failed after {retries+1} attempts: {e}")
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
            raise ValueError(f"Could not parse JSON from DeepSeek response: {raw[:200]}")

    # ------------------------------------------------------------------
    # Embeddings — DeepSeek has no embedding API; use local Ollama
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return embedding vector via local Ollama nomic-embed-text."""
        import httpx
        payload = {"model": self.EMBED_MODEL, "prompt": text}
        response = httpx.post(
            f"{self.OLLAMA_URL}/api/embeddings",
            json=payload,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.json()["embedding"]

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        return bool(self._api_key)

    def list_models(self) -> list[str]:
        return [self.pipeline_model, self.synthesis_model, self.EMBED_MODEL]
