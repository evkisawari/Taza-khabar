import logging
import feedparser
import httpx
import asyncio
import re
import html as html_parser
import os
import threading
import concurrent.futures
from datetime import datetime
from bs4 import BeautifulSoup
from database import AsyncSessionLocal
from models import Article
from sqlalchemy.future import select
from sqlalchemy import func, desc
import trafilatura
from dotenv import load_dotenv
from groq import Groq

# --- Load environment FIRST, before anything else ---
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sync")

executor = concurrent.futures.ThreadPoolExecutor(max_workers=5)

# =============================================================
# GROQ AI SUMMARIZER
# =============================================================
def groq_summarize(text: str, language: str = "english") -> str:
    """Use Groq Llama3 to write a clean 60-word professional news summary."""
    if not text or len(text.strip()) < 150:
        logger.warning("Text too short for summarization, skipping.")
        return ""

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("❌ GROQ_API_KEY not found in environment!")
        return ""

    try:
        client = Groq(api_key=api_key)
        lang_instruction = "Hindi (Devanagari script only)" if language == "hindi" else "English"
        
        prompt = f"""You are a professional news editor. Write a clean, factual 60-word summary of the article below.

Rules:
- Language: {lang_instruction}
- Output ONLY the summary. No intro phrases like "Here is..." or "Sure..."
- Do NOT mention the source website name
- Do NOT include any metadata, links, or UI elements
- Max 75 words

Article:
{text[:800]}"""

        response = client.chat.completions.create(
            messages=[{"role": "user", "content": prompt}],
            model="llama-3.3-70b-versatile",
            temperature=0.3,
            max_tokens=150,
        )
        summary = response.choices[0].message.content.strip()
        # Remove any leaked prefix phrases
        summary = re.sub(r'^(Sure|Here is|Summary|सारांश|यहाँ)[^।.]*[।:.]?\s*', '', summary, flags=re.IGNORECASE).strip()
        logger.info(f"✅ Groq summary generated ({len(summary)} chars)")
        return summary
    except Exception as e:
        logger.error(f"❌ Groq API failed: {e}")
        return ""


# =============================================================
# CONTENT CLEANER
# =============================================================
# Language names that appear in Google News language-picker blocks
_LANG_LIST_WORDS = {'नेपाली','मराठी','हिन्दी','हिंदी','असमीया','বাংলা','ਪੰਜਾਬੀ','ગુજરાતી','ଓଡ଼ିଆ','தமிழ்','తెలుగు','ಕನ್ನಡ','മലയാളം','සිංහල','Melayu','Slovenčina','Kiswahili'}

def is_language_list(text: str) -> bool:
    """Returns True if the text is a Google News language-picker menu, not real news."""
    words = set(re.split(r'[\s\-–\n]+', text))
    matches = words & _LANG_LIST_WORDS
    return len(matches) >= 3  # If 3+ language names found, it's junk

def clean_text(raw: str, language: str = "en") -> str:
    """Remove HTML tags, metadata, and language-list junk from RSS content."""
    if not raw:
        return ""
    # Strip HTML tags
    text = re.sub(r'<[^>]+>', ' ', raw)
    text = html_parser.unescape(text)
    text = re.sub(r'\s+', ' ', text).strip()

    # Kill the English Google News language footer
    text = re.sub(r'English\s*United\s*States.*', '', text, flags=re.IGNORECASE | re.DOTALL)
    text = re.sub(r'Kiswahili.*', '', text, flags=re.IGNORECASE | re.DOTALL)

    # Hindi-specific: Remove everything before the first Devanagari character
    if language == 'hi':
        match = re.search(r'[\u0900-\u097F]', text)
        if match:
            text = text[match.start():]

    # Common junk phrases
    junk_patterns = [
        r'कॉपी लिंक', r'copy link', r'advertisement',
        r'follow us on.*', r'subscribe to.*',
        r'read more.*', r'also read.*',
        r'[-|]\s*hindi news.*',
    ]
    for p in junk_patterns:
        text = re.sub(p, '', text, flags=re.IGNORECASE)

    return text.strip()


