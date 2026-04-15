from llm.client import OllamaClient
from llm.gemini_client import GeminiClient
from llm.openai_client import OpenAIClient


def create_llm_client(config) -> OllamaClient | GeminiClient | OpenAIClient:
    """Return the right LLM client based on LLM_PROVIDER in the config."""
    if config.llm.provider == "gemini":
        return GeminiClient(
            pipeline_model=config.llm.pipeline_model,
            synthesis_model=config.llm.synthesis_model,
            temperature=config.llm.temperature,
            timeout=config.llm.timeout,
        )
    if config.llm.provider == "openai":
        return OpenAIClient(
            pipeline_model=config.llm.pipeline_model,
            synthesis_model=config.llm.synthesis_model,
            temperature=config.llm.temperature,
            timeout=config.llm.timeout,
        )
    return OllamaClient(
        base_url=config.llm.base_url,
        pipeline_model=config.llm.pipeline_model,
        synthesis_model=config.llm.synthesis_model,
        embed_model=config.llm.embed_model,
        temperature=config.llm.temperature,
        timeout=config.llm.timeout,
    )
