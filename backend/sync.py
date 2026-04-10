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

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_html(raw_html):
    if not raw_html:
        return ""
    text = html_parser.unescape(raw_html)
    meta_keywords = [
        "Article URL:", "Comments URL:", "Points:", "# Comments:", 
        "Source:", "Source Link:", "Read more at:", "Read more:", 
        "Source Name:", "The post appeared first on", "Check out more"
    ]
    lines = re.split(r'<p>|<div>|<br>|\n|<li>', text, flags=re.IGNORECASE)
    cleaned_parts = [l.strip() for l in lines if l.strip() and not any(k.lower() in l.lower() for k in meta_keywords)]
    text = " ".join(cleaned_parts)
    soup = BeautifulSoup(text, "lxml")
    for s in soup(["script", "style", "nav", "footer", "iframe"]):
        s.decompose()
    text = soup.get_text(separator=' ')
    text = re.sub(r'https?://\S+', '', text)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def summarize(text, word_limit=70):
    if not text or len(text) < 40:
        return "Latest updates from our reporting partners. You can tap 'Read More' to view the exhaustive coverage on the official source website."
    words = text.split()
    if len(words) <= word_limit:
        return text
    snippet = " ".join(words[:word_limit])
    last_dot = snippet.rfind('.')
    last_purna_viraam = snippet.rfind('।')
    cutoff = max(last_dot, last_purna_viraam)
    if cutoff != -1:
        snippet = snippet[:cutoff + 1]
    else:
        snippet += "..."
    return snippet

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
                if not image_url and 'media_content' in entry:
                    image_url = entry.media_content[0]['url']
                if not image_url and 'media_thumbnail' in entry:
                    image_url = entry.media_thumbnail[0]['url']
                if not image_url:
                    content_to_scrape = entry.get('description', '') + entry.get('summary', '')
                    if content_to_scrape:
                        soup = BeautifulSoup(content_to_scrape, "lxml")
                        img = soup.find("img")
                        if img and img.get("src"):
                            image_url = img.get("src")

                category_placeholders = {
                    'Technology': 'https://images.unsplash.com/photo-1488590528505-98d2b5aba04b?auto=format&fit=crop&q=80&w=1000',
                    'Business': 'https://images.unsplash.com/photo-1460925895917-afdab827c52f?auto=format&fit=crop&q=80&w=1000',
                    'Sports': 'https://images.unsplash.com/photo-1461896641502-47db8c966ff7?auto=format&fit=crop&q=80&w=1000',
                    'International': 'https://images.unsplash.com/photo-1529107386315-e1a2ed48a620?auto=format&fit=crop&q=80&w=1000',
                    'Entertainment': 'https://images.unsplash.com/photo-1522869635100-9f4c5e86aa37?auto=format&fit=crop&q=80&w=1000',
                    'Iran War': 'https://images.unsplash.com/photo-1585007600263-ad1f30472692?auto=format&fit=crop&q=80&w=1000',
                }

                if not image_url or 'via.placeholder' in image_url:
                    image_url = category_placeholders.get(source['category'], 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&q=80&w=1000')

                raw_content = entry.get('description', entry.get('summary', ''))
                clean_content = clean_html(raw_content)
                short_content = summarize(clean_content)
                
                # --- IRAN WAR PRIORITY LOGIC ---
                title = entry.get('title', '')
                final_category = source['category']
                is_trending = 0
                
                war_keywords = ["iran", "israel", "hezbollah", "missile", "drone", "war", "conflict", "tehran", "tel aviv"]
                if any(kw in title.lower() for kw in war_keywords) or any(kw in short_content.lower() for kw in war_keywords):
                    final_category = "Iran War"
                    is_trending = 1 # Force to the very top!

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
                    created_at=datetime.utcnow(),
                    is_trending=is_trending
                ))
        return articles
    except Exception as e:
        logger.error(f"Error fetching {source['name']}: {e}")
        return []

