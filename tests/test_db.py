import pytest
from database.db import (
    get_or_create_user,
    add_expense,
    get_expenses,
    get_total_by_category,
    filter_unseen_urls,
    mark_news_shown,
    is_news_shown,
)


# ── users ──────────────────────────────────────────────────────────────────────

def test_get_or_create_user_creates(test_db):
    user = get_or_create_user(11111, ["AI"])
    assert user["telegram_id"] == 11111
    assert "id" in user


def test_get_or_create_user_idempotent(test_db):
    u1 = get_or_create_user(22222, ["AI"])
    u2 = get_or_create_user(22222, ["AI"])
    assert u1["id"] == u2["id"]


# ── shown_news ────────────────────────────────────────────────────────────────

def test_mark_and_check_shown(test_db):
    user = get_or_create_user(33333, [])
    url = "https://example.com/news/1"
    assert not is_news_shown(user["id"], url)
    mark_news_shown(user["id"], url, "Test Title")
    assert is_news_shown(user["id"], url)


def test_filter_unseen_returns_only_new(test_db):
    user = get_or_create_user(44444, [])
    seen_url = "https://example.com/old"
    new_url = "https://example.com/new"
    mark_news_shown(user["id"], seen_url)

    unseen = filter_unseen_urls(user["id"], [seen_url, new_url])
    assert unseen == {new_url}


def test_filter_unseen_empty_input(test_db):
    user = get_or_create_user(55555, [])
    assert filter_unseen_urls(user["id"], []) == set()


# ── expenses ──────────────────────────────────────────────────────────────────

def test_add_and_get_expense(test_db):
    user = get_or_create_user(66666, [])
    add_expense(user["id"], 50.0, "AED", "транспорт", "такси")

    expenses = get_expenses(user["id"], days=30)
    assert len(expenses) == 1
    assert expenses[0]["amount"] == 50.0
    assert expenses[0]["category"] == "транспорт"


def test_get_expenses_filters_by_user(test_db):
    u1 = get_or_create_user(77777, [])
    u2 = get_or_create_user(88888, [])
    add_expense(u1["id"], 10.0, "AED", "еда", "кола")
    add_expense(u2["id"], 20.0, "AED", "еда", "кофе")

    assert len(get_expenses(u1["id"], days=30)) == 1
    assert len(get_expenses(u2["id"], days=30)) == 1


def test_get_total_by_category(test_db):
    user = get_or_create_user(99999, [])
    add_expense(user["id"], 30.0, "AED", "еда", "обед")
    add_expense(user["id"], 20.0, "AED", "еда", "ужин")
    add_expense(user["id"], 50.0, "AED", "транспорт", "такси")

    totals = get_total_by_category(user["id"], days=30)
    by_cat = {r["category"]: r["total"] for r in totals}

    assert by_cat["еда"] == 50.0
    assert by_cat["транспорт"] == 50.0


def test_get_total_by_category_empty(test_db):
    user = get_or_create_user(10001, [])
    assert get_total_by_category(user["id"], days=30) == []


def test_get_expenses_empty_returns_list(test_db):
    user = get_or_create_user(10002, [])
    assert get_expenses(user["id"], days=30) == []
