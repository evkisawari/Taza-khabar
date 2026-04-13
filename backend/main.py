from fastapi import FastAPI, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.future import select
from sqlalchemy import desc, func
import asyncio
import logging
from database import init_db, AsyncSessionLocal
from models import Article
from sync import sync_all_news

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# --- CORE ASGI APP ---
app = FastAPI(title="Taza Khabar Production API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await init_db()
    asyncio.create_task(background_sync())

@app.get("/")
async def root():
    return {"message": "Taza Khabar API is Online"}

async def background_sync():
    while True:
        try:
            await sync_all_news()
        except Exception as e:
            logging.error(f"Background sync error: {e}")
        # Wait 1 hour (3600 seconds) between syncs to conserve Groq AI tokens
        await asyncio.sleep(3600)

@app.get("/api/status")
async def get_status():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Article).order_by(desc(Article.created_at)).limit(1))
        latest = result.scalars().first()
        count_result = await db.execute(select(func.count(Article.id)))
        total_count = count_result.scalar()
        return {
            "success": True,
            "data": {
                "last_sync": latest.created_at.isoformat() if latest else None,
                "total_articles": total_count
            }
        }

@app.get("/api/categories")
async def get_categories():
    return {
        "success": True,
        "data": ["All", "National", "Politics", "War", "International"]
    }

@app.post("/api/sync")
async def trigger_sync():
    asyncio.create_task(sync_all_news())
    return {"message": "Sync started in background"}

@app.get("/api/news")
async def get_news(category: str = "all", language: str = "en", limit: int = 10, offset: int = 0):
    async with AsyncSessionLocal() as db:
        query = select(Article)
        
        # STRICT LANGUAGE FILTER
        lang_filter = language.lower()
        if lang_filter != "all":
            query = query.filter(Article.language == lang_filter)
            
        # CATEGORY FILTER
        if category.lower() != "all":
            query = query.filter(func.lower(Article.category) == category.lower())
            
        query = query.order_by(desc(Article.created_at)).offset(offset).limit(limit)
        
        result = await db.execute(query)
        articles = result.scalars().all()
        
        return {
            "success": True, 
            "data": [a.to_dict() for a in articles],
            "count": len(articles)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
