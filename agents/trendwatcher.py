# ============================================================
# СТАНДАРТНАЯ БИБЛИОТЕКА
# ============================================================
import json #Когда llama3.1 будет возвращать список запросов или структурированные ответы
import logging #Когда пайплайн идёт минуту через 10 узлов — без логов ты слепой
from datetime import datetime #Сохраняя саммари, обычно делают имя файла с датой: summaries_2026-05-05.md.
from pathlib import Path #Когда save_results_node будет писать саммари в файл, лучше работать с путями через Path
from typing import TypedDict # ✅ для State и сигнатур
from urllib.parse import quote_plus #Что делает: превращает "AI стартапы" → "AI+%D1%81%D1%82..." для безопасной вставки в URL.
import string
# ============================================================
# СТОРОННИЕ БИБЛИОТЕКИ
# ============================================================
import feedparser              # парсинг RSS-фидов Google News
import ollama                  # клиент для локальной llama3.1
import trafilatura             # извлечение чистого текста из HTML
from langgraph.graph import StateGraph, START, END
import langdetect
# ============================================================
# ВНУТРЕННИЕ МОДУЛИ
# ============================================================
from database.db import get_or_create_user,filter_unseen_urls, mark_news_shown
from agents.llm import call_ollama,build_google_news_url,fetch_article_text,normalize_title
# ============================================================
# CONFIG
# ============================================================

MAX_QUERIES_PER_INTEREST = 3
MAX_NEWS_PER_QUERY = 10
MIN_ARTICLE_LENGTH = 200  # символов, статьи короче — отбрасываем
REQUEST_TIMEOUT = 10      # секунд

GOOGLE_NEWS_RSS_BASE = "https://news.google.com/rss/search"

# ============================================================
# STATES  = словарь, который путешествует через все узлы графа в котором заранее созданые переменые.
# ============================================================
class TrendState(TypedDict):
    # --- Идентификация юзера ---
    telegram_id: int # вход в систему
    user_id: int| None # внутренний id из БД (после load_user)

    # --- Интересы и запросы ---
    user_interests : list[str] # изначальный список интересов
    search_queries : list[str] # поисковые запросы от ллм

    # --- Новости на разных этапах ---
    raw_news : list[dict] # все найденые новости с дублями
    unique_news : list[dict] # после дедубликации
    fresh_news : list[dict] # после фильтрации по url
    relevant_news : list[dict] # после фильтрации по заголовкам
    articles_with_text : list[dict] # текст статей
    max_articles: int

# ============================================================
# NODES
# ============================================================
def load_user_node(state: TrendState) -> dict:
    print(f"🔵 load_user STATE: telegram_id={state.get('telegram_id')}, interests={state.get('user_interests')}")
    user = get_or_create_user(state["telegram_id"], [])
    return {"user_id": user['id']}


def expand_interests_node(state:TrendState) -> dict:
    """
    Превращает список интересов юзера в список поисковых запросов
    через llama3.1.
    """
    print(f"🔵 expand_interests STATE: interests={state.get('user_interests')}")
    interests = state.get("user_interests", [])

    if not interests:
        print("⚠️ Нет интересов — пропускаем")
        return {"search_queries": []}


    today = datetime.now().strftime("%B %Y")  # "May 2026"
    current_year = datetime.now().year  # 2026
    prompt = f"""
    You are a search query generator for Google News.

    Your ONLY task is to generate search queries based on user interests.
    Do NOT discuss ethics, privacy, safety, or relevance.
    The topics are public news categories.

    IMPORTANT:
    - Today is {today}. Focus on FRESH and CURRENT news.
    - Use the year {current_year} ONLY if it is naturally relevant.
    - DO NOT use past years like 2022, 2023, 2024.
    - Prefer queries without any year unless absolutely necessary.

    User interests:
    {', '.join(interests)}

    Generate 5 short Google News search queries for EACH interest.

    Rules:
    - Each query must be on a new line
    - NO numbering
    - NO quotes
    - NO JSON
    - NO explanations
    - ONLY raw search queries

    Queries must be:
    - specific
    - news-oriented
    - focused on recent events, trends, breakthroughs, or updates

    Good examples:
    latest OpenAI news
    AI startup funding rounds
    NVIDIA new GPU release
    major AI industry announcement
    machine learning breakthrough 2026

    Bad examples (DO NOT do this):
    AI news in 2023
    history of Google
    predictions for 2025
    old technology trends

    Example for topic "Dubai":
    Dubai latest news
    Dubai real estate market update
    Dubai tourism statistics 2026
    Dubai infrastructure projects
    Dubai economy investment news

    Now generate queries for:
    {state["user_interests"]}
    """

    answer = call_ollama(prompt)
    queries = [line.strip() for line in answer.split("\n") if line.strip()]
    return {"search_queries": queries}


