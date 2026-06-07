# ============================================================
# СТАНДАРТНАЯ БИБЛИОТЕКА
# ============================================================
import os
import string
from urllib.parse import quote_plus

import anthropic
import ollama
import trafilatura
from googlenewsdecoder import gnewsdecoder
import requests

OLLAMA_MODEL = "llama3.1"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MIN_ARTICLE_LENGTH = 200


def call_claude(prompt: str) -> str:
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    message = client.messages.create(
        model=CLAUDE_MODEL,
        max_tokens=1024,
        messages=[{"role": "user", "content": prompt}],
    )
    return message.content[0].text


def call_ollama(prompt: str) -> str:
    answer = ollama.chat(model=OLLAMA_MODEL, messages=[{"role": "user", "content": prompt}])
    return answer["message"]["content"]


def call_llm(prompt: str) -> str:
    """Claude primary, Ollama fallback."""
    try:
        return call_claude(prompt)
    except Exception as e:
        print(f"⚠️ Claude недоступен ({e}), переключаюсь на Ollama")
        return call_ollama(prompt)

# собираем URL
def build_google_news_url(query:str,lang:str = 'en') ->str:
    """
    Формирует URL для RSS-фида Google News по поисковому запросу.

    Пример:
        build_google_news_url("AI startup", "en")
        → "https://news.google.com/rss/search?q=AI+startup&hl=en&gl=US&ceid=US:en"

    Args:
        query: поисковый запрос
        lang: "en" или "ru"

    Returns:
        готовый URL для feedparser
    """
    query=quote_plus(query)
    if lang == 'ru':
        return f'https://news.google.com/rss/search?q={query}&hl=ru&gl=RU&ceid=RU:ru'

    else:
        return f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
# извлекаем текст из статьи

def fetch_article_text(url: str) -> str | None:
    """
    Скачивает текст статьи.
    Если URL — Google News обёртка, сначала декодирует в реальный URL.
    """

    # 🆕 ШАГ 1: если это Google News URL — декодируем
    if "news.google.com" in url:
        try:
            decoded = gnewsdecoder(url, interval=1)

            if decoded.get("status"):
                url = decoded["decoded_url"]
                print(f"     🔓 Real URL: {url[:70]}...")
            else:
                print(f"     ⚠️ Не удалось декодировать Google URL")
                return None

        except Exception as e:
            print(f"     ⚠️ Decoder error: {e}")
            return None

    # ШАГ 2: скачиваем как раньше
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)

        if response.status_code != 200:
            print(f"     ⚠️ Status: {response.status_code}")
            return None

        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
        )

        return text

    except Exception as e:
        print(f"     ⚠️ Error: {e}")
        return None

#избавляемся от дубликатов
def normalize_title(title:str)->str:
   title = title.lower()
   title = title.translate(str.maketrans('','',string.punctuation))
   title =' '.join(title.split())
   return title

