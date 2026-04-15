"""Ollama HTTP client — thin wrapper used by all pipeline steps."""

import json
import time
from typing import Any, Optional

import httpx
from loguru import logger


class OllamaClient:
    """Wraps the Ollama /api/chat and /api/embeddings endpoints."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        pipeline_model: str = "qwen3.5:4b",
        synthesis_model: str = "qwen3.5:4b",
        embed_model: str = "nomic-embed-text",
        temperature: float = 0.1,
        timeout: int = 120,
    ):
        self.base_url = base_url.rstrip("/")
        self.pipeline_model = pipeline_model
        self.synthesis_model = synthesis_model
        self.embed_model = embed_model
        self.temperature = temperature
        self.timeout = timeout

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
        payload: dict[str, Any] = {
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "stream": False,
            "think": False,          # disable Qwen3 thinking mode — faster pipeline calls
            "options": {"temperature": self.temperature},
        }
        if json_output:
            payload["format"] = "json"

        for attempt in range(retries + 1):
            try:
                resp = httpx.post(
                    f"{self.base_url}/api/chat",
                    json=payload,
                    timeout=self.timeout,
                )
                resp.raise_for_status()
                return resp.json()["message"]["content"]
            except Exception as e:
                if attempt < retries:
                    wait = 5 * (attempt + 1)
                    logger.warning(f"LLM attempt {attempt+1} failed: {e} — retrying in {wait}s")
                    time.sleep(wait)
                else:
                    logger.error(f"LLM call failed after {retries+1} attempts: {e}")
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
            # Attempt to extract JSON block if model added prose around it
            start = raw.find("{")
            end = raw.rfind("}") + 1
            if start != -1 and end > start:
                try:
                    return json.loads(raw[start:end])
                except json.JSONDecodeError:
                    pass
            raise ValueError(f"Could not parse JSON from LLM response: {raw[:200]}")

    # ------------------------------------------------------------------
    # Embeddings
    # ------------------------------------------------------------------

    def embed(self, text: str) -> list[float]:
        """Return embedding vector for text."""
        resp = httpx.post(
            f"{self.base_url}/api/embeddings",
            json={"model": self.embed_model, "prompt": text[:4096]},
            timeout=60,
        )
        resp.raise_for_status()
        return resp.json()["embedding"]

    # ------------------------------------------------------------------
    # Health check
    # ------------------------------------------------------------------

    def is_available(self) -> bool:
        try:
            r = httpx.get(f"{self.base_url}/api/version", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    def list_models(self) -> list[str]:
        try:
            r = httpx.get(f"{self.base_url}/api/tags", timeout=10)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
        except Exception:
            return []
