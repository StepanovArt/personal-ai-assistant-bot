"""
Content Creator Agent — генерация LinkedIn постов из трендов.

Pipeline:
1. TrendWatcher → новости
2. SelectorAgent → выбор лучшей новости
3. WriterAgent → генерация постов
"""

import json

from agents.llm import call_ollama
from agents.trendwatcher import graph as trend_graph
from database.db import get_db,get_or_create_user, mark_news_shown

# =========================
# 1. FETCH TRENDS
# =========================

def fetch_trends(telegram_id: int, interests: list[str], max_articles: int = 5) -> list[dict]:
    """Получает свежие статьи через TrendWatcher."""

    result = trend_graph.invoke({
        "telegram_id": telegram_id,
        "user_interests": interests,
        "max_articles": max_articles,  # 🆕 чтобы граф знал сколько брать
    })

    return result.get("articles_with_text", []) or []


# 2. SELECT BEST NEWS (STRUCTURED)
# =========================
def pick_hottest_news(news_list: list[dict]) -> dict | None:
    """LLM выбирает самую вирусную новость (через JSON output)."""

    if not news_list:
        return None

    if len(news_list) == 1:
        chosen = news_list[0].copy()
        chosen["reason"] = "единственная статья"
        return chosen

    news_text = ""
    for i, news in enumerate(news_list, 1):
        # 🆕 берём первые 500 символов текста как превью для выбора
        text_preview = news.get("text", "")[:500]

        news_text += f"""
    === НОВОСТЬ {i} ===
    Заголовок: {news.get('title', 'N/A')}
    Превью: {text_preview}...
    """

    prompt = f"""
    You are a LinkedIn content strategy expert.

    Your task is to select the SINGLE most viral and engaging news item from the list below.

    Selection criteria (in order of importance):
    - Virality and potential to generate engagement (comments, reactions, debate)
    - Recency and current relevance
    - Relevance to AI / tech audience
    - Strength of potential hook for a LinkedIn post

    NEWS LIST:
    {news_text}

    IMPORTANT:
    - Choose ONLY ONE item
    - Be strict and decisive
    - Prioritize engagement over neutrality or completeness

    OUTPUT FORMAT (STRICT JSON ONLY):

    {{
      "chosen_index": integer from 1 to {len(news_list)},
      "reason": "one clear sentence explaining why this news is the most viral"
    }}

    Rules:
    - NO extra text
    - NO markdown
    - NO explanations outside JSON
    - ONLY valid JSON response
    """

    answer = call_ollama(prompt)

    print("🎯 RAW LLM OUTPUT:")
    print(answer)

    # =========================
    # SAFE PARSING
    # =========================
    try:
        data = json.loads(answer)

        idx = data.get("chosen_index")
        reason = data.get("reason", "не указана")

        if not idx or idx < 1 or idx > len(news_list):
            raise ValueError("invalid index")

        chosen = news_list[idx - 1].copy()
        chosen["reason"] = reason
        return chosen

    except Exception as e:
        print(f"⚠️ fallback triggered: {e}")

        chosen = news_list[0].copy()
        chosen["reason"] = "fallback: LLM output invalid"
        return chosen


# =========================
# 3. GENERATE POSTS
# =========================

def generate_linkedin_post(topic: str, context: str = "") -> dict:
    """Генерирует 3 варианта поста."""
    print(f"📏 Топик: {len(topic)} симв")
    print(f"📏 Контекст: {len(context)} симв")
    prompt = f"""
    You are a senior LinkedIn content writer for an AI/Tech engineer.

    TOPIC:
    {topic}

    CONTEXT:
    {context[:1200]}

    Your task:
    Write ONE concise, high-quality LinkedIn post.

    STYLE:
    - Personal but professional tone
    - Strong hook in the first 1-2 lines
    - Short paragraphs
    - Practical insight
    - Natural LinkedIn writing style
    - End with a discussion question
    - Add 3-5 relevant hashtags

    STRICT LENGTH RULE:
    - Maximum 1200 characters total
    - Prefer 700-1000 characters
    - Never exceed 1200 characters
    - Avoid unnecessary details

    IMPORTANT:
    - Return ONLY the post text
    - NO markdown
    - NO explanations
    - NO intro like "Here is your post"
    - Start directly with the post

    LANGUAGE:
    Use the same language as the topic.

    Write the post now.
    """
    print(f"📏 Промпт: {len(prompt)} симв")
    print(f"🤖 Зову Llama...")
    answer = call_ollama(prompt)
    print(f"✅ Llama ответила: {len(answer)} симв")
    try:
        return json.loads(answer)
    except Exception:
        return {
            "story": answer,
            "educational": "",
            "opinion": ""
        }


def mark_article_as_used(telegram_id: int, article_url: str, article_title: str):
    """Помечает статью как использованную для поста."""
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()

        if not user:
            return

        user_id = user["id"]

        # Сохраняем в shown_news
        conn.execute(
            """
            INSERT INTO shown_news (user_id, url, title, shown_at)
            VALUES (?, ?, ?, datetime('now'))
            """,
            (user_id, article_url, article_title)
        )
        conn.commit()


# =========================
# 4. MAIN PIPELINE
# =========================

def create_post_from_trends(telegram_id: int, interests: list[str]) -> dict:
    # Получаем user_id
    user = get_or_create_user(telegram_id, [])
    user_id = user["id"]

    print("📰 Fetching articles...")
    articles = fetch_trends(telegram_id, interests, max_articles=5)

    if not articles:
        return {"error": "No news found"}

    print(f"✅ Got {len(articles)} articles")

    print("🎯 Picking hottest...")
    chosen = pick_hottest_news(articles)

    if not chosen:
        return {"error": "Selection failed"}

    print(f"🔥 Selected: {chosen['title']}")

    # 🎯 СОХРАНЯЕМ В БД — ПОСЛЕ выбора
    mark_news_shown(
        user_id=user_id,
        url=chosen["url"],  # одна строка, не список
        title=chosen.get("title")  # бонус — для дебага
    )
    print(f"💾 Помечено в БД")

    print("✍️ Generating posts...")
    variants = generate_linkedin_post(
        topic=chosen.get("title", ""),
        context=chosen.get("text", "")[:500]
    )

    return {
        "chosen_news": chosen,
        "variants": variants
    }

# ============================================================
# ТЕСТ
# ============================================================
if __name__ == "__main__":
    print("✍️ Тест полного pipeline ContentCreator...")
    print()

    # Используй СВОЙ telegram_id и интересы
    result = create_post_from_trends(
        telegram_id=913679228,
        interests=["AI"]
    )

    if "error" in result:
        print(f"❌ Ошибка: {result['error']}")
    else:
        chosen = result["chosen_news"]
        print(f"\n🎯 ВЫБРАННАЯ НОВОСТЬ:")
        print(f"   Заголовок: {chosen['title']}")
        print(f"   URL: {chosen.get('url', 'N/A')}")
        print(f"   Почему: {chosen['reason']}")

        print(f"\n📝 СГЕНЕРИРОВАННЫЕ ВАРИАНТЫ:\n")
        for key, variant_text in result["variants"].items():
            print(f"\n{'=' * 70}")
            print(f"📝 {key.upper()}")  # ← просто ключ (story/educational/opinion)
            print(f"{'=' * 70}")
            print(variant_text)  # ← это и есть текст поста
            print(f"\n📊 Длина: {len(variant_text)} символов")