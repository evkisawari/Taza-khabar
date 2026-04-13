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

from groq import AsyncGroq
import asyncio

# =============================================================
# GROQ AI SUMMARIZER (with auto-retry on rate limit)
# =============================================================
async def _call_groq(prompt: str, max_tokens: int = 150) -> str:
    """Make a Groq API call with up to 3 retries on rate limit (429)."""
    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        logger.error("❌ GROQ_API_KEY not found in environment!")
        return ""
    client = AsyncGroq(api_key=api_key)
    for attempt in range(3):
        try:
            response = await client.chat.completions.create(
                messages=[{"role": "user", "content": prompt}],
                model="llama-3.3-70b-versatile",
                temperature=0.3,
                max_tokens=max_tokens,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            err = str(e)
            if "429" in err or "rate_limit" in err:
                # Extract wait time from error message, default 60s
                import re as _re
                wait_match = _re.search(r'try again in (\d+)m(\d+(\.\d+)?)?s', err)
                wait_sec = int(wait_match.group(1)) * 60 + 10 if wait_match else 65
                wait_sec = min(wait_sec, 60)  # Cap at 1 minute so we don't hold up indefinitely
                logger.warning(f"⏳ Rate limit hit. Waiting {wait_sec}s before retry {attempt+1}/3...")
                await asyncio.sleep(wait_sec)
            else:
                logger.error(f"❌ Groq API error: {err}")
                return ""
    logger.error("❌ Groq gave up after 3 retries.")
    return ""


async def groq_summarize(text: str, language: str = "english") -> str:
    """Use Groq to write a professional 60-word news summary. Never stores raw text."""
    if not text or len(text.strip()) < 150:
        return ""
    
    lang_instruction = "Hindi (Devanagari script only, no English words)" if language == "hindi" else "English"
    prompt = f"""You are a professional news editor for a top news app.
Write a clear, factual summary of this news article in EXACTLY 55-65 words.

Strict rules:
- Language: {lang_instruction}
- Output ONLY the summary paragraph. Nothing else.
- NO intro phrases like "Here is...", "Sure...", "Summary:"
- NO source names, website names, or author names
- NO ellipsis (...) at the end
- Must be a complete sentence

Article:
{text[:1200]}"""

    summary = await _call_groq(prompt, max_tokens=150)
    if not summary:
        return ""
    # Strip any leaked prefix
    import re
    summary = re.sub(r'^(Sure|Here is|Summary|सारांश|यहाँ)[^।.]*[।:.]?\s*', '', summary, flags=re.IGNORECASE).strip()
    logger.info(f"✅ Groq summary ({len(summary)} chars): {summary[:60]}...")
    return summary


async def groq_make_title(text: str, language: str = "english") -> str:
    """Use Groq to write a clean, punchy news headline (max 12 words)."""
    if not text or len(text.strip()) < 100:
        return ""
    lang_instruction = "Hindi (Devanagari script only)" if language == "hindi" else "English"
    prompt = f"""Write a punchy, factual news headline in {lang_instruction} for this article.
Max 12 words. Output ONLY the headline. No quotes, no punctuation at end.

Article:
{text[:600]}"""
    return await _call_groq(prompt, max_tokens=50)


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

                # --- STEP 2: Generate AI title + AI summary from Groq ---
                ai_title = await groq_make_title(content_for_ai, language=lang_param)
                final_title = ai_title if ai_title and len(ai_title) > 5 else title

                summary = await groq_summarize(content_for_ai, language=lang_param)

                # Skip article entirely if Groq couldn't summarize — no raw text stored ever
                if not summary or len(summary) < 30:
                    logger.warning(f"Groq returned empty summary, skipping: {final_title[:50]}")
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
                    title=final_title,
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
                logger.info(f"✅ Saved: [{lang_code}/{source['category']}] {final_title[:60]}")

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

        # --- ENGLISH (Additional Categories) ---
        {'name': 'News18 Sports', 'url': 'https://www.news18.com/rss/sports.xml', 'category': 'Sports', 'language': 'en'},
        {'name': 'The Hindu Business', 'url': 'https://www.thehindu.com/business/feeder/default.rss', 'category': 'Business', 'language': 'en'},
        {'name': 'News18 Ent', 'url': 'https://www.news18.com/rss/movies.xml', 'category': 'Entertainment', 'language': 'en'},

        # --- HINDI (National) ---
        {'name': 'Amar Ujala', 'url': 'https://www.amarujala.com/rss/breaking-news.xml', 'category': 'National', 'language': 'hi'},
        {'name': 'Live Hindustan', 'url': 'https://feed.livehindustan.com/rss/3127', 'category': 'National', 'language': 'hi'},
        {'name': 'Bhaskar National', 'url': 'https://www.bhaskar.com/rss-feed/1061/', 'category': 'National', 'language': 'hi'},
        {'name': 'India TV Hindi', 'url': 'https://www.indiatv.in/cms/rssfeed', 'category': 'National', 'language': 'hi'},

        # --- HINDI (International, Politics, War) ---
        {'name': 'News18 Hindi World', 'url': 'https://hindi.news18.com/khabar-rss/', 'category': 'International', 'language': 'hi'},
        {'name': 'Jansatta Politics', 'url': 'https://www.jansatta.com/feed/', 'category': 'Politics', 'language': 'hi'},
        {'name': 'Bhaskar Politics', 'url': 'https://www.bhaskar.com/rss-v1--category-1065.xml', 'category': 'Politics', 'language': 'hi'},
        {'name': 'Bhaskar World', 'url': 'https://www.bhaskar.com/rss-v1--category-1068.xml', 'category': 'War', 'language': 'hi'},

        # --- HINDI (Additional Categories) ---
        {'name': 'Bhaskar Sports', 'url': 'https://www.bhaskar.com/rss-v1--category-1066.xml', 'category': 'Sports', 'language': 'hi'},
        {'name': 'Amar Ujala Biz', 'url': 'https://www.amarujala.com/rss/business.xml', 'category': 'Business', 'language': 'hi'},
        {'name': 'Amar Ujala Ent', 'url': 'https://www.amarujala.com/rss/entertainment.xml', 'category': 'Entertainment', 'language': 'hi'},
    ]

    # Process in small batches to avoid overloading
    batch_size = 2
    for i in range(0, len(sources), batch_size):
        batch = sources[i:i + batch_size]
        await asyncio.gather(*(ingest_source(s) for s in batch))

    logger.info("✅ Sync complete.")


if __name__ == "__main__":
    asyncio.run(sync_all_news())
