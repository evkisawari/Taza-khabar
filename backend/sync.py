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
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        logger.error("❌ No GEMINI_API_KEY found!")
        return None
        
    try:
        genai.configure(api_key=api_key)
        
        # Self-Healing Discovery Logic
        available = [m.name for m in genai.list_models() if 'generateContent' in m.supported_generation_methods]
        
        # Priority mapping (Flexible discovery)
        priority = ['gemini-3-flash', 'gemini-2.5-flash', 'gemini-2.0-flash', 'gemini-1.5-flash', 'gemini-pro']
        
        selected = None
        for p in priority:
            for a in available:
                if p in a:
                    selected = a
                    break
            if selected: break
            
        target_model = selected if selected else (available[0] if available else 'models/gemini-1.5-flash')
        logger.info(f"🔍 Using Model: {target_model}")
        
        model = genai.GenerativeModel(target_model)
        response = model.generate_content(prompt)
        
        if response and hasattr(response, 'text'):
            return response.text.strip()
            
    except Exception as e:
        logger.error(f"❌ AI Error: {e}")
    return None

def clean_html(raw_html):
    if not raw_html: return ""
    # Remove HTML tags and common entities
    cleanr = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    cleantext = re.sub(cleanr, ' ', raw_html)
    return html_parser.unescape(cleantext).strip()

def clean_title(title):
    if not title: return ""
    title = html_parser.unescape(title)
    # Remove source names from titles (e.g., "Title - BBC News")
    title = re.sub(r'\s*[\-\|]\s*.*$', '', title)
    return title.strip()

executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

def scrape_with_trafilatura(url):
    """Deep Scraping with Browser Headers"""
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com/"
    }
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = client.get(url)
            if resp.status_code == 200:
                # Try Trafilatura first
                content = trafilatura.extract(resp.text, include_comments=False)
                if content and len(content) > 300:
                    return content
                
                # BS4 Fallback (More aggressive for stubborn sites)
                soup = BeautifulSoup(resp.text, 'lxml')
                for s in soup(["script", "style", "nav", "footer", "header", "aside"]):
                    s.decompose()
                paragraphs = soup.find_all('p')
                text = " ".join([p.text.strip() for p in paragraphs if len(p.text.strip()) > 50])
                return text if len(text) > 300 else None
    except Exception as e:
        logger.warning(f"Scrape failed for {url}: {e}")
        return None
    return None

async def fetch_article_body(url):
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(executor, scrape_with_trafilatura, url)
    except:
        return None

async def fetch_direct_rss(source, db):
    articles_found = 0
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            response = await client.get(source['url'])
            feed = feedparser.parse(response.text)
            
            for entry in feed.entries[:25]: # Fresh 25 articles per source
                article_url = entry.get('link')
                if not article_url: continue
                
                title = clean_title(entry.get('title', ''))
                art_id = f"{article_url}_{title}"
                
                # Check duplication
                exists = await db.execute(select(Article).where(Article.id == art_id))
                if exists.scalars().first():
                    continue 
                
                # Deep Scrape
                full_body = await fetch_article_body(article_url)
                
                # Content Prep
                rss_summary = clean_html(entry.get('summary', ''))
                clean_content = full_body if full_body else rss_summary
                
                if len(clean_content) < 150: 
                    logger.debug(f"Skipping {title} - Content too short ({len(clean_content)})")
                    continue

                lang_name = 'Hindi' if source.get('language') == 'hi' else 'English'
                
                prompt = f"""
                You are a Professional News Summarizer for a premium app.
                1. TASK: Summarize the following news content in exactly 60-70 words.
                2. LANGUAGE: The summary MUST be entirely in {lang_name}.
                3. TONE: Professional, objective, and engaging.
                4. FORBIDDEN: Do NOT mention source names (BBC, Reuters, NDTV, AajTak, etc.) or "According to...".
                5. QUALITY: If the content is broken, ads, or not a news story, respond with 'REJECT'.
                
                Content: {clean_content[:3000]}
                """
                
                ai_result = call_gemini(prompt)
                
                if not ai_result or "REJECT" in ai_result.upper():
                    continue

                # Final Cleanup
                summary = ai_result.strip()
                # Remove common AI prefixes
                summary = re.sub(r'^(Summary|Here is a summary|The story is about):', '', summary, flags=re.IGNORECASE).strip()
                
                image_url = 'https://images.unsplash.com/photo-1504711434969-e33886168f5c'
                if 'media_content' in entry and entry['media_content']:
                    image_url = entry['media_content'][0]['url']
                elif 'media_thumbnail' in entry and entry['media_thumbnail']:
                    image_url = entry['media_thumbnail'][0]['url']
                elif 'enclosure' in entry: # Some feeds use enclosure
                    image_url = entry['enclosure'].get('url', image_url)

                new_art = Article(
                    id=art_id,
                    title=title,
                    content=summary,
                    image_url=image_url,
                    source_name=source['name'],
                    source_url=article_url,
                    category=source['category'],
                    language=source.get('language', 'en'),
                    created_at=datetime.utcnow()
                )
                db.add(new_art)
                articles_found += 1
                
                # Commit frequently to avoid losing work
                await db.commit()
                
                # Respect API limits
                await asyncio.sleep(4)
                
        logger.info(f"✅ {source['name']}: Added {articles_found} new articles.")
        return articles_found
    except Exception as e:
        logger.error(f"Error fetching {source['name']}: {e}")
        return 0

