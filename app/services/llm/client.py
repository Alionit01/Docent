import json
import time
from openai import AsyncOpenAI
from app.config import settings

_client: AsyncOpenAI | None = None


def _get_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(
            api_key=settings.llm_api_key,
            base_url=settings.llm_base_url,
        )
    return _client


async def llm_complete(
    messages: list[dict],
    temperature: float = 0.3,
    max_retries: int = 3,
    json_mode: bool = False,
) -> dict | None:
    kwargs = {
        "model": settings.llm_model,
        "messages": messages,
        "temperature": temperature,
    }
    if json_mode:
        kwargs["response_format"] = {"type": "json_object"}

    for attempt in range(max_retries):
        try:
            response = await _get_client().chat.completions.create(**kwargs)
            content = response.choices[0].message.content
            if json_mode:
                return json.loads(content)
            return {"text": content}
        except Exception:
            if attempt < max_retries - 1:
                time.sleep(2 ** attempt)
            else:
                return None
