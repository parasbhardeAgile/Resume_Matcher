import json
import logging
import re
from typing import Any, Dict, List, Tuple

from .base import Strategy
from ..providers.base import Provider
from ..exceptions import StrategyError


logger = logging.getLogger(__name__)

# Precompiled for performance; matches ```json ... ``` or ``` ... ``` fenced blocks
FENCE_PATTERN = re.compile(r"```(?:json)?\s*([\s\S]*?)```", re.IGNORECASE)


class JSONWrapper(Strategy):
    async def __call__(
        self, prompt: str, provider: Provider, **generation_args: Any
    ) -> Dict[str, Any]:
        """
        Wrapper strategy to format the prompt as JSON with the help of LLM.
        """
        response = await provider(prompt, **generation_args)

        # --- Start Modification ---
        # Check if the response is a dictionary and extract the text content
        if isinstance(response, dict) and 'text' in response:
            response_text = response['text']
        elif isinstance(response, str):
            response_text = response
        else:
            logger.error(f"Unexpected response type from provider: {type(response)}")
            raise StrategyError("Unexpected response type from provider.")

        response_text = response_text.strip()
        # --- End Modification ---

        logger.info(f"provider response text: {response_text}") # Log the extracted text

        # 1) Try direct parse first
        try:
            # Use response_text instead of response
            return json.loads(response_text)
        except json.JSONDecodeError:
            pass

        # 2) If wrapped in fenced code blocks, try all and return the first valid JSON
        #    Matches ```json\n...``` or ```\n...``` variants
        # Use response_text instead of response
        for fence_match in FENCE_PATTERN.finditer(response_text):
            fenced = fence_match.group(1).strip()
            try:
                return json.loads(fenced)
            except json.JSONDecodeError:
                continue

        # 3) Fallback: extract the largest JSON-looking object block { ... }
        # Use response_text instead of response
        obj_start, obj_end = response_text.find("{"), response_text.rfind("}")

        candidates: List[Tuple[int, str]] = []
        if obj_start != -1 and obj_end != -1 and obj_end > obj_start:
            # Use response_text instead of response
            candidates.append((obj_start, response_text[obj_start : obj_end + 1]))

        for _, candidate in candidates:
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                candidate2 = candidate.replace("```", "").strip()
                try:
                    return json.loads(candidate2)
                except json.JSONDecodeError:
                    continue

        if candidates:
            # If we had candidates but none parsed, log the last error contextfully
            # Use response_text instead of response
            _err_preview = response_text if len(response_text) <= 2000 else response_text[:2000] + "... (truncated)"
            logger.error(
                "provider returned non-JSON. failed to parse candidate blocks - response: %s",
                _err_preview,
            )
            raise StrategyError("JSON parsing error: failed to parse candidate JSON blocks")

        # 4) No braces found: fail clearly
        logger.error(
            # Use response_text instead of response
            "provider response contained no JSON object braces: %s", response_text
        )
        raise StrategyError("JSON parsing error: no JSON object detected in provider response")

# --- MDWrapper remains the same ---
class MDWrapper(Strategy):
    # ... (keep the existing MDWrapper code) ...
    async def __call__(
        self, prompt: str, provider: Provider, **generation_args: Any
    ) -> str: # Changed return type hint to str
        """
        Wrapper strategy to format the prompt as Markdown with the help of LLM.
        """
        logger.info(f"prompt given to provider: \n{prompt}")
        response = await provider(prompt, **generation_args)

        # --- Start Modification for MDWrapper ---
        # Handle potential dictionary response for MDWrapper as well
        if isinstance(response, dict) and 'text' in response:
            response_text = response['text']
        elif isinstance(response, str):
            response_text = response
        else:
            logger.error(f"Unexpected response type from provider for MD: {type(response)}")
            raise StrategyError("Unexpected response type from provider for MD.")
        # --- End Modification for MDWrapper ---

        logger.info(f"provider response: {response_text}") # Log the extracted text
        try:
            # Use response_text instead of response
            response_text = (
                "```md\n" + response_text + "```" if "```md" not in response_text else response_text
            )
            return response_text # Return the string directly
        except Exception as e:
            logger.error(
                # Use response_text instead of response
                f"provider returned non-md. parsing error: {e} - response: {response_text}"
            )
            raise StrategyError(f"Markdown processing error: {e}") from e