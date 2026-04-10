import logging
import feedparser
import httpx
import asyncio
import re
import html as html_parser
from datetime import datetime, timedelta
import time
from bs4 import BeautifulSoup
from database import AsyncSessionLocal
from models import Article
from sqlalchemy.future import select
from sqlalchemy import or_, func, desc

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_html(raw_html):
    if not raw_html: return ""
    text = html_parser.unescape(raw_html)
    soup = BeautifulSoup(text, "lxml")
    for s in soup(["script", "style", "nav", "footer", "iframe"]):
        s.decompose()
    text = soup.get_text(separator=' ')
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def summarize(text, word_limit=70):
    if not text or len(text) < 40:
        return "Latest updates from our reporting partners. Tap 'Read More' for exhaustive coverage."
    words = text.split()
    if len(words) <= word_limit: return text
    snippet = " ".join(words[:word_limit])
    cutoff = max(snippet.rfind('.'), snippet.rfind('।'))
    return snippet[:cutoff + 1] if cutoff != -1 else snippet + "..."

def parse_date(entry):
    """Pro Date Parsing: Fallback to now if entry has no date"""
    for attr in ['published_parsed', 'updated_parsed', 'created_parsed']:
        if hasattr(entry, attr) and getattr(entry, attr):
            return datetime.fromtimestamp(time.mktime(getattr(entry, attr)))
    return datetime.utcnow()

async def fetch_direct_rss(source):
    articles = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            response = await client.get(source['url'])
            feed = feedparser.parse(response.text)
            
            for entry in feed.entries:
                image_url = None
                if 'enclosures' in entry and entry.enclosures:
                    for enc in entry.enclosures:
                        if enc.get('type', '').startswith('image/') or enc.get('url', '').lower().endswith(('.jpg', '.jpeg', '.png', '.webp')):
                            image_url = enc.get('url')
                            break
                if not image_url and 'media_content' in entry: image_url = entry.media_content[0]['url']
                if not image_url and 'media_thumbnail' in entry: image_url = entry.media_thumbnail[0]['url']
                
                # Default Image
                if not image_url:
                    image_url = 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&q=80&w=1000'

                raw_content = entry.get('description', entry.get('summary', ''))
                short_content = summarize(clean_html(raw_content))
                pub_date = parse_date(entry)
                
                title = entry.get('title', '')
                final_category = source['category']
                is_trending = 0
                
                # --- Advanced Conflict Detection ---
                war_keywords = ["iran", "israel", "hezbollah", "missile", "drone", "war", "conflict", "tehran", "tel aviv", "हमास", "ईरान", "युद्ध"]
                search_text = (title + " " + short_content).lower()
                
                if any(kw in search_text for kw in war_keywords):
                    final_category = "Iran War"
                    # Only map to trending if it's very fresh (last 6 hours)
                    if datetime.utcnow() - pub_date < timedelta(hours=6):
                        is_trending = 1

                articles.append(Article(
                    id=entry.get('id', entry.get('link', '')),
                    title=title,
                    content=short_content,
                    author=entry.get('author', source['name']),
                    image_url=image_url,
                    source_name=source['name'],
                    source_url=entry.get('link'),
                    category=final_category,
                    language=source.get('language', 'en'),
                    created_at=pub_date, # USE ACTUAL PUB DATE
                    is_trending=is_trending
                ))
        return articles
    except Exception as e:
        logger.error(f"Error {source['name']}: {e}")
        return []

async def sync_all_news():
    logger.info(f"✨ Starting Sync at {datetime.now()}")
    sources = [
        {'name': 'Google Conflict', 'url': 'https://news.google.com/rss/search?q=Iran+Israel+War&hl=en-IN&gl=IN&ceid=IN:en', 'category': 'Iran War', 'language': 'en'},
        {'name': 'Google News EN', 'url': 'https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en', 'category': 'National', 'language': 'en'},
        {'name': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'category': 'International', 'language': 'en'},
        {'name': 'BBC World', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'category': 'International', 'language': 'en'},
        {'name': 'Reuters', 'url': 'https://www.reutersagency.com/feed/?best-topics=political-news&post_types=best', 'category': 'International', 'language': 'en'},
        {'name': 'TOI', 'url': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms', 'category': 'National', 'language': 'en'},
        {'name': 'Bollywood Hungama', 'url': 'https://www.bollywoodhungama.com/rss/news.xml', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'Bhaskar National', 'url': 'https://www.bhaskar.com/rss-v1--category-1061.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Aaj Tak', 'url': 'https://www.aajtak.in/rssfeeds/?id=home', 'category': 'National', 'language': 'hi'},
        {'name': 'NDTV India', 'url': 'https://ndtv.in/rss/ndtv-india-news.xml', 'category': 'National', 'language': 'hi'},
    ]
    
    async with AsyncSessionLocal() as db:
        total_added = 0
        try:
            for source in sources:
                articles = await fetch_direct_rss(source)
                for article in articles:
                    # Deduplication
                    stmt = select(Article).where(Article.id == article.id)
                    res = await db.execute(stmt)
                    if res.scalars().first(): continue
                    
                    db.add(article)
                    total_added += 1
                await db.commit()
                await asyncio.sleep(0.2)
            logger.info(f"✅ Added {total_added} fresh news cards.")
        except Exception:
            await db.rollback()
鼓