async def sync_all_news():
    logger.info(f"✨ Starting Deep News Sync at {datetime.now()}")
    
    sources = [
        {'name': 'Google News India', 'url': 'https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en', 'category': 'National', 'language': 'en'},
        {'name': 'Al Jazeera', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'category': 'International', 'language': 'en'},
        {'name': 'Defense News', 'url': 'https://www.defensenews.com/m/rss/', 'category': 'International', 'language': 'en'},
        {'name': 'BBC News World', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'category': 'International', 'language': 'en'},
        {'name': 'The Hindu World', 'url': 'https://www.thehindu.com/news/international/feeder/default.rss', 'category': 'International', 'language': 'en'},
        {'name': 'Reuters', 'url': 'https://www.reutersagency.com/feed/?best-topics=political-news&post_types=best', 'category': 'International', 'language': 'en'},
        {'name': 'Times of India', 'url': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms', 'category': 'National', 'language': 'en'},
        {'name': 'NDTV Sports', 'url': 'https://feeds.feedburner.com/ndtvsports-latest', 'category': 'Sports', 'language': 'en'},
        {'name': 'Gadgets 360', 'url': 'https://feeds.feedburner.com/gadgets360-latest', 'category': 'Technology', 'language': 'en'},
        {'name': 'News18 Movies', 'url': 'https://www.news18.com/commonfeeds/v1/eng/rss/movies.xml', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'Bollywood Hungama', 'url': 'https://www.bollywoodhungama.com/rss/news.xml', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'HT Entertainment', 'url': 'https://www.hindustantimes.com/feeds/rss/entertainment/rssfeed.xml', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'NDTV Profit', 'url': 'https://feeds.feedburner.com/ndtvprofit-latest', 'category': 'Business', 'language': 'en'},
        {'name': 'India Today English', 'url': 'https://www.indiatoday.in/rss/home', 'category': 'National', 'language': 'en'},
        {'name': 'Economic Times', 'url': 'https://economictimes.indiatimes.com/rssfeedstopstories.cms', 'category': 'Business', 'language': 'en'},
        
        # --- HINDI SOURCES ---
        {'name': 'Bhaskar National', 'url': 'https://www.bhaskar.com/rss-v1--category-1061.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Aaj Tak', 'url': 'https://www.aajtak.in/rssfeeds/?id=home', 'category': 'National', 'language': 'hi'},
        {'name': 'NDTV India', 'url': 'https://ndtv.in/rss/ndtv-india-news.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Amar Ujala', 'url': 'https://www.amarujala.com/rss/breaking-news.xml', 'category': 'Politics', 'language': 'hi'},
        {'name': 'BBC Hindi', 'url': 'https://feeds.bbci.co.uk/hindi/rss.xml', 'category': 'International', 'language': 'hi'},
        {'name': 'Bhaskar Bollywood', 'url': 'https://www.bhaskar.com/rss-v1--category-11215.xml', 'category': 'Entertainment', 'language': 'hi'},
        {'name': 'Bhaskar Tech', 'url': 'https://www.bhaskar.com/rss-v1--category-5707.xml', 'category': 'Technology', 'language': 'hi'},
        {'name': 'Bhaskar Sports', 'url': 'https://www.bhaskar.com/rss-v1--category-1053.xml', 'category': 'Sports', 'language': 'hi'},
        {'name': 'Bhaskar Business', 'url': 'https://www.bhaskar.com/rss-v1--category-1051.xml', 'category': 'Business', 'language': 'hi'},
        {'name': 'Bhaskar Women', 'url': 'https://www.bhaskar.com/rss-v1--category-1532.xml', 'category': 'Lifestyle', 'language': 'hi'},
        {'name': 'Bhaskar Career', 'url': 'https://www.bhaskar.com/rss-v1--category-11945.xml', 'category': 'Technology', 'language': 'hi'},
        {'name': 'Bhaskar International', 'url': 'https://www.bhaskar.com/rss-v1--category-1125.xml', 'category': 'International', 'language': 'hi'},
    ]
    
    async with AsyncSessionLocal() as db:
        total_added = 0
        try:
            recent_limit = datetime.utcnow() - timedelta(hours=12)
            for source in sources:
                logger.info(f"Syncing {source['name']}...")
                articles = await fetch_direct_rss(source)
                for article in articles:
                    result = await db.execute(select(Article).where(Article.id == article.id))
                    if result.scalars().first():
                        continue
                    title_snippet = article.title[:40] if article.title else ""
                    if title_snippet:
                        similar_result = await db.execute(
                            select(Article).where(
                                Article.title.like(f"{title_snippet}%"),
                                Article.created_at >= recent_limit
                            )
                        )
                        if similar_result.scalars().first():
                            continue
                    db.add(article)
                    total_added += 1
                await db.commit()
                await asyncio.sleep(0.3)
            logger.info(f"✅ Sync Complete. Added {total_added} fresh news cards.")
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            await db.rollback()
鼓