import requests
import feedparser


def search_news_node(state):
    queries = state.get("search_queries", [])
    if not queries:
        return {"raw_news": []}

    print(f"🔍 Поиск по {len(queries)} запросам...")

    raw_news = []

    for query in queries:
        url = build_google_news_url(query)
        print(f"  🌐 URL: {url}")

        try:
            # 🆕 Скачиваем через requests (с редиректами)
            response = requests.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
                },
                allow_redirects=True,
                timeout=10
            )

            # 🆕 feedparser получает уже готовый контент
            feed = feedparser.parse(response.content)

            entries = feed.entries

            # Определяем язык запроса
            try:
                lang = langdetect.detect(query)
            except:
                lang = "en"

            print(f"  '{query}' [{lang}] → {len(entries)} результатов")

            for entry in entries:
                raw_news.append({
                    "title": entry.get("title", ""),
                    "url": entry.get("link", ""),
                    "source": entry.get("source", {}).get("title", "Unknown") if isinstance(entry.get("source"),
                                                                                            dict) else str(
                        entry.get("source", "Unknown")),
                    "published": entry.get("published", ""),
                    "lang": lang,
                })
        except Exception as e:
            print(f"  ⚠️ Ошибка: {e}")
            continue

    print(f"📰 Всего собрано: {len(raw_news)}")
    return {"raw_news": raw_news}

def deduplicate_node(state:TrendState) -> dict:
    """
    Убирает дубликаты внутри одного запуска:
    1) по URL
    2) по нормализованным заголовкам
    """
    seen_url =set()
    seen_title=set()
    unique_news=[]
    for news in state['raw_news']:
        url=news['url']
        title=news['title']
        norm_title = normalize_title(title)
        if url  in seen_url:
            continue
        if norm_title  in seen_title:
            continue
        seen_url.add(url)
        seen_title.add(norm_title)
        unique_news.append(news)
    return {'unique_news': unique_news}


def filter_already_shown_node(state:TrendState) -> dict:
    """
    Убирает новости, которые уже показывались юзеру в прошлых запусках.
    Использует БД (filter_unseen_urls).
    """
    user_id, unique_news = state["user_id"], state["unique_news"]
    urls=[ i['url'] for i in unique_news ]
    unseen = filter_unseen_urls(user_id, urls)
    fresh  = [ n for n in unique_news if n['url'] in unseen]
    return {'fresh_news':fresh}



def filter_by_titles_node(state: TrendState) -> dict:
    """Просто берём первые N новостей."""
    fresh_news = state['fresh_news']
    max_n=state.get("max_articles")
    relevant_news = fresh_news[:max_n]
    return {"relevant_news": relevant_news}


def read_articles_node(state: TrendState) -> dict:
    relevant_news = state.get("relevant_news", [])
    max_articles = state.get("max_articles", 5)
    to_fetch = relevant_news[:max_articles]

    print(f"📚 Скачиваю текст {len(to_fetch)} статей...")

    articles_with_text = []

    for i, news in enumerate(to_fetch, 1):
        url = news.get("url", "")
        title = news.get("title", "")[:60]

        print(f"  [{i}/{len(to_fetch)}] 📄 {title}...")

        # 🆕 fetch_article_text сама разберётся с Google URL
        text = fetch_article_text(url)

        if not text:
            print(f"     ❌ Не получили текст")
            continue

        if len(text) < 200:
            print(f"     ⏭ Слишком короткий ({len(text)} символов)")
            continue

        print(f"     ✅ Получено {len(text)} символов")

        articles_with_text.append({
            **news,
            "text": text,
        })

    print(f"📊 Итого скачано: {len(articles_with_text)} из {len(to_fetch)}")

    return {"articles_with_text": articles_with_text}



#============================================================
# BUILDERS
# ============================================================
builder = StateGraph(TrendState)

# nodes registration
builder.add_node("load_user", load_user_node)
builder.add_node("expand_interests", expand_interests_node)
builder.add_node("search_news", search_news_node)
builder.add_node("deduplicate", deduplicate_node)
builder.add_node("filter_already_shown", filter_already_shown_node)
builder.add_node("filter_by_titles", filter_by_titles_node)
builder.add_node("read_articles", read_articles_node)


# connect ages
builder.add_edge(START,"load_user")
builder.add_edge("load_user","expand_interests")
builder.add_edge("expand_interests","search_news")
builder.add_edge("search_news","deduplicate")
builder.add_edge("deduplicate","filter_already_shown")
builder.add_edge("filter_already_shown","filter_by_titles")
builder.add_edge("filter_by_titles","read_articles")
builder.add_edge("read_articles",END)

graph = builder.compile()

