def clean_title(title: str) -> str:
    if not title:
        return ""
    title = html_parser.unescape(title)
    # Remove "Source - " prefix patterns
    title = re.sub(r'^[^|–-]*[-–|]\s*', '', title)
    # Remove trailing " - Source" suffix
    title = re.sub(r'\s*[-–|][^|–-]*$', '', title)
    # For Hindi titles: strip any leading Latin characters
    if re.search(r'[\u0900-\u097F]', title):
        m = re.search(r'[\u0900-\u097F]', title)
        if m:
            title = title[m.start():]
    return title.strip()


# =============================================================
# ARTICLE BODY FETCHER (Deep Scraper)
# =============================================================
def scrape_article(url: str) -> str | None:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.google.com/",
    }
    try:
        with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as client:
            resp = client.get(url)
            if resp.status_code != 200:
                return None
            # Try trafilatura (best quality)
            content = trafilatura.extract(resp.text, include_comments=False, include_tables=False)
            if content and len(content) > 200:
                return content
            # Fallback: extract <p> tags
            soup = BeautifulSoup(resp.text, 'lxml')
            for tag in soup(["script", "style", "nav", "footer", "header", "aside"]):
                tag.decompose()
            paragraphs = [p.get_text(" ").strip() for p in soup.find_all('p') if len(p.get_text().strip()) > 40]
            body = " ".join(paragraphs)
            return body if len(body) > 200 else None
    except Exception as e:
        logger.warning(f"Scrape failed for {url}: {e}")
        return None


async def fetch_body(url: str) -> str | None:
    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(executor, scrape_article, url)
    except Exception:
        return None


# =============================================================
# PER-SOURCE INGESTION
# =============================================================
async def ingest_source(source: dict):
    articles_saved = 0
    try:
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
        async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(source['url'])
            feed = feedparser.parse(resp.text)

        lang_code = source.get('language', 'en')
        lang_param = 'hindi' if lang_code == 'hi' else 'english'

        async with AsyncSessionLocal() as db:
            for entry in feed.entries[:20]:
                link = entry.get('link')
                if not link:
                    continue

                title = clean_title(entry.get('title', ''))
                if not title:
                    continue

                art_id = f"{link}_{title[:50]}"

                # Skip duplicates
                exists = await db.execute(select(Article).where(Article.id == art_id))
                if exists.scalars().first():
                    continue

                # --- STEP 1: Get article body (prefer full scrape over RSS snippet) ---
                body = await fetch_body(link)
                rss_text = clean_text(entry.get('summary', ''), language=lang_code)

                # Use full article body if available, otherwise fall back to RSS summary
                content_for_ai = clean_text(body, language=lang_code) if body else rss_text

                # CRITICAL: Skip if it's a Google News language-picker list (not real news)
                if is_language_list(content_for_ai):
                    logger.info(f"Skipping (language list junk): {title[:50]}")
                    continue

                # Skip if content is too short to be real news
                if len(content_for_ai) < 150:
                    logger.info(f"Skipping (too short): {title[:50]}")
                    continue

                # --- STEP 2: Send to Groq for professional summary ---
                summary = groq_summarize(content_for_ai, language=lang_param)

                # If Groq fails, skip the article entirely (no junk fallback)
                if not summary or len(summary) < 30:
                    logger.warning(f"Groq returned empty summary, skipping: {title[:50]}")
                    continue

                # --- STEP 3: Get image ---
                image_url = 'https://images.unsplash.com/photo-1504711434969-e33886168f5c?w=800'
                if entry.get('media_content'):
                    image_url = entry['media_content'][0].get('url', image_url)
                elif entry.get('media_thumbnail'):
                    image_url = entry['media_thumbnail'][0].get('url', image_url)

                # --- STEP 4: Save to DB ---
                article = Article(
                    id=art_id,
                    title=title,
                    content=summary,
                    image_url=image_url,
                    source_name=source['name'],
                    source_url=link,
                    category=source['category'],
                    language=lang_code,
                    created_at=datetime.utcnow(),
                )
                db.add(article)
                await db.commit()
                articles_saved += 1
                logger.info(f"✅ Saved: [{lang_code}/{source['category']}] {title[:60]}")

                # Small delay to avoid Groq rate limits
                await asyncio.sleep(2)

        logger.info(f"📰 {source['name']}: {articles_saved} new articles saved.")
    except Exception as e:
        logger.error(f"❌ Error in source '{source['name']}': {e}")


