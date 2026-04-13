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

from groq import Groq
groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))

def groq_summarize(text, language="english"):
    """High-speed AI Summarization using Groq"""
    if not text or len(text) < 100: return text
    
    try:
        prompt = f"""
        Summarize this news article in about 60 words.
        Target Language: {language}
        
        Strict Rules:
        1. Output ONLY the summary text. No 'Here is a summary' or 'Sure'.
        2. Remove all metadata, source names, 'Copy Link', or junk text.
        3. Professional, engaging, and factual news tone.
        4. Max 75 words.
        
        ARTICLE:
        {text[:4000]}
        """
        
        chat_completion = groq_client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama3-70b-8192",
            temperature=0.5,
        )
        summary = chat_completion.choices[0].message.content.strip()
        # Basic character cleaning if common prefixes leak
        summary = re.sub(r'^(Summary|यहाँ सारांश है|सारांश):', '', summary, flags=re.IGNORECASE).strip()
        return summary
    except Exception as e:
        logger.info(f"Groq API Error: {e}. Falling back to clean text...")
        return text[:400] + "..."

def local_smart_summarize(text, language="english", sentences_count=3):
    # This is now a simple wrapper for Groq
    return groq_summarize(text, language)

def clean_html(raw_html, language='en'):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    cleantext = re.sub(cleanr, ' ', raw_html)
    text = html_parser.unescape(cleantext).strip()
    
    # --- BHASKAR SPECIAL SCRUBBER ---
    if "Dainik Bhaskar" in text or "Hindi News" in text:
        # Throw away leading metadata
        text = re.sub(r'^.*?Dainik Bhaskar', '', text, flags=re.IGNORECASE)
        text = re.sub(r'^.*?News Headlines Today.*?\-\s*', '', text, flags=re.IGNORECASE)

    # --- DEVANAGARI LOCK ---
    if language == 'hi':
        # Remove everything until the first Hindi character (Devanagari)
        devanagari_search = re.search(r'[\u0900-\u097F]', text)
        if devanagari_search:
            text = text[devanagari_search.start():]
            
    # Remove common    # --- GLOBAL JUNK DELETE ---
    junk = [
        r'English\s*United\s*States.*?Kiswahili', # Kills the Google News language picker block
        r'कॉपी लिंक', r'copy link', r'Advertisement', 
        r'Follow us on.*$', r'Subscribe to.*$',
        r'^.*?\s*[\-\|]\s*.*? न्यूज़\s*:', # "City - Title News:"
        r'[\-\|]\s*Hindi News.*$',
    ]
    for pattern in junk:
        text = re.sub(pattern, '', text, flags=re.IGNORECASE)
        
    return text.strip()

def clean_title(title):
    if not title: return ""
    title = html_parser.unescape(title)
    # Remove source names and metadata headers
    title = re.sub(r'^.*?[\-\|]\s*', '', title)
    title = re.sub(r'\s*[\-\|]\s*.*$', '', title)
    title = re.sub(r'Hindi News.*?:', '', title, flags=re.IGNORECASE)
    # Ensure no English junk prefixes in Hindi titles
    if re.search(r'[\u0900-\u097F]', title):
        dev = re.search(r'[\u0900-\u097F]', title)
        if dev: title = title[dev.start():]
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
                    
                    lang_code = source.get('language', 'en')
                    full_body = await fetch_article_body(article_url)
                    rss_summary = clean_html(entry.get('summary', ''), language=lang_code)
                    clean_content = full_body if full_body else rss_summary
                    
                    if len(clean_content) < 150: continue
                
                    # Use Local Smart Summarizer instead of Gemini
                    lang_param = 'hindi' if lang_code == 'hi' else 'english'
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
    sources = [
        {'name': 'The Hindu', 'url': 'https://www.thehindu.com/news/national/feeder/default.rss', 'category': 'National', 'language': 'en'},
        {'name': 'BBC World', 'url': 'http://feeds.bbci.co.uk/news/world/rss.xml', 'category': 'International', 'language': 'en'},
        {'name': 'Al Jazeera War', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'category': 'War', 'language': 'en'},
        {'name': 'Reuters Politics', 'url': 'https://www.reutersagency.com/feed/?best-topics=political-news&post_type=best', 'category': 'Politics', 'language': 'en'},
        
        # --- GOOGLE NEWS HINDI (ULTRA CLEAN & ALWAYS FULL) ---
        {'name': 'Google Hindi National', 'url': 'https://news.google.com/rss/headlines/section/topic/NATION?hl=hi&gl=IN&ceid=IN:hi', 'category': 'National', 'language': 'hi'},
        {'name': 'Google Hindi World', 'url': 'https://news.google.com/rss/headlines/section/topic/WORLD?hl=hi&gl=IN&ceid=IN:hi', 'category': 'International', 'language': 'hi'},
        {'name': 'Google Hindi Politics', 'url': 'https://news.google.com/rss/search?q=politics&hl=hi&gl=IN&ceid=IN:hi', 'category': 'Politics', 'language': 'hi'},
        {'name': 'Google Hindi War', 'url': 'https://news.google.com/rss/search?q=war+conflict&hl=hi&gl=IN&ceid=IN:hi', 'category': 'War', 'language': 'hi'},
        {'name': 'Aaj Tak Home', 'url': 'https://www.aajtak.in/rssfeeds/?id=home', 'category': 'National', 'language': 'hi'}
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
