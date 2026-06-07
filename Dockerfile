FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# SQLite database lives outside the image so data survives container restarts
VOLUME ["/app/data"]
ENV DB_PATH=/app/data/personal_ai.db

CMD ["python", "-m", "bot.main"]
