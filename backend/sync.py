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
# import google.generativeai as genai
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
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer

def call_gemini(prompt):
    """
    DEPRECATED: Removed Gemini to eliminate 429 quota limits.
    Now using local smart extraction.
    """
    pass

def local_smart_summarize(text, language="english", sentences_count=3):
    try:
        # Try requested language first
        try:
            parser = PlaintextParser.from_string(text, Tokenizer(language))
        except:
            # Fallback to English tokenizer if language (like hindi) is missing
            parser = PlaintextParser.from_string(text, Tokenizer("english"))
            
        summarizer = LsaSummarizer()
        summary = summarizer(parser.document, sentences_count)
        result = " ".join([str(sentence) for sentence in summary])
        # Ensure it fits within a nice 60-70 word equivalent
        return result[:400] + "..." if len(result) > 400 else result
    except Exception as e:
        logger.error(f"Local summary failed: {e}")
        return text[:400] + "..."

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

async def fetch_direct_rss(source):
    articles_found = 0
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            response = await client.get(source['url'])
            feed = feedparser.parse(response.text)
            
            async with AsyncSessionLocal() as db:
                for entry in feed.entries[:25]: 
                    article_url = entry.get('link')
                    if not article_url: continue
                    
                    title = clean_title(entry.get('title', ''))
                    art_id = f"{article_url}_{title}"
                    
                    exists = await db.execute(select(Article).where(Article.id == art_id))
                    if exists.scalars().first():
                        continue 
                    
                    full_body = await fetch_article_body(article_url)
                    rss_summary = clean_html(entry.get('summary', ''))
                    clean_content = full_body if full_body else rss_summary
                    
                    if len(clean_content) < 150: continue
                
                    # Use Local Smart Summarizer instead of Gemini
                    lang_param = 'hindi' if source.get('language') == 'hi' else 'english'
                    summary = local_smart_summarize(clean_content, language=lang_param)
                    
                    # If local sum fails to produce good text, fallback to clean rss summary
                    if len(summary) < 50:
                        summary = rss_summary[:400] + "..."
                        
                    image_url = 'https://images.unsplash.com/photo-1504711434969-e33886168f5c'
                    if 'media_content' in entry and entry['media_content']:
                        image_url = entry['media_content'][0]['url']
                    elif 'media_thumbnail' in entry and entry['media_thumbnail']:
                        image_url = entry['media_thumbnail'][0]['url']
                    elif 'enclosure' in entry:
                        image_url = entry['enclosure'].get('url', image_url)

                    new_art = Article(
                        id=art_id, title=title, content=summary,
                        image_url=image_url, source_name=source['name'],
                        source_url=article_url, category=source['category'],
                        language=source.get('language', 'en'), created_at=datetime.utcnow()
                    )
                    db.add(new_art)
                    articles_found += 1
                    await db.commit()
                    await asyncio.sleep(4)
                    
        logger.info(f"✅ {source['name']}: Added {articles_found} articles.")
    except Exception as e:
        logger.error(f"Error fetching {source['name']}: {e}")

async def sync_all_news():
    logger.info("--- Starting Parallel Pro News Sync ---")
    # (Sources list remains same)
    sources = [
        {'name': 'The Hindu National', 'url': 'https://www.thehindu.com/news/national/feeder/default.rss', 'category': 'National', 'language': 'en'},
        {'name': 'TOI News', 'url': 'https://timesofindia.indiatimes.com/rssfeeds/-2128936835.cms', 'category': 'National', 'language': 'en'},
        {'name': 'BBC World News', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'category': 'International', 'language': 'en'},
        {'name': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'category': 'International', 'language': 'en'},
        {'name': 'TechCrunch', 'url': 'https://techcrunch.com/feed/', 'category': 'Technology', 'language': 'en'},
        {'name': 'The Verge', 'url': 'https://www.theverge.com/rss/index.xml', 'category': 'Technology', 'language': 'en'},
        {'name': 'Business Today', 'url': 'https://www.businesstoday.in/rss/home', 'category': 'Business', 'language': 'en'},
        {'name': 'Hollywood Reporter', 'url': 'https://www.hollywoodreporter.com/feed/', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'ESPN Cricket', 'url': 'https://www.espncricinfo.com/rss/content/story/feeds/0.xml', 'category': 'Sports', 'language': 'en'},
        {'name': 'Reuters Politics', 'url': 'https://www.reutersagency.com/feed/?best-topics=political-news&post_type=best', 'category': 'Politics', 'language': 'en'},
        {'name': 'Vogue Lifestyle', 'url': 'https://www.vogue.com/feed/lifestyle/rss', 'category': 'Lifestyle', 'language': 'en'},
        {'name': 'Bhaskar National', 'url': 'https://www.bhaskar.com/rss-v1--category-1061.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Aaj Tak Home', 'url': 'https://www.aajtak.in/rssfeeds/?id=home', 'category': 'National', 'language': 'hi'},
        {'name': 'Navbharat Times', 'url': 'https://navbharattimes.indiatimes.com/rssfeeds/2276856.cms', 'category': 'National', 'language': 'hi'},
        {'name': 'Bhaskar Business', 'url': 'https://www.bhaskar.com/rss-v1--category-1064.xml', 'category': 'Business', 'language': 'hi'},
        {'name': 'Aaj Tak Sports', 'url': 'https://www.aajtak.in/rssfeeds/?id=sports', 'category': 'Sports', 'language': 'hi'}
    ]
    
    import random
    random.shuffle(sources)
    
    # Run sources in Parallel batches
    batch_size = 3
    for i in range(0, len(sources), batch_size):
        batch = sources[i:i + batch_size]
        logger.info(f"Processing Batch {i//batch_size + 1}...")
        await asyncio.gather(*(fetch_direct_rss(source) for source in batch))
            
    logger.info("--- Parallel Sync Batch Complete ---")

if __name__ == "__main__":
    asyncio.run(sync_all_news())
