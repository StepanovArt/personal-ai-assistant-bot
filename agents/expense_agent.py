import json
import logging
import re
from datetime import datetime

from agents.llm import call_llm
from database.db import add_expense, get_or_create_user, get_total_by_category

logger = logging.getLogger(__name__)

CATEGORIES = ["food", "transport", "cafe", "shopping", "entertainment", "health", "housing", "other"]

SYNONYMS: dict[str, str] = {
    "groceries": "food", "supermarket": "food", "store": "food",
    "restaurant": "cafe", "coffee": "cafe", "coffee shop": "cafe",
    "taxi": "transport", "metro": "transport", "bus": "transport", "uber": "transport",
    "clothes": "shopping", "shoes": "shopping",
    "cinema": "entertainment", "games": "entertainment",
    "rent": "housing", "apartment": "housing",
    "pharmacy": "health", "doctor": "health",
}

CURRENCY_ALIASES: dict[str, str] = {
    "dirham": "AED", "dirhams": "AED", "aed": "AED",
    "ruble": "RUB", "rubles": "RUB", "rub": "RUB",
    "dollar": "USD", "usd": "USD", "$": "USD",
    "euro": "EUR", "eur": "EUR", "€": "EUR",
}


def _normalize_category(raw: str) -> str:
    raw = raw.lower().strip()
    if raw in CATEGORIES:
        return raw
    if raw in SYNONYMS:
        return SYNONYMS[raw]
    for kw, cat in SYNONYMS.items():
        if kw in raw:
            return cat
    return "other"


def _detect_currency(text: str) -> str:
    lower = text.lower()
    for alias, code in CURRENCY_ALIASES.items():
        if alias in lower:
            return code
    return "AED"


def _regex_fallback(text: str) -> dict:
    amount_match = re.search(r"\b(\d+(?:[.,]\d+)?)\b", text)
    amount = float(amount_match.group(1).replace(",", ".")) if amount_match else 0.0
    amount = max(0.0, amount)

    lower = text.lower()
    category = "other"
    for kw, cat in SYNONYMS.items():
        if kw in lower:
            category = cat
            break
    else:
        for cat in CATEGORIES:
            if cat in lower:
                category = cat
                break

    return {
        "amount": amount,
        "currency": _detect_currency(text),
        "category": category,
        "description": text.strip(),
    }


def extract_expense(text: str) -> dict:
    """
    Extracts expense structure from free-form text.
    Returns dict with keys: amount, currency, category, description.
    Falls back to regex if LLM fails.
    """
    prompt = f"""
You are an expense parser. Extract structured data from the user's message.

User message: "{text}"

Pick the best category:
- food: groceries, food at home, supermarket, toast, sandwich, snacks, drinks
- cafe: cafe, restaurant, coffee shop, eating out, takeaway order
- transport: taxi, uber, bus, metro, fuel, parking
- shopping: clothes, shoes, electronics, household items
- entertainment: cinema, games, events, concerts, sports
- health: pharmacy, doctor visit, medicine, gym
- housing: rent, utilities, internet, housing
- other: anything that doesn't fit above

Return ONLY valid JSON, no extra text:
{{
  "amount": <number>,
  "currency": "<3-letter code, e.g. AED, RUB, USD>",
  "category": "<one of: food, transport, cafe, shopping, entertainment, health, housing, other>",
  "description": "<short description in the same language as the input, 3-6 words>"
}}

Rules:
- amount must be a positive number
- if currency is unclear, use AED
- category must be exactly one from the list above
"""
    try:
        raw = call_llm(prompt)
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        if not clean:
            raise ValueError("LLM returned empty response")
        data = json.loads(clean)

        amount = float(data.get("amount", 0))
        if amount <= 0:
            raise ValueError("amount must be positive")

        return {
            "amount": amount,
            "currency": str(data.get("currency", "AED")).upper(),
            "category": _normalize_category(str(data.get("category", "other"))),
            "description": str(data.get("description", text.strip())),
        }
    except Exception as e:
        logger.warning("LLM extraction failed (%s), using regex fallback", e)
        return _regex_fallback(text)


def save_expense(telegram_id: int, text: str) -> dict:
    """Extracts expense from text and saves it to the DB. Returns the saved dict."""
    extracted = extract_expense(text)
    user = get_or_create_user(telegram_id, [])
    expense_id = add_expense(
        user_id=user["id"],
        amount=extracted["amount"],
        currency=extracted["currency"],
        category=extracted["category"],
        description=extracted["description"],
    )
    logger.info(
        "Expense saved: id=%s user=%s amount=%.2f %s category=%s",
        expense_id, telegram_id, extracted["amount"], extracted["currency"], extracted["category"],
    )
    return {**extracted, "id": expense_id}


def get_monthly_summary(telegram_id: int) -> str:
    """Returns a text report of expenses for the current month."""
    user = get_or_create_user(telegram_id, [])
    rows = get_total_by_category(user["id"], days=30)

    if not rows:
        return "No expenses found in the last 30 days."

    month_name = datetime.now().strftime("%B %Y")

    totals_by_currency: dict[str, float] = {}
    for r in rows:
        totals_by_currency[r["currency"]] = totals_by_currency.get(r["currency"], 0) + r["total"]

    total_lines = ", ".join(f"{v:.0f} {k}" for k, v in totals_by_currency.items())
    lines = [f"📊 {month_name}\n", f"Total: {total_lines}\n", "By category:"]
    for row in rows:
        lines.append(f"  • {row['category']} — {row['total']:.0f} {row['currency']}")

    return "\n".join(lines)
