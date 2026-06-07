import asyncio
import os
import certifi

os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

from fastapi import HTTPException, FastAPI
from pydantic import BaseModel
from agents.trendwatcher import graph

app = FastAPI(
    title="TrendWatcher API",
    description="REST API для агента отслеживания трендов",
    version="0.1.0",
)


class TrendRequest(BaseModel):
    telegram_id: int
    interests: list[str]


class ArticleItem(BaseModel):
    title: str
    url: str
    source: str
    text: str


class TrendResponse(BaseModel):
    count: int
    articles: list[ArticleItem]


@app.post("/trends", response_model=TrendResponse)
async def get_trends(request: TrendRequest):
    if not request.interests:
        raise HTTPException(status_code=400, detail="interests cannot be empty")

    result = await asyncio.to_thread(
        graph.invoke,
        {"telegram_id": request.telegram_id, "user_interests": request.interests},
    )

    raw = result.get("articles_with_text", [])
    articles = [
        ArticleItem(
            title=a.get("title", ""),
            url=a.get("url", ""),
            source=a.get("source", ""),
            text=a.get("text", ""),
        )
        for a in raw
    ]
    return TrendResponse(count=len(articles), articles=articles)
