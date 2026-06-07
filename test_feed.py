import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

import feedparser
import urllib.request

URL = "https://news.google.com/rss/search?q=NVIDIA+AI+acceleration+hardware+news&hl=en&gl=US&ceid=US:en"

print("="*70)
print("ТЕСТ 1: feedparser БЕЗ User-Agent")
print("="*70)
result1 = feedparser.parse(URL)
print(f"  Статус: {result1.get('status')}")
print(f"  Bozo: {result1.bozo}")
if result1.bozo:
    print(f"  Ошибка: {result1.bozo_exception}")
print(f"  Записей: {len(result1.entries)}")

print("\n" + "="*70)
print("ТЕСТ 2: feedparser С User-Agent")
print("="*70)
result2 = feedparser.parse(
    URL,
    agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"
)
print(f"  Статус: {result2.get('status')}")
print(f"  Bozo: {result2.bozo}")
if result2.bozo:
    print(f"  Ошибка: {result2.bozo_exception}")
print(f"  Записей: {len(result2.entries)}")

print("\n" + "="*70)
print("ТЕСТ 3: Сырой HTTP запрос через urllib")
print("="*70)
try:
    req = urllib.request.Request(URL, headers={
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'
    })
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        print(f"  HTTP статус: {resp.status}")
        print(f"  Размер: {len(body)} байт")
        print(f"  Первые 300 символов:")
        print(f"  {body[:300]}")
        print(f"\n  Содержит '<item>': {'<item>' in body}")
        print(f"  Содержит '<entry>': {'<entry>' in body}")
except Exception as e:
    print(f"  ОШИБКА: {type(e).__name__}: {e}")

print("\n" + "="*70)
print("ТЕСТ 4: feedparser с готовой строкой XML (если ТЕСТ 3 получил данные)")
print("="*70)
try:
    result4 = feedparser.parse(body)
    print(f"  Bozo: {result4.bozo}")
    if result4.bozo:
        print(f"  Ошибка: {result4.bozo_exception}")
    print(f"  Записей: {len(result4.entries)}")
    if result4.entries:
        print(f"  Первая запись: {result4.entries[0].get('title', 'нет title')[:80]}")
except Exception as e:
    print(f"  ОШИБКА: {e}")