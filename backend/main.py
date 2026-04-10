from fastapi import FastAPI, BackgroundTasks, Query
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.future import select
from sqlalchemy import desc, or_
from database import engine, Base, AsyncSessionLocal
from models import Article
from sync import sync_all_news
import asyncio
from datetime import datetime, timedelta

app = FastAPI(title="Taza Khabar API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    asyncio.create_task(background_sync())

async def background_sync():
    while True:
        try:
            await sync_all_news()
        except Exception as e:
            print(f"Sync error: {e}")
        await asyncio.sleep(300) # Sync every 5 minutes

@app.get("/api/news")
async def get_news(
    category: str = 'all',
    language: str = 'en',
    limit: int = 20,
    offset: int = 0
):
    async with AsyncSessionLocal() as db:
        query = select(Article)
        
        # Bilingual logic: filter by language correctly
        query = query.where(Article.language == language)
        
        if category != 'all':
            query = query.where(Article.category.ilike(category))
            
        # Priority sort: Trending first, then most recent
        query = query.order_by(desc(Article.is_trending), desc(Article.created_at))
        
        result = await db.execute(query.offset(offset).limit(limit))
        articles = result.scalars().all()
        return {"success": True, "data": articles}

@app.get("/api/categories")
async def get_categories():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Article.category).distinct())
        cats = [c[0] for c in result.all()]
        if 'all' not in cats: cats.insert(0, 'all')
        return {"success": True, "data": cats}

@app.post("/api/sync")
async def trigger_sync(background_tasks: BackgroundTasks):
    background_tasks.add_task(sync_all_news)
    return {"success": True, "message": "Manual sync initiated"}

@app.get("/api/status")
async def get_status():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Article))
        total = len(result.scalars().all())
        return {"last_sync": datetime.now().isoformat(), "total_articles": total}
