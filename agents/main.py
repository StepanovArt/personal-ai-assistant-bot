import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from database.db import init_db, get_or_create_user, update_user_interests
from trendwatcher import graph  # ← поменяй на имя своего файла с агентом

# ============================================================
# НАСТРОЙКИ
# ============================================================
MY_TELEGRAM_ID = 12345
MY_INTERESTS = ["AI","Машинное обучение",'ИИ' ]   # ← ПОМЕНЯЙ на свои интересы

# ============================================================
# ПОДГОТОВКА БД
# ============================================================

print("🔧 Готовлю БД...")
init_db()

# Создаём юзера если его нет
user = get_or_create_user(MY_TELEGRAM_ID, [])
print(f"✅ Юзер: id={user['id']}, telegram_id={MY_TELEGRAM_ID}")

# Обновляем интересы
update_user_interests(MY_TELEGRAM_ID, MY_INTERESTS)
print(f"✅ Интересы: {MY_INTERESTS}")

# ============================================================
# ЗАПУСК АГЕНТА
# ============================================================
print("\n🚀 Запускаю агента...\n")

initial_state = {"telegram_id": MY_TELEGRAM_ID}

for chunk in graph.stream(initial_state):
    for node_name, node_output in chunk.items():
        print(f"\n{'=' * 60}")
        print(f"✅ Узел завершён: {node_name}")
        print(f"{'=' * 60}")

        # ЗАЩИТА: если узел не вернул обновление state
        if node_output is None:
            print("  (узел не изменил state)")
            continue

        for key, value in node_output.items():
            if isinstance(value, list):
                print(f"  {key}: {len(value)} элементов")
            else:
                print(f"  {key}: {value}")

print("\n🎉 Готово! Смотри файл trends_*.md")