async def sync_all_news():
    logger.info("--- Starting Professional News Sync ---")
    sources = [
        # ENGLISH - NATIONAL
        {'name': 'The Hindu National', 'url': 'https://www.thehindu.com/news/national/feeder/default.rss', 'category': 'National', 'language': 'en'},
        {'name': 'TOI News', 'url': 'https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms', 'category': 'National', 'language': 'en'},
        
        # ENGLISH - INTERNATIONAL
        {'name': 'BBC World News', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'category': 'International', 'language': 'en'},
        {'name': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'category': 'International', 'language': 'en'},
        
        # ENGLISH - TECHNOLOGY & BUSINESS
        {'name': 'TechCrunch', 'url': 'https://techcrunch.com/feed/', 'category': 'Technology', 'language': 'en'},
        {'name': 'The Verge', 'url': 'https://www.theverge.com/rss/index.xml', 'category': 'Technology', 'language': 'en'},
        {'name': 'Business Today', 'url': 'https://www.businesstoday.in/rss/home', 'category': 'Business', 'language': 'en'},
        
        # ENGLISH - ENTERTAINMENT & SPORTS
        {'name': 'Hollywood Reporter', 'url': 'https://www.hollywoodreporter.com/feed/', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'ESPN Cricket', 'url': 'https://www.espncricinfo.com/rss/content/story/feeds/0.xml', 'category': 'Sports', 'language': 'en'},
        
        # ENGLISH - POLITICS & LIFESTYLE
        {'name': 'Reuters Politics', 'url': 'https://www.reutersagency.com/feed/?best-topics=political-news&post_type=best', 'category': 'Politics', 'language': 'en'},
        {'name': 'Vogue Lifestyle', 'url': 'https://www.vogue.com/feed/lifestyle/rss', 'category': 'Lifestyle', 'language': 'en'},
        
        # HINDI SOURCES (Keep working ones)
        {'name': 'Bhaskar National', 'url': 'https://www.bhaskar.com/rss-v1--category-1061.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Aaj Tak Home', 'url': 'https://www.aajtak.in/rssfeeds/?id=home', 'category': 'National', 'language': 'hi'},
        {'name': 'Navbharat Times', 'url': 'https://navbharattimes.indiatimes.com/rssfeeds/2276856.cms', 'category': 'National', 'language': 'hi'}
    ]
    
    async with AsyncSessionLocal() as db:
        for source in sources:
            logger.info(f"Syncing {source['name']}...")
            await fetch_direct_rss(source, db)
    logger.info("--- Sync Complete ---")

if __name__ == "__main__":
    asyncio.run(sync_all_news())
