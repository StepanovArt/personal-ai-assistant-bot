import asyncio
from fastapi import HTTPException,FastAPI
from pydantic import BaseModel
from agents.trendwatcher import graph
import os
import certifi
os.environ['SSL_CERT_FILE'] = certifi.where()
os.environ['REQUESTS_CA_BUNDLE'] = certifi.where()

# СОЗДАНИЕ ПРИЛОЖЕНИЯ
app=FastAPI(title="TrendWatcher API",
     description="REST API для агента отслеживания трендов",
     version="0.1.0")
# PYDANTIC MODELS
class TrendRequest(BaseModel):
    telegram_id: int
    interests: list[str]

class SummartItem(BaseModel):
    title: str
    url: str
    source: str
    summary: str

class TrendResponse(BaseModel):
    count:int
    summaries:list[SummartItem]


# ENDPOINTS
@app.post('/trends',response_model=TrendResponse)
async def get_trends(request:TrendRequest):
    if not request.interests:
        raise HTTPException(status_code=400 , detail='interests cannot be empty')

    result=await asyncio.to_thread(graph.invoke,{
             "telegram_id": request.telegram_id, "user_interests": request.interests
          })
    summaries = result.get('summaries',[])
    return  TrendResponse(count=len(summaries),summaries=summaries)
