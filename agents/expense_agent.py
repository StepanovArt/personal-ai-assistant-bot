import json
import logging
import re
from datetime import datetime

from agents.llm import call_llm
from database.db import add_expense, get_or_create_user, get_total_by_category

logger = logging.getLogger(__name__)

CATEGORIES = ["еда", "транспорт", "кафе", "покупки", "развлечения", "здоровье", "жильё", "другое"]

SYNONYMS: dict[str, str] = {
    "продукты": "еда", "супермаркет": "еда", "магазин": "еда",
    "ресторан": "кафе", "кофе": "кафе", "кафешка": "кафе",
    "такси": "транспорт", "метро": "транспорт", "автобус": "транспорт", "uber": "транспорт",
    "одежда": "покупки", "обувь": "покупки",
    "кино": "развлечения", "игры": "развлечения",
    "аренда": "жильё", "квартира": "жильё",
    "аптека": "здоровье", "врач": "здоровье",
}

CURRENCY_ALIASES: dict[str, str] = {
    "дирхам": "AED", "дирхама": "AED", "дирхамов": "AED", "aed": "AED",
    "рубл": "RUB", "руб": "RUB", "rub": "RUB",
    "доллар": "USD", "usd": "USD", "$": "USD",
    "евро": "EUR", "eur": "EUR", "€": "EUR",
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
    return "другое"


def _detect_currency(text: str) -> str:
    lower = text.lower()
    for alias, code in CURRENCY_ALIASES.items():
        if alias in lower:
            return code
    return "AED"


def _regex_fallback(text: str) -> dict:
    amount_match = re.search(r"\b(\d+(?:[.,]\d+)?)\b", text)
    amount = float(amount_match.group(1).replace(",", ".")) if amount_match else 0.0

    lower = text.lower()
    category = "другое"
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
    Извлекает структуру расхода из произвольного текста.
    Возвращает dict с ключами: amount, currency, category, description.
    При ошибке LLM — regex-fallback.
    """
    prompt = f"""
You are an expense parser. Extract structured data from the user's message.

User message: "{text}"

Return ONLY valid JSON, no extra text:
{{
  "amount": <number>,
  "currency": "<3-letter code, e.g. AED, RUB, USD>",
  "category": "<one of: еда, транспорт, кафе, покупки, развлечения, здоровье, жильё, другое>",
  "description": "<short description in the same language as the input>"
}}

Rules:
- amount must be a positive number
- if currency is unclear, use AED
- category must be exactly one from the list
- description: 3-6 words max
"""
    try:
        raw = call_llm(prompt)
        # Strip markdown code fences if model wraps in ```json
        clean = re.sub(r"```(?:json)?|```", "", raw).strip()
        data = json.loads(clean)

        amount = float(data.get("amount", 0))
        if amount <= 0:
            raise ValueError("amount must be positive")

        return {
            "amount": amount,
            "currency": str(data.get("currency", "AED")).upper(),
            "category": _normalize_category(str(data.get("category", "другое"))),
            "description": str(data.get("description", text.strip())),
        }
    except Exception as e:
        logger.warning("LLM extraction failed (%s), using regex fallback", e)
        return _regex_fallback(text)


def save_expense(telegram_id: int, text: str) -> dict:
    """Извлекает расход из текста и сохраняет в БД. Возвращает сохранённый dict."""
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
    """Возвращает текстовый отчёт по тратам за текущий месяц."""
    user = get_or_create_user(telegram_id, [])
    rows = get_total_by_category(user["id"], days=30)

    if not rows:
        return "За последние 30 дней трат не найдено."

    month_name = datetime.now().strftime("%B %Y")
    total = sum(r["total"] for r in rows)
    currency = rows[0]["currency"]

    lines = [f"📊 {month_name}\n", f"Всего: {total:.0f} {currency}\n", "По категориям:"]
    for row in rows:
        lines.append(f"  • {row['category']} — {row['total']:.0f} {row['currency']}")

    return "\n".join(lines)
