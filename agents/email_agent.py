import imaplib
import email
from email.header import decode_header
import os
from dotenv import load_dotenv
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from agents.llm import call_ollama
import re
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

# КОНФИГ
load_dotenv()
GMAIL_USER = os.getenv('GMAIL_USER')
GMAIL_PASSWORD = os.getenv('GMAIL_APP_PASSWORD')
IMAP_SERVER = "imap.gmail.com"

SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587  # TLS


# ОСНОВНОЙ ХЕЛПЕР
def fetch_unread_emails(period: str) -> list[dict]:
    """
    Получает непрочитанные письма из Gmail inbox за указанный период.

    Args:
        period: строка вида "2d", "1h", "30m"

    Returns:
        список словарей: [{"from": ..., "subject": ..., "date": ..., "body": ...}, ...]
    """
    # 1 find start date
    now = datetime.now()
    value = int(period[:-1])
    unit = period[-1]
    if unit == 'd':
        since = (now - timedelta(days=value)).strftime("%d-%b-%Y")
    elif unit == 'h':
        since = (now - timedelta(hours=value)).strftime("%d-%b-%Y")
    else:
        raise TypeError('days and hours only(')
    # 2 connect to the mail
    imap = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
    imap.login(GMAIL_USER, GMAIL_PASSWORD)
    print("Connected!")
    imap.select('inbox')

    # 3 find unreaded mails
    criteria = f'(UNSEEN SINCE "{since}")'
    status, message_ids = imap.search(None, criteria)
    msg_id = message_ids[0].split()

    lst_of_letters = []
    for i in msg_id:
        status, data = imap.fetch(i, 'BODY.PEEK[]')
        raw_email = data[0][1]
        msg = email.message_from_bytes(raw_email)

        lst_of_letters.append({
            "Message_id": i.decode(),
            "From": decode_mine_helper(msg.get('From')),
            "Subject": decode_mine_helper(msg.get("Subject")),
            "Count_attachments": count_attachments(msg),
            "Name_attachments": get_count_attachment_name(msg)})

    imap.close()
    imap.logout()
    return lst_of_letters


def count_attachments(raw_file: str) -> int :
    count = 0
    for i in raw_file.walk():
        if i.get_filename():
            count += 1
    if count > 0:
        return count
    return 0


def get_count_attachment_name(raw_file: str) -> list[str]:
    files = []
    for i in raw_file.walk():
        filename = i.get_filename()
        if filename:
            files.append(filename)
    if len(files) > 0:
        return files
    return ""


def decode_mine_helper(raw_helper: str) -> str:
    """
    Декодирует email header (тема может быть в UTF-8/Base64).
    Пример: "=?UTF-8?B?0J/RgNC40LLQtdGCIQ==?=" → "Привет!"
    """

    parts = email.header.decode_header(raw_helper)
    decodede_parts = ''
    for part, encoding in parts:
        if isinstance(part, bytes):
            decodede_parts += part.decode(encoding or "utf-8")
        else:
            decodede_parts += part

    return decodede_parts


def extract_body(msg) -> str:  # Превращает структуру письма в чистый текст
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if payload:
            charset = msg.get_content_charset()
            return payload.decode(charset, errors='replace')
        return ''
    plain_text = ''
    html_text = ''

    for part in msg.walk():
        content_type = part.get_content_type()
        content_disposition = str(part.get("Content-Disposition", ""))

        if "attachment" in content_disposition:
            continue

        payload = part.get_payload(decode=True)
        if not payload:
            continue

        charset = part.get_content_charset() or 'utf-8'
        decoded = payload.decode(charset, errors='replace')

        if content_type == "text/plain":
            plain_text = decoded
            break  # нашли plain — больше не ищем
        elif content_type == "text/html" and not html_text:
            html_text = decoded

    # ВОЗВРАТ — приоритет plain, иначе html → text
    if plain_text:
        return plain_text.strip()
    if html_text:
        soup = BeautifulSoup(html_text, 'html.parser')
        return soup.get_text(separator='\n').strip()
    return ''


def fetch_email_body(message_id: str) -> str:  # Загружает текст ОДНОГО конкретного письма по его ID.
    # 2 connect to the mail
    imap = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
    imap.login(GMAIL_USER, GMAIL_PASSWORD)
    print("Connected!")
    imap.select('inbox')

    status, data = imap.fetch(message_id.encode(), 'BODY.PEEK[]')
    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)
    body = extract_body(msg)
    imap.close()
    imap.logout()
    return body


