import logging
import feedparser
import httpx
import asyncio
import re
import html as html_parser
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from database import AsyncSessionLocal
from models import Article
from sqlalchemy.future import select
from sqlalchemy import or_, func, desc
import os
import google.generativeai as genai
import trafilatura
from dotenv import load_dotenv
import threading
import concurrent.futures

# Load environment variables
load_dotenv()

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync")

# --- PRO MAX AI ENGINE ---
def call_gemini(prompt):
    """
    NEW 2026 SDK CALL: 
    This uses the self-healing discovery logic to bypass 404 errors.
    """
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ No GEMINI_API_KEY found in environment!")
        return None
        
    try:
        genai.configure(api_key=api_key)
        
        # 1. AUTO-DISCOVERY: Find the best model your account allows
        # This prevents the '404 Model Not Found' error permanently
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Priority mapping (1.5 Flash is now Top Stable Priority)
        priority = ['gemini-1.5-flash', 'gemini-1.5-flash-8b', 'gemini-1.0-pro', 'gemini-2.0-flash']
        
        selected = None
        for p in priority:
            for a in available:
                if p in a:
                    # VALIDATION PING: Quick check to see if it's REALLY available
                    try:
                        m_test = genai.GenerativeModel(a)
                        m_test.generate_content("ping")
                        selected = a
                        break
                    except:
                        continue
            if selected: break
            
        target_model = selected if selected else (available[0] if available else 'models/gemini-1.5-flash')

        logger.info(f"🔍 Discovered model: {target_model}")
        
        model = genai.GenerativeModel(target_model)
        response = model.generate_content(prompt)
        
        if response and hasattr(response, 'text'):
            return response.text.strip()
            
    except Exception as e:
        if "429" in str(e):
            logger.warning("⚠️ Quota limit hit! Skipping this article.")
        elif "API_KEY_INVALID" in str(e) or "403" in str(e):
            logger.error("🔥 CRITICAL: Your API Key is BLOCKED or INVALID. Please get a new one at ai.google.dev")
        else:
            logger.error(f"❌ AI Error: {e}")
    return None

def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    cleantext = re.sub(cleanr, '', raw_html)
    return html_parser.unescape(cleantext).strip()

def clean_title(title):
    if not title: return ""
    title = html_parser.unescape(title)
    title = re.sub(r'\s*\|\s*.*$', '', title)
    title = re.sub(r'\s*-\s*.*$', '', title)
    return title.strip()

executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

def scrape_with_trafilatura(url):
    """Deep Scraping with Stealth Headers"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36",
        "Referer": "https://www.google.com/"
    }
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                return trafilatura.extract(resp.text, include_comments=False)
    except:
        return None
    return None

async def fetch_article_body(url):
    loop = asyncio.get_event_loop()
    try:
        body = await loop.run_in_executor(executor, scrape_with_trafilatura, url)
        return body if body and len(body) > 200 else None
    except:
        return None

async def fetch_direct_rss(source, db):
    articles = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36'}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            response = await client.get(source['url'])
            feed = feedparser.parse(response.text)
            
            # Increased to 30 articles! We can do this now because we save AI quota
            for entry in feed.entries[:30]: 
                article_url = entry.get('link')
                if not article_url: continue
                
                cleaned_title = clean_title(entry.get('title', ''))
                art_id = f"{article_url}_{cleaned_title}"
                
                # PRE-FLIGHT CHECK: Let's not waste our Gemini Quota if we already have it!
                exists = await db.execute(select(Article).where(Article.id == art_id))
                if exists.scalars().first():
                    continue # Skip! Already in database
                
                # Scraping
                full_body = await fetch_article_body(article_url)
                clean_content = full_body if full_body else clean_html(entry.get('summary', ''))
                
                if len(clean_content) < 200: continue

                lang_name = 'Hindi' if source.get('language') == 'hi' else 'English'
                # PRO MAX CONSOLIDATED PROMPT
                prompt = f"""
                You are a Chief News Editor writing for a premium news app.
                1. QUALITY: If content is JSON junk, broken, or not news, reply ONLY 'REJECT'.
                2. LANGUAGE AND TONE: Write a HIGH-QUALITY, engaging, and professional 60-70 word summary strictly in {lang_name}. Do NOT mix languages.
                3. NO BRANDS: Do NOT mention any news organizations (AajTak, BBC, Reuters, News18, NDTV, Bhaskar, etc.).
                4. NO META: Do not mention reporters, authors, or reading time.
                
                Content: {clean_content[:2000]}
                """
                
                # Single API Call
                ai_result = call_gemini(prompt)
                
                if not ai_result or "REJECT" in ai_result.upper():
                    continue

                # Final cleaning
                summary = ai_result
                blacklist = ["AajTak", "News18", "BBC", "Amar Ujala", "Navbharat Times", "DW.com", "Bhaskar"]
                for b in blacklist:
                    summary = re.sub(re.escape(b), "", summary, flags=re.IGNORECASE)
                
                new_art = Article(
                    id=art_id,
                    title=cleaned_title,
                    content=summary.strip(),
                    image_url=entry.get('media_content', [{}])[0].get('url', 'https://images.unsplash.com/photo-1504711434969-e33886168f5c'),
                    source_name=source['name'],
                    source_url=article_url,
                    category=source['category'],
                    language=source.get('language', 'en'),
                    created_at=datetime.utcnow()
                )
                articles.append(new_art)
                
                # Because we verified it's new, we commit it immediately
                db.add(new_art)
                await db.commit()
                
                # BREATHING ROOM FOR QUOTA (Max 10 requests per minute)
                await asyncio.sleep(6)
                
        return articles
    except Exception as e:
        logger.error(f"Error fetching {source['name']}: {e}")
        return []

async def sync_all_news():
    logger.info("Starting Pro Max News Sync...")
    sources = [
        {'name': 'Google News National', 'url': 'https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en', 'category': 'National', 'language': 'en'},
        {'name': 'Google News World', 'url': 'https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en', 'category': 'International', 'language': 'en'},
        {'name': 'Bhaskar National', 'url': 'https://www.bhaskar.com/rss-v1--category-1061.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Aaj Tak', 'url': 'https://www.aajtak.in/rssfeeds/?id=home', 'category': 'National', 'language': 'hi'}
    ]
    
    async with AsyncSessionLocal() as db:
        for source in sources:
            logger.info(f"Processing {source['name']}...")
            await fetch_direct_rss(source, db)
    logger.info("✅ Sync Complete!")

if __name__ == "__main__":
    asyncio.run(sync_all_news())
