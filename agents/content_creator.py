"""
Content Creator Agent — generates LinkedIn posts from trending news.

Pipeline:
1. TrendWatcher → news articles
2. SelectorAgent → picks the best article
3. WriterAgent → generates the post
"""

import json
import logging

from agents.llm import call_llm

logger = logging.getLogger(__name__)
from agents.trendwatcher import graph as trend_graph
from database.db import get_db,get_or_create_user, mark_news_shown

# =========================
# 1. FETCH TRENDS
# =========================

def fetch_trends(telegram_id: int, interests: list[str], max_articles: int = 5) -> list[dict]:
    """Fetches fresh articles via TrendWatcher."""

    result = trend_graph.invoke({
        "telegram_id": telegram_id,
        "user_interests": interests,
        "max_articles": max_articles,
    })

    return result.get("articles_with_text", []) or []


# 2. SELECT BEST NEWS (STRUCTURED)
# =========================
def pick_hottest_news(news_list: list[dict]) -> dict | None:
    """LLM selects the most viral news item (via JSON output)."""

    if not news_list:
        return None

    if len(news_list) == 1:
        chosen = news_list[0].copy()
        chosen["reason"] = "only article available"
        return chosen

    news_text = ""
    for i, news in enumerate(news_list, 1):
        text_preview = news.get("text", "")[:500]

        news_text += f"""
    === NEWS {i} ===
    Title: {news.get('title', 'N/A')}
    Preview: {text_preview}...
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

    answer = call_llm(prompt)

    logger.debug("LLM selector output: %s", answer)

    # =========================
    # SAFE PARSING
    # =========================
    try:
        data = json.loads(answer)

        idx = data.get("chosen_index")
        reason = data.get("reason", "not provided")

        if not idx or idx < 1 or idx > len(news_list):
            raise ValueError("invalid index")

        chosen = news_list[idx - 1].copy()
        chosen["reason"] = reason
        return chosen

    except Exception as e:
        logger.warning("Selector fallback triggered: %s", e)

        chosen = news_list[0].copy()
        chosen["reason"] = "fallback: LLM output invalid"
        return chosen


# =========================
# 3. GENERATE POSTS
# =========================

def generate_linkedin_post(topic: str, context: str = "") -> dict:
    """Generates a LinkedIn post from the given topic and context."""
    logger.debug("Topic length: %d chars, context length: %d chars", len(topic), len(context))
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
    logger.debug("Prompt length: %d chars", len(prompt))
    logger.info("Calling LLM for post generation...")
    answer = call_llm(prompt)
    logger.info("LLM responded: %d chars", len(answer))
    return {"story": answer}


def mark_article_as_used(telegram_id: int, article_url: str, article_title: str):
    """Marks an article as used for post generation."""
    with get_db() as conn:
        user = conn.execute("SELECT id FROM users WHERE telegram_id = ?",
            (telegram_id,)
        ).fetchone()

        if not user:
            return

        user_id = user["id"]

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
    user = get_or_create_user(telegram_id, [])
    user_id = user["id"]

    logger.info("Fetching articles for user %s...", telegram_id)
    articles = fetch_trends(telegram_id, interests, max_articles=5)

    if not articles:
        return {"error": "No news found"}

    logger.info("Got %d articles", len(articles))

    logger.info("Picking hottest article...")
    chosen = pick_hottest_news(articles)

    if not chosen:
        return {"error": "Selection failed"}

    logger.info("Selected: %s", chosen['title'])

    mark_news_shown(
        user_id=user_id,
        url=chosen["url"],
        title=chosen.get("title")
    )
    logger.debug("Marked as shown in DB")

    logger.info("Generating LinkedIn post...")
    variants = generate_linkedin_post(
        topic=chosen.get("title", ""),
        context=chosen.get("text", "")[:500]
    )

    return {
        "chosen_news": chosen,
        "variants": variants
    }