import json
import asyncio
from app.services.llm.client import llm_complete

REPAIR_PROMPT = """
The previous JSON output was invalid. Please fix it.

Error: {error}

Original attempt: {original}

Return ONLY valid JSON with the same structure. Do not include any text outside the JSON.
"""


async def llm_json_with_repair(
    messages: list[dict],
    temperature: float = 0.3,
    max_retries: int = 3,
    fallback_keys: list[str] | None = None,
) -> dict | None:
    """Call LLM with JSON repair on failure. Returns dict or None."""
    for attempt in range(max_retries):
        result = await llm_complete(messages, temperature=temperature, json_mode=False)

        if result is None:
            continue

        text = result.get("text", "")
        try:
            return json.loads(text)
        except json.JSONDecodeError as e:
            if attempt < max_retries - 1:
                repair_messages = messages + [
                    {"role": "user", "content": REPAIR_PROMPT.format(error=str(e), original=text[:500])},
                ]
                result = await llm_complete(repair_messages, temperature=0.1, json_mode=False)
                if result:
                    try:
                        return json.loads(result.get("text", ""))
                    except json.JSONDecodeError:
                        continue
            else:
                # Final fallback: extract what we can
                if fallback_keys:
                    fallback = {}
                    for key in fallback_keys:
                        fallback[key] = text[:200] if key == "explanation" else ""
                    return fallback
                return None

    return None
