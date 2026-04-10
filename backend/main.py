from fastapi import FastAPI, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.future import select
from sqlalchemy import desc, func, update
import asyncio
import logging
from database import init_db, AsyncSessionLocal
from models import Article
from sync import sync_all_news

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="Next-Gen Inshorts API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    await init_db()
    # PRO MIGRATION: Update existing articles to the new Iran War category
    asyncio.create_task(migrate_old_data())
    # Start background sync task
    asyncio.create_task(background_sync())

async def migrate_old_data():
    async with AsyncSessionLocal() as db:
        logger.info("🛡️ Starting Data Migration for Iran War category...")
        # Keywords for finding old news to move
        en_keywords = ["iran", "israel", "hezbollah", "missile", "drone", "war", "conflict", "tehran", "tel aviv"]
        hi_keywords = ["ईरान", "इजराइल", "युद्ध", "मिसाइल", "ड्रोन", "संघर्ष", "तेहरान", "तेल अवीव"]
        
        all_kw = en_keywords + hi_keywords
        
        updated_count = 0
        try:
            # Check all articles
            result = await db.execute(select(Article))
            articles = result.scalars().all()
            for a in articles:
                search_text = (a.title + " " + (a.content or "")).lower()
                if any(kw in search_text for kw in all_kw):
                    if a.category != "Iran War":
                        a.category = "Iran War"
                        a.is_trending = 1
                        updated_count += 1
            await db.commit()
            logger.info(f"✅ Migration Complete. Moved {updated_count} articles to Iran War.")
        except Exception as e:
            logger.error(f"Migration failed: {e}")

async def background_sync():
    while True:
        try:
            await sync_all_news()
        except Exception as e:
            logging.error(f"Background sync error: {e}")
        await asyncio.sleep(300)

@app.get("/")
async def root():
    return {"message": "Inshorts News API is running"}

@app.get("/api/status")
async def get_status():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(Article).order_by(desc(Article.created_at)).limit(1))
        latest = result.scalars().first()
        count_result = await db.execute(select(func.count(Article.id)))
        total_count = count_result.scalar()
        return {
            "last_sync": latest.created_at.isoformat() if latest else None,
            "total_articles": total_count
        }

@app.get("/api/categories")
async def get_categories():
    return {
        "success": True,
        "data": ["All", "Iran War", "National", "Politics", "Technology", "Sports", "Entertainment", "Business", "International", "Lifestyle"]
    }

@app.get("/api/news")
async def get_news(category: str = "all", language: str = "en", limit: int = 10, offset: int = 0):
    async with AsyncSessionLocal() as db:
        query = select(Article)
        
        if category.lower() != "all":
            # Strip spaces and case-insensitive match
            query = query.filter(func.lower(func.trim(Article.category)) == category.lower().strip())
        
        query = query.filter(Article.language == language)
        query = query.order_by(desc(Article.is_trending), desc(Article.created_at)).offset(offset).limit(limit)
        result = await db.execute(query)
        articles = result.scalars().all()
        
        return {
            "success": True, 
            "data": [a.to_dict() for a in articles],
            "count": len(articles)
        }

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
鼓
