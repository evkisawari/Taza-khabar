import asyncio
import logging
from database import AsyncSessionLocal, init_db
from models import Article
from sqlalchemy import delete
from sync import sync_all_news

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def reset_database():
    print("Starting Deep Database Reset...")
    
    # 1. Initialize DB structure
    await init_db()
    
    async with AsyncSessionLocal() as db:
        try:
            # 2. Wipe everything
            print("Wiping 'articles' table...")
            await db.execute(delete(Article))
            await db.commit()
            print("Database is now EMPTY.")
            
            # 3. Fresh Sync
            print("Starting fresh Bilingual Sync...")
            await sync_all_news()
            print("Fresh news added to DB successfully!")
            
        except Exception as e:
            print(f"❌ Reset failed: {e}")
            await db.rollback()

if __name__ == "__main__":
    asyncio.run(reset_database())