# =============================================================
# MASTER SYNC ORCHESTRATOR
# =============================================================
async def sync_all_news():
    logger.info("🚀 Starting news sync...")

    sources = [
        # --- ENGLISH (National) ---
        {'name': 'BBC India', 'url': 'http://feeds.bbci.co.uk/news/world/asia/india/rss.xml', 'category': 'National', 'language': 'en'},
        {'name': 'The Hindu', 'url': 'https://www.thehindu.com/feeder/default.rss', 'category': 'National', 'language': 'en'},
        {'name': 'India Today', 'url': 'https://www.indiatoday.in/rss/home', 'category': 'National', 'language': 'en'},
        {'name': 'Moneycontrol', 'url': 'http://www.moneycontrol.com/rss/latestnews.xml', 'category': 'National', 'language': 'en'},
        
        # --- ENGLISH (International) ---
        {'name': 'Guardian India', 'url': 'https://www.theguardian.com/world/india/rss', 'category': 'International', 'language': 'en'},
        {'name': 'News18 World', 'url': 'https://www.news18.com/rss/world.xml', 'category': 'International', 'language': 'en'},
        {'name': 'Reuters World', 'url': 'https://www.reutersagency.com/feed/?best-topics=world-news&post_type=best', 'category': 'International', 'language': 'en'},

        # --- ENGLISH (Politics & War) ---
        {'name': 'The Print Politics', 'url': 'https://theprint.in/category/politics/feed/', 'category': 'Politics', 'language': 'en'},
        {'name': 'Al Jazeera War', 'url': 'https://www.aljazeera.com/xml/rss/all.xml', 'category': 'War', 'language': 'en'},

        # --- HINDI (National) ---
        {'name': 'Amar Ujala', 'url': 'https://www.amarujala.com/rss/breaking-news.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Live Hindustan', 'url': 'https://feed.livehindustan.com/rss/3127', 'category': 'National', 'language': 'hi'},
        {'name': 'Bhaskar National', 'url': 'https://www.bhaskar.com/rss-feed/1061/', 'category': 'National', 'language': 'hi'},
        {'name': 'India TV Hindi', 'url': 'https://www.indiatv.in/cms/rssfeed', 'category': 'National', 'language': 'hi'},

        # --- HINDI (International & Politics) ---
        {'name': 'News18 Hindi World', 'url': 'https://hindi.news18.com/khabar-rss/', 'category': 'International', 'language': 'hi'},
        {'name': 'Jansatta Politics', 'url': 'https://www.jansatta.com/feed/', 'category': 'Politics', 'language': 'hi'},
        {'name': 'Bhaskar Politics', 'url': 'https://www.bhaskar.com/rss-v1--category-1065.xml', 'category': 'Politics', 'language': 'hi'},
    ]

    # Process in small batches to avoid overloading
    batch_size = 2
    for i in range(0, len(sources), batch_size):
        batch = sources[i:i + batch_size]
        await asyncio.gather(*(ingest_source(s) for s in batch))

    logger.info("✅ Sync complete.")


if __name__ == "__main__":
    asyncio.run(sync_all_news())
