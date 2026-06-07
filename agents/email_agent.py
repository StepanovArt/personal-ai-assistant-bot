import email
import imaplib
import logging
import re
import smtplib

logger = logging.getLogger(__name__)
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from bs4 import BeautifulSoup

from agents.llm import call_llm

IMAP_SERVER = "imap.gmail.com"
SMTP_SERVER = "smtp.gmail.com"
SMTP_PORT = 587


def fetch_unread_emails(period: str, gmail_user: str, gmail_password: str) -> list[dict]:
    """
    Получает непрочитанные письма из Gmail inbox за указанный период.

    Args:
        period: строка вида "1d", "1h", "12h"
        gmail_user: адрес Gmail
        gmail_password: Google App Password
    """
    now = datetime.now()
    value = int(period[:-1])
    unit = period[-1]
    if unit == 'd':
        since = (now - timedelta(days=value)).strftime("%d-%b-%Y")
    elif unit == 'h':
        since = (now - timedelta(hours=value)).strftime("%d-%b-%Y")
    else:
        raise TypeError('days and hours only(')

    imap = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
    imap.login(gmail_user, gmail_password)
    imap.select('inbox')

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
            "From": decode_mime_header(msg.get('From')),
            "Subject": decode_mime_header(msg.get("Subject")),
            "Count_attachments": count_attachments(msg),
            "Name_attachments": get_attachment_names(msg),
        })

    imap.close()
    imap.logout()
    return lst_of_letters


def fetch_email_body(message_id: str, gmail_user: str, gmail_password: str) -> str:
    """Загружает тело одного письма по его ID."""
    imap = imaplib.IMAP4_SSL(IMAP_SERVER, 993)
    imap.login(gmail_user, gmail_password)
    imap.select('inbox')

    status, data = imap.fetch(message_id.encode(), 'BODY.PEEK[]')
    raw_email = data[0][1]
    msg = email.message_from_bytes(raw_email)
    body = extract_body(msg)

    imap.close()
    imap.logout()
    return body


def analyze_email(message_id: str, gmail_user: str, gmail_password: str) -> dict:
    """Загружает письмо, делает саммари и генерирует черновик ответа."""
    text = fetch_email_body(message_id, gmail_user, gmail_password)
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
    - Ответ должен быть вежливым, профессиональным, кратким.
    - Если письмо не требует ответа, напиши строго: "ОТВЕТ НЕ НУЖЕН"

    ПИСЬМО:
    \"\"\"
    {text}
    \"\"\"

    ФОРМАТ ОТВЕТА (СТРОГО СОБЛЮДАЙ):

    SUMMARY:
    [саммари здесь]

    DRAFT_REPLY:
    [черновик ответа здесь]
    """

    answer = call_llm(prompt)

    try:
        if "DRAFT_REPLY:" not in answer:
            return {"summary": answer, "draft_reply": "(не удалось сгенерировать ответ)"}
        parts = answer.split("DRAFT_REPLY:")
        return {
            "summary": parts[0].replace("SUMMARY:", "").strip(),
            "draft_reply": parts[1].strip(),
        }
    except Exception:
        return {"summary": "(ошибка парсинга ответа LLM)", "draft_reply": ""}


def send_email(
    to: str, subject: str, body: str,
    gmail_user: str, gmail_password: str,
) -> bool:
    """Отправляет email через Gmail SMTP. Возвращает True если успешно."""
    try:
        msg = MIMEMultipart()
        msg['From'] = gmail_user
        msg['To'] = to
        msg['Subject'] = subject
        msg.attach(MIMEText(body, 'plain', 'utf-8'))

        server = smtplib.SMTP(SMTP_SERVER, SMTP_PORT)
        server.starttls()
        server.login(gmail_user, gmail_password)
        server.send_message(msg)
        server.quit()
        return True
    except Exception as e:
        logger.error("Ошибка отправки email: %s", e)
        return False


def extract_email_address(from_field: str) -> str:
    """Из 'Вася <vasya@gmail.com>' вытаскивает 'vasya@gmail.com'."""
    match = re.search(r'<(.+?)>', from_field)
    return match.group(1) if match else from_field.strip()


# ── helpers ───────────────────────────────────────────────────────────────────

def decode_mime_header(raw: str) -> str:
    parts = email.header.decode_header(raw or "")
    result = ""
    for part, encoding in parts:
        if isinstance(part, bytes):
            result += part.decode(encoding or "utf-8")
        else:
            result += part
    return result


def count_attachments(msg) -> int:
    return sum(1 for part in msg.walk() if part.get_filename())


def get_attachment_names(msg) -> list[str]:
    return [part.get_filename() for part in msg.walk() if part.get_filename()]


def extract_body(msg) -> str:
    if not msg.is_multipart():
        payload = msg.get_payload(decode=True)
        if payload:
            return payload.decode(msg.get_content_charset() or "utf-8", errors='replace')
        return ''

    plain_text = ''
    html_text = ''
    for part in msg.walk():
        content_type = part.get_content_type()
        if "attachment" in str(part.get("Content-Disposition", "")):
            continue
        payload = part.get_payload(decode=True)
        if not payload:
            continue
        decoded = payload.decode(part.get_content_charset() or 'utf-8', errors='replace')
        if content_type == "text/plain":
            plain_text = decoded
            break
        elif content_type == "text/html" and not html_text:
            html_text = decoded

    if plain_text:
        return plain_text.strip()
    if html_text:
        return BeautifulSoup(html_text, 'html.parser').get_text(separator='\n').strip()
    return ''
