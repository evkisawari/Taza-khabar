import asyncio
from database import engine, init_db, AsyncSessionLocal
from models import Base, Article
from sync import sync_all_news

async def rebuild_db():
    print("Dropping old table structure...")
    async with engine.begin() as conn:
        # Force drop and recreate
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    print("New structure built with 'language' and 'category' support.")
    
    print("Performing fresh sync...")
    await sync_all_news()
    print("SUCCESS: Your database is now perfectly bilingual and categorized!")

if __name__ == "__main__":
    asyncio.run(rebuild_db())
