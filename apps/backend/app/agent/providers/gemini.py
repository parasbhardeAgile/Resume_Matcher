import aiohttp
import json
import logging
from typing import Any, Dict

from ..exceptions import ProviderError
from .base import Provider, EmbeddingProvider
from ...core import settings

logger = logging.getLogger(__name__)


class GeminiProvider(Provider):
    """
    Provider for text generation using Google Gemini API.
    """
    def __init__(
        self,
        model_name: str = settings.LL_MODEL,
        api_key: str | None = None,
        api_base_url: str | None = None,
        opts: Dict[str, Any] = None
    ):
        self.model_name = model_name
        self.api_key = api_key or settings.LLM_API_KEY
        self.api_base_url = api_base_url or settings.LLM_BASE_URL or "https://generativelanguage.googleapis.com/v1beta"
        self.opts = opts or {}

        if not self.api_key:
            raise ProviderError("Gemini API key is missing")

    async def __call__(self, prompt: str, **generation_args: Any) -> Dict[str, Any]:
        """
        Calls the Gemini API with a prompt and returns parsed JSON output if possible.
        """
        url = f"{self.api_base_url}/models/{self.model_name}:generateContent?key={self.api_key}"
        max_tokens = self.opts.get("max_output_tokens", 8192)
        logger.info(f"✅ GeminiProvider is using max_output_tokens: {max_tokens}")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature": self.opts.get("temperature", 0.2),
                "topK": self.opts.get("top_k", 40),
                "topP": self.opts.get("top_p", 0.9),
                "maxOutputTokens": max_tokens
            }
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise ProviderError(f"Gemini API error: {response.status} - {text}")

                    data = await response.json()
                    logger.info(f"provider in gemini response: {data}")
                    text_output = data["candidates"][0]["content"]["parts"][0]["text"]

                    try:
                        return json.loads(text_output)
                    except Exception:
                        return {"text": text_output}

        except Exception as e:
            logger.error(f"Gemini provider error: {e}")
            raise ProviderError(f"Gemini provider error: {e}")


class GeminiEmbeddingProvider(EmbeddingProvider):
    """
    Provider for embeddings using Google Gemini API.
    """
    def __init__(
        self,
        embedding_model: str = settings.EMBEDDING_MODEL,
        api_key: str | None = None,
        api_base_url: str | None = None,
    ):
        self.embedding_model = embedding_model
        self.api_key = api_key or settings.EMBEDDING_API_KEY
        self.api_base_url = api_base_url or settings.EMBEDDING_BASE_URL or "https://generativelanguage.googleapis.com/v1beta"

        if not self.api_key:
            raise ProviderError("Gemini Embedding API key is missing")

    async def embed(self, text: str) -> list[float]:
        url = f"{self.api_base_url}/models/{self.embedding_model}:embedContent?key={self.api_key}"
        payload = {"content": {"parts": [{"text": text}]}}

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as response:
                    if response.status != 200:
                        text = await response.text()
                        raise ProviderError(f"Gemini Embedding API error: {response.status} - {text}")
                    data = await response.json()
                    return data["embedding"]["values"]

        except Exception as e:
            logger.error(f"Gemini embedding error: {e}")
            raise ProviderError(f"Gemini embedding error: {e}")
