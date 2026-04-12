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
    
    # 1. Parse with BeautifulSoup first to strip tags safely
    soup = BeautifulSoup(raw_html, "lxml")
    for s in soup(["script", "style", "nav", "footer", "iframe", "header", "button"]):
        s.decompose()
        
    text = soup.get_text(separator=' ')
    text = html_parser.unescape(text)
    
    # 2. Filtering out ghost lines and persistent metadata
    meta_keywords = [
        "Article URL:", "Comments URL:", "Points:", "# Comments:", 
        "Source:", "Source Link:", "Read more at:", "Read more:", 
        "Source Name:", "The post appeared first on", "Check out more",
        "Subscribe to", "Follow us on", "Click here to", "ALSO READ",
        "Copyright", "All rights reserved"
    ]
    
    # Split by periods or suggestive breaks to filter individual sentences
    sentences = re.split(r'(?<=[.।!|])\s+', text)
    cleaned_sentences = []
    for s in sentences:
        s = s.strip()
        if not s: continue
        # Ignore sentences that are too short or contain metadata keywords
        if len(s) < 10: continue
        if any(k.lower() in s.lower() for k in meta_keywords): continue
        # Ignore ghost text placeholders
        if s.lower() in ["loading...", "read more", "continue reading"]: continue
        cleaned_sentences.append(s)
    
    # 3. Final Rejoin
    text = " ".join(cleaned_sentences)
    text = re.sub(r'https?://\S+', '', text) # Final URL safety
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text

def clean_title(title):
    if not title: return ""
    
    # 1. Unescape HTML entities (converts &#039; to ', &amp; to &, etc.)
    title = html_parser.unescape(title)
    
    # 2. Remove bilingual separators usually like "Title in Hindi | Title in English"
    if '|' in title:
        parts = title.split('|')
        title = parts[0].strip()
    if ' - ' in title:
        title = title.split(' - ')[0].strip()
        
    # 3. Final cleanup of whitespace and stray characters
    title = re.sub(r'\s+', ' ', title).strip()
    return title.strip()

def summarize(text, word_limit=70):
    if not text or len(text.strip()) < 20:
        return "Latest updates from our reporting partners. You can tap 'Read More' to view the exhaustive coverage on the official source website."
    
    words = text.split()
    if len(words) <= word_limit:
        return text
    
    # Take first N words and try to end at a sentence break for smoothness
    snippet = " ".join(words[:word_limit])
    
    # Support both English (.) and Hindi (।) and (|) and (!) sentence endings
    ends = [snippet.rfind('.'), snippet.rfind('।'), snippet.rfind('|'), snippet.rfind('!')]
    cutoff = max(ends)
    
    # Only cutoff if the sentence is reasonably long, otherwise use ...
    if cutoff != -1 and cutoff > (len(snippet) * 0.6):
        snippet = snippet[:cutoff + 1]
    else:
        # Try to find a space near the limit to avoid cutting words
        last_space = snippet.rfind(' ')
        if last_space != -1:
            snippet = snippet[:last_space]
        snippet += "..."
        
    return snippet

