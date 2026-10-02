"""Генерация поисковых запросов через внешний LLM (OpenAI-совместимый API)."""

class LLMError(Exception):
    pass

def parse_queries(text):
    import json
    import re
    items = []
    m = re.search(r"\[.*\]", text, re.S)
    if m:
        try:
            items = json.loads(m.group(0))
        except ValueError:
            items = []
    if not items:
        items = [re.sub(r"^[\s\-\*\d\.\)]+", "", ln).strip().strip('"') for ln in text.splitlines()]
    clean, seen = [], set()
    for it in items:
        s = str(it).strip()
        if 2 <= len(s) <= 64 and s.lower() not in seen:
            seen.add(s.lower())
            clean.append(s)
    return clean[:30]

async def generate_queries(topic, language="ru"):
    import os
    import aiohttp

    key = os.getenv("LLM_API_KEY", "").strip()
    if not key:
        raise LLMError("не задан LLM_API_KEY")
    
    url = os.getenv("LLM_API_URL", "https://api.openai.com/v1/chat/completions").strip()
    # Авто-исправление ссылки для OpenRouter
    if url == "https://openrouter.ai" or url == "https://openrouter.ai/":
        url = "https://openrouter.ai/api/v1/chat/completions"

    model = os.getenv("LLM_MODEL", "gpt-4o-mini").strip()

    prompt = (
        f"Сгенерируй до 20 коротких поисковых запросов (1-3 слова) для поиска публичных чатов "
        f"в Telegram по теме «{topic}». Язык запросов: {language}. Включи синонимы, смежные темы, "
        f"популярные формулировки и нишевые подтемы. Ответь ТОЛЬКО JSON-массивом строк, без пояснений."
    )
    payload = {"model": model, "messages": [{"role": "user", "content": prompt}]}
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    
    try:
        timeout = aiohttp.ClientTimeout(total=60)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(url, json=payload, headers=headers) as resp:
                body = await resp.text()
                if resp.status != 200:
                    raise LLMError(f"HTTP {resp.status}: {body[:200]}")
                try:
                    data = await resp.json(content_type=None)
                except Exception:
                    raise LLMError(f"Ошибка JSON. Ответ сервера: {body[:100]}...")
        
        text = data["choices"][0]["message"]["content"]
    except LLMError:
        raise
    except Exception as e:
        raise LLMError(f"{type(e).__name__}: {e}")

    queries = parse_queries(text)
    if topic.lower() not in [q.lower() for q in queries]:
        queries.insert(0, topic)
    if not queries:
        raise LLMError("пустой ответ модели")
    return queries
