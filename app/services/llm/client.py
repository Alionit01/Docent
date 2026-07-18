import json
import time
import logging
import re
from openai import AsyncOpenAI
from app.config import settings

logger = logging.getLogger(__name__)

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


def _try_parse_json(text: str) -> dict | None:
    """Try to extract JSON from text that may have markdown fences or extra content."""
    text = text.strip()
    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Try extracting from ```json ... ``` block
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass
    return None


async def llm_complete(
    messages: list[dict],
    temperature: float = 0.3,
    max_retries: int = 3,
    json_mode: bool = False,
) -> dict | None:
    kwargs: dict = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
    }

    # Try with response_format first, fall back to plain text if it fails
    json_is_supported = True

    for attempt in range(max_retries):
        try:
            if json_mode and json_is_supported:
                kwargs["response_format"] = {"type": "json_object"}

            response = await _get_client().chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            logger.info(f"LLM response received, usage: {response.usage}")

            if json_mode:
                parsed = _try_parse_json(content)
                if parsed is not None:
                    return parsed
                # If json_object format failed, fall back on next attempt
                if json_is_supported and "response_format" in kwargs:
                    logger.warning("JSON parse failed with response_format, falling back to plain text")
                    json_is_supported = False
                    kwargs.pop("response_format", None)
                    continue
                # Try one more time without response_format
                if json_is_supported:
                    json_is_supported = False
                    kwargs.pop("response_format", None)
                    continue

            return {"text": content}

        except Exception as e:
            error_msg = str(e)
            logger.warning(f"LLM call attempt {attempt + 1} failed: {error_msg}")

            # If the error is about unsupported response_format, drop it
            if "response_format" in error_msg.lower() or "json_object" in error_msg.lower():
                kwargs.pop("response_format", None)
                json_is_supported = False
                continue

            if attempt < max_retries - 1:
                wait = 2 ** attempt
                logger.info(f"Retrying in {wait}s...")
                time.sleep(wait)
            else:
                logger.error(f"LLM call failed after {max_retries} attempts")
                return None

    return None
