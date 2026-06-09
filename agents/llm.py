import logging
import os
import string
from urllib.parse import quote_plus

import anthropic
import ollama

logger = logging.getLogger(__name__)
import trafilatura
from googlenewsdecoder import gnewsdecoder
import requests

OLLAMA_MODEL = "llama3.1"
CLAUDE_MODEL = "claude-haiku-4-5-20251001"
MIN_ARTICLE_LENGTH = 200

_claude_client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))


def call_claude(prompt: str) -> str:
    message = _claude_client.messages.create(
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
        logger.warning("Claude unavailable (%s), switching to Ollama", e)
        return call_ollama(prompt)

def build_google_news_url(query:str,lang:str = 'en') ->str:
    """
    Create URL for RSS Google News search based on query and language.

    Example:
        build_google_news_url("AI startup", "en")
        → "https://news.google.com/rss/search?q=AI+startup&hl=en&gl=US&ceid=US:en"

    Args:
        query: search query string
        lang: language code, either "en" or "ru". Determines the Google News edition

    Returns:
        URL for feedparser
    """
    query=quote_plus(query)
    if lang == 'ru':
        return f'https://news.google.com/rss/search?q={query}&hl=ru&gl=RU&ceid=RU:ru'

    else:
        return f"https://news.google.com/rss/search?q={query}&hl=en-US&gl=US&ceid=US:en"
def fetch_article_text(url: str) -> str | None:
    """
    Download article text.
    If URL is a Google News wrapper, decode it to the real URL first.
    """

    
    if "news.google.com" in url:
        try:
            decoded = gnewsdecoder(url, interval=1)

            if decoded.get("status"):
                url = decoded["decoded_url"]
                logger.debug("Real URL: %s...", url[:70])
            else:
                logger.warning("Failed to decode Google News URL")
                return None

        except Exception as e:
            logger.warning("Decoder error: %s", e)
            return None

    # download article content with trafilatura
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9",
        "Accept-Language": "en-US,en;q=0.9",
    }

    try:
        response = requests.get(url, headers=headers, timeout=10, allow_redirects=True)

        if response.status_code != 200:
            logger.warning("HTTP %s for %s", response.status_code, url[:70])
            return None

        text = trafilatura.extract(
            response.text,
            include_comments=False,
            include_tables=False,
        )

        return text

    except Exception as e:
        logger.warning("Article fetch error: %s", e)
        return None

def normalize_title(title:str)->str:
   title = title.lower()
   title = title.translate(str.maketrans('','',string.punctuation))
   title =' '.join(title.split())
   return title