async def fetch_article_body(url):
    """Deep Scrapes the actual news website to get the real story."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=10.0) as client:
            response = await client.get(url)
            if response.status_code != 200: return None
            
            soup = BeautifulSoup(response.text, "lxml")
            
            # Remove noise
            for s in soup(["script", "style", "nav", "footer", "header", "aside"]):
                s.decompose()

            # Strategy: Find the div with the most paragraphs
            main_content = ""
            potential_bodies = soup.find_all(['div', 'article', 'section'])
            best_element = None
            max_p = 0
            
            for element in potential_bodies:
                p_count = len(element.find_all('p', recursive=False))
                if p_count > max_p:
                    max_p = p_count
                    best_element = element
            
            if best_element:
                paragraphs = best_element.find_all('p')
                main_content = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 40])
            
            # Fallback to all P tags if no clear body found
            if not main_content or len(main_content) < 100:
                paragraphs = soup.find_all('p')
                main_content = " ".join([p.get_text().strip() for p in paragraphs if len(p.get_text().strip()) > 40])

            return clean_html(main_content)
    except:
        return None

async def fetch_direct_rss(source):
    articles = []
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115.0.0.0 Safari/537.36'}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            response = await client.get(source['url'])
            feed = feedparser.parse(response.text)
            
            # Limit to top 5 articles per source for Deep Scraping to keep it fast
            for entry in feed.entries[:5]:
                # Robust Image Extraction
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

                # Deep Scrape for high quality content
                article_url = entry.get('link')
                full_body = await fetch_article_body(article_url)
                
                if full_body and len(full_body) > 100:
                    clean_content = full_body
                else:
                    # Fallback to RSS description if scraping fails
                    desc = entry.get('description', entry.get('summary', ''))
                    clean_content = clean_html(desc)

                short_content = summarize(clean_content, word_limit=60)
                cleaned_title = clean_title(entry.get('title', ''))

                # Generate a unique ID
                unique_id = f"{article_url}_{cleaned_title}"
                
                articles.append(Article(
                    id=unique_id,
                    title=cleaned_title,
                    content=short_content,
                    author=entry.get('author', source['name']),
                    image_url=image_url if image_url else 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?auto=format&fit=crop&q=80&w=1000',
                    source_name=source['name'],
                    source_url=article_url,
                    category=source['category'],
                    language=source.get('language', 'en'),
                    created_at=datetime.utcnow(),
                    is_trending=1 if 'trending' in cleaned_title.lower() else 0
                ))
        return articles
    except Exception as e:
        logger.error(f"Error fetching {source['name']}: {e}")
        return []

async def sync_all_news():
    logger.info(f"✨ Starting Deep News Sync at {datetime.now()}")
    
    # Precise Inshorts Source Mapping (Bilingual)
    sources = [
        # --- ENGLISH SOURCES ---
        {'name': 'BBC News World', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'category': 'International', 'language': 'en'},
        {'name': 'The Hindu World', 'url': 'https://www.thehindu.com/news/international/feeder/default.rss', 'category': 'International', 'language': 'en'},
        {'name': 'Reuters', 'url': 'https://www.reutersagency.com/feed/?best-topics=political-news&post_types=best', 'category': 'International', 'language': 'en'},
        {'name': 'Times of India', 'url': 'https://timesofindia.indiatimes.com/rssfeedstopstories.cms', 'category': 'National', 'language': 'en'},
        {'name': 'The Indian Express', 'url': 'https://indianexpress.com/section/india/feed/', 'category': 'National', 'language': 'en'},
        {'name': 'Hindustan Times', 'url': 'https://www.hindustantimes.com/feeds/rss/india-news/rssfeed.xml', 'category': 'National', 'language': 'en'},
        {'name': 'News18 National', 'url': 'https://www.news18.com/commonfeeds/v1/eng/rss/india.xml', 'category': 'National', 'language': 'en'},
        {'name': 'News18 Politics', 'url': 'https://www.news18.com/commonfeeds/v1/eng/rss/politics.xml', 'category': 'Politics', 'language': 'en'},
        {'name': 'NDTV Politics', 'url': 'https://feeds.feedburner.com/ndtvnews-india-news', 'category': 'Politics', 'language': 'en'},
        {'name': 'NDTV Sports', 'url': 'https://feeds.feedburner.com/ndtvsports-latest', 'category': 'Sports', 'language': 'en'},
        {'name': 'Gadgets 360', 'url': 'https://feeds.feedburner.com/gadgets360-latest', 'category': 'Technology', 'language': 'en'},
        {'name': 'News18 Movies', 'url': 'https://www.news18.com/commonfeeds/v1/eng/rss/movies.xml', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'Bollywood Hungama', 'url': 'https://www.bollywoodhungama.com/rss/news.xml', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'HT Entertainment', 'url': 'https://www.hindustantimes.com/feeds/rss/entertainment/rssfeed.xml', 'category': 'Entertainment', 'language': 'en'},
        {'name': 'NDTV Profit', 'url': 'https://feeds.feedburner.com/ndtvprofit-latest', 'category': 'Business', 'language': 'en'},
        {'name': 'Economic Times', 'url': 'https://economictimes.indiatimes.com/rssfeedstopstories.cms', 'category': 'Business', 'language': 'en'},
        {'name': 'News18 Lifestyle', 'url': 'https://www.news18.com/commonfeeds/v1/eng/rss/lifestyle.xml', 'category': 'Lifestyle', 'language': 'en'},
        {'name': 'Times of India Lifestyle', 'url': 'https://timesofindia.indiatimes.com/rssfeeds/2886704.cms', 'category': 'Lifestyle', 'language': 'en'},
        
        # --- HINDI SOURCES (MASTER LIST) ---
        {'name': 'Bhaskar National', 'url': 'https://www.bhaskar.com/rss-v1--category-1061.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Aaj Tak', 'url': 'https://www.aajtak.in/rssfeeds/?id=home', 'category': 'National', 'language': 'hi'},
        {'name': 'NDTV India', 'url': 'https://ndtv.in/rss/ndtv-india-news.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Amar Ujala', 'url': 'https://www.amarujala.com/rss/breaking-news.xml', 'category': 'Politics', 'language': 'hi'},
        {'name': 'Dainik Jagran', 'url': 'http://rss.jagran.com/local/uttar-pradesh/lucknow-city.xml', 'category': 'Politics', 'language': 'hi'},
        {'name': 'Navbharat Times Politics', 'url': 'https://navbharattimes.indiatimes.com/rssfeeds/2276800.cms', 'category': 'Politics', 'language': 'hi'},
        {'name': 'BBC Hindi', 'url': 'https://feeds.bbci.co.uk/hindi/rss.xml', 'category': 'International', 'language': 'hi'},
        {'name': 'Bhaskar Bollywood', 'url': 'https://www.bhaskar.com/rss-v1--category-11215.xml', 'category': 'Entertainment', 'language': 'hi'},
        {'name': 'Bhaskar Tech', 'url': 'https://www.bhaskar.com/rss-v1--category-5707.xml', 'category': 'Technology', 'language': 'hi'},
        {'name': 'Bhaskar Sports', 'url': 'https://www.bhaskar.com/rss-v1--category-1053.xml', 'category': 'Sports', 'language': 'hi'},
        {'name': 'Bhaskar Business', 'url': 'https://www.bhaskar.com/rss-v1--category-1051.xml', 'category': 'Business', 'language': 'hi'},
        {'name': 'Bhaskar Women', 'url': 'https://www.bhaskar.com/rss-v1--category-1532.xml', 'category': 'Lifestyle', 'language': 'hi'},
        {'name': 'News18 Hindi Lifestyle', 'url': 'https://hindi.news18.com/commonfeeds/v1/hin/rss/lifestyle.xml', 'category': 'Lifestyle', 'language': 'hi'},
        {'name': 'Bhaskar Career', 'url': 'https://www.bhaskar.com/rss-v1--category-11945.xml', 'category': 'Technology', 'language': 'hi'},
        {'name': 'Bhaskar International', 'url': 'https://www.bhaskar.com/rss-v1--category-1125.xml', 'category': 'International', 'language': 'hi'},
        {'name': 'Google News National', 'url': 'https://news.google.com/rss/headlines/section/topic/NATION?hl=en-IN&gl=IN&ceid=IN:en', 'category': 'National', 'language': 'en'},
        {'name': 'Google News World', 'url': 'https://news.google.com/rss/headlines/section/topic/WORLD?hl=en-IN&gl=IN&ceid=IN:en', 'category': 'International', 'language': 'en'},
        {'name': 'Google News Hindi', 'url': 'https://news.google.com/rss?hl=hi&gl=IN&ceid=IN:hi', 'category': 'National', 'language': 'hi'},
        {'name': 'Google News International Hindi', 'url': 'https://news.google.com/rss/headlines/section/topic/WORLD?hl=hi&gl=IN&ceid=IN:hi', 'category': 'International', 'language': 'hi'},
    ]
    
    async with AsyncSessionLocal() as db:
        total_added = 0
        try:
            recent_limit = datetime.utcnow() - timedelta(hours=12)
            for source in sources:
                logger.info(f"Syncing {source['name']}...")
                articles = await fetch_direct_rss(source)
                for article in articles:
                    # 1. Strict ID Check (Same Link)
                    result = await db.execute(select(Article).where(Article.id == article.id))
                    if result.scalars().first():
                        continue

                    # 2. Add to DB
                    db.add(article)
                    total_added += 1
                await db.commit()
                await asyncio.sleep(0.5) 
                
            logger.info(f"✅ Sync Complete. Added {total_added} fresh news cards.")
        except Exception as e:
            logger.error(f"Sync failed: {e}")
            await db.rollback()