def analyze_email(message_id: str) -> str:
    text = fetch_email_body(message_id)
    prompt = f"""
    Ты — профессиональный AI email-ассистент для Telegram-бота.

    Твоя задача:
    1. Прочитать письмо.
    2. Сделать краткое и полезное саммари на русском языке.
    3. Сгенерировать черновик ответа.

    ВАЖНЫЕ ПРАВИЛА:

    === ДЛЯ SUMMARY ===
    - SUMMARY ВСЕГДА должен быть на русском языке.
    - Если оригинальное письмо написано НЕ на русском языке, в начале SUMMARY добавь:
      "Переведено с английского:"
    - Если письмо уже на русском — НЕ добавляй эту строку.
    - Саммари должно быть коротким: 3–5 предложений максимум.
    - Удали приветствия, подписи, рекламу и лишний шум.
    - Выдели:
      - главную мысль
      - важные детали
      - дедлайны
      - что требуется от пользователя
    - Если письмо выглядит как реклама/спам/авторассылка — кратко укажи это.

    === ДЛЯ DRAFT_REPLY ===
    - Ответ должен быть на ТОМ ЖЕ ЯЗЫКЕ, что и оригинальное письмо.
    - Ответ должен быть:
      - вежливым
      - профессиональным
      - кратким
      - без лишней воды
    - Если письмо не требует ответа (уведомление, рассылка, реклама и т.д.), напиши строго:
      "ОТВЕТ НЕ НУЖЕН"
    - Не выдумывай факты, которых нет в письме.
    - Не добавляй лишних объяснений от себя.

    ПИСЬМО:
    \"\"\"
    {text}
    \"\"\"

    ФОРМАТ ОТВЕТА (СТРОГО СОБЛЮДАЙ):

    SUMMARY:
    [саммари здесь]

    DRAFT_REPLY:
    [черновик ответа здесь]

    Никаких дополнительных комментариев.
    Никаких пояснений.
    Только указанный формат.
    """

    answer = call_ollama(prompt)

    try:
        if "DRAFT_REPLY:" not in answer:
            return {"summary": answer, "draft_reply": "(не удалось сгенерировать ответ)"}
        parts = answer.split("DRAFT_REPLY:")
        summary_part = parts[0].replace("SUMMARY:", "").strip()
        reply_part = parts[1].strip()
        return {"summary": summary_part, "draft_reply": reply_part,
                }
    except Exception as e:
        return {
            "summary": "(ошибка парсинга ответа LLM)",
            "draft_reply": "",
        }



def send_email(to: str, subject: str, body: str, in_reply_to: str = None) -> bool:
    """
    Отправляет email через Gmail SMTP.

    Returns:
        True если успешно, False если ошибка
    """
    try:
        # Создаём сообщение
        msg = MIMEMultipart()
        msg['From'] = GMAIL_USER
        msg['To'] = to
        msg['Subject'] = subject

        # Добавляем тело (plain text)
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        # Подключаемся к SMTP с TLS
        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(GMAIL_USER, GMAIL_PASSWORD)

        # Отправляем
        server.send_message(msg)
        server.quit()

        return True

    except Exception as e:
        print(f"❌ Ошибка отправки: {e}")
        return False




def extract_email_address(from_field: str) -> str:
    """
    Из 'Вася <vasya@gmail.com>' вытаскивает 'vasya@gmail.com'.
    Если просто email — возвращает как есть.
    """
    match = re.search(r'<(.+?)>', from_field)
    if match:
        return match.group(1)
    return from_field.strip()


if __name__ == "__main__":
    # ====== ТЕСТ send_email ======
    print("\n" + "=" * 60)
    print("📨 Тестирую отправку самому себе...")
    print("=" * 60)

    success = send_email(
        to=GMAIL_USER,  # себе!
        subject="Тест от моего бота",
        body="Привет! Это тестовое письмо от EmailAgent.\n\nЕсли получил — значит SMTP работает 🎉"
    )

    if success:
        print("✅ Отправлено! Проверь свой инбокс через 10-30 секунд.")
    else:
        print("❌ Ошибка отправки.")

