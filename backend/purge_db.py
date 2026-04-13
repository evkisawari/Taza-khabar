"""
Run this ONCE on AWS after deployment to wipe old junk data.
Usage: python purge_db.py
"""
import asyncio
from database import AsyncSessionLocal
from models import Article
from sqlalchemy import delete

async def purge():
    print("🗑️  Purging ALL old articles from database...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(delete(Article))
        await db.commit()
        print(f"✅ Done. Deleted all articles. Fresh sync will begin automatically.")

asyncio.run(purge())
