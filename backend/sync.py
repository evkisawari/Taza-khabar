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
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure Google Gemini
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY)
    # Using 'gemini-1.5-flash' which is the most stable identifier
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

async def is_high_quality(text, language='hi'):
    """Use Gemini to decide if this news is worth showing (filters out junk and technical noise)."""
    if not model or not text or len(text) < 150:
        return False
        
    try:
        # We want to filter out tech junk, snippets with just JSON, or broken scrapes.
        # "Good News" focus: prioritize informative, uplifting, or relevant stories.
        prompt = f"""
        Act as a "Good News" Chief Editor. Decide if this content is high-quality news for humans.
        Language: {language}
        
        REJECT if:
        - Contains technical JSON code, scripts, or internal metadata (e.g. {{"_id": "...", "slug": "..."}}).
        - It is just "loading...", "cookie policy", or broken text fragments.
        - It is irrelevant garbage or purely promotional spam.
        
        ACCEPT if:
        - It is a readable news story, report, or update.
        - It is informative, interesting, or uplifting.
        
        Content: {text[:1000]}
        
        Answer with ONLY 'ACCEPT' or 'REJECT'.
        """
        response = await model.generate_content_async(prompt)
        result = response.text.strip().upper()
        return "ACCEPT" in result
    except Exception as e:
        logger.error(f"AI Decision Error: {e}")
        return True # Default to True to avoid losing news on API failure

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def clean_html(raw_html):
    if not raw_html:
        return ""
    
    # 1. Parse with BeautifulSoup first to strip tags safely
    soup = BeautifulSoup(raw_html, "html.parser")
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
        "Copyright", "All rights reserved", "Aaj Tak", "News18", "Amar Ujala",
        "Dainik Bhaskar", "BBC", "Reuters", "The Hindu", "Times of India",
        "Read more", "Continue reading", "Learn more", "Author", "Designation",
        "Reading time", "पदनाम", "पढ़ने का समय", "मिनट", "सुहैब"
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
    
    # 3. Final Rejoin and Technical Junk Removal
    text = " ".join(cleaned_sentences)
    
    # Remove technical JSON-LD or Hydration Data (Common in modern news sites)
    text = re.sub(r'\{[^{}]*"_id":[^{}]*\}', '', text)
    text = re.sub(r'\{[^{}]*"slug":[^{}]*\}', '', text)
    text = re.sub(r'\{[^{}]*"type":[^{}]*\}', '', text)
    
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

async def summarize(text, language='en'):
    """Professional summarizer with Gemini support and strict word count fallback."""
    if not text or len(text.strip()) < 50:
        return "Latest updates from our reporting partners. You can tap 'Read More' to view the exhaustive coverage on the official source website."

    # Remove any existing trailing ellipses from raw text
    text = text.strip().rstrip('.')

    # --- ATTEMPT PRO GEMINI SUMMARIZATION ---
    if model:
        try:
            prompt = f"""
            Act as a "Good News" Editor for an app called Taza Khabar.
            Task: Summarize this article in {language} for a mobile news feed (Inshorts style).
            
            STRICT RULES:
            1. Length: Exactly 60-80 words.
            2. Formatting: NO technical junk, NO JSON, NO meta-data.
            3. Tone: Professional, clear, and engaging. Focus on the core story.
            4. Ending: MUST end with a full stop (.).
            5. Content: Explain the Who, What, Where, and Why.
            6. NO SOURCE NAMES: Strictly DO NOT mention "AajTak", "News18", "BBC", "Amar Ujala", "Navbharat Times", "DW.com", "Bhaskar", or any other news brand name.
            7. NO METADATA: Strictly DO NOT include author names, reading times (e.g. "9 min read"), designations, or "Written by" lines.
            8. NO LABELS: Do not include "Read more", "Click here", "Copy link", or "Learn more".
            9. STORY ONLY: Return only the facts of the story in a professional tone. No lists of sources.
            
            Article Content: {text}
            """
            response = await model.generate_content_async(prompt)
            summary = response.text.strip()
            
            # Strict word count verification
            word_count = len(re.findall(r'\w+', summary))
            if 55 <= word_count <= 85 and not summary.endswith('...'):
                return summary
            logger.warning(f"Gemini summary rejected (word count: {word_count}). Falling back.")
        except Exception as e:
            logger.error(f"Gemini Summarization error: {e}")

    # --- FALLBACK: HIGH QUALITY ALGORITHMIC SUMMARIZATION ---
    # Tokenize into sentences
    sentences = re.split(r'(?<=[.।!|])\s+', text)
    cleaned_sentences = [s.strip() for s in sentences if len(s.split()) > 5]
    
    if not cleaned_sentences:
        return text[:300].strip() + "."

    result_summary = ""
    current_word_count = 0
    
    for sentence in cleaned_sentences:
        sentence_words = len(sentence.split())
        if current_word_count + sentence_words <= 85:
            result_summary += " " + sentence
            current_word_count += sentence_words
        else:
            # If we haven't reached min 55 words, try to take a part of this sentence
            if current_word_count < 55:
                needed = 65 - current_word_count
                partial = " ".join(sentence.split()[:needed])
                # Clean up partial sentence
                partial = re.sub(r'[,;:\s]+$', '', partial) + "."
                result_summary += " " + partial
            break
            
    result_summary = result_summary.strip()
    
    # Final cleanup to ensure no ellipses and good word count
    final_words = result_summary.split()
    if len(final_words) > 85:
        result_summary = " ".join(final_words[:80]) + "."
    elif len(final_words) < 55:
        # If still too short, pad with original content up to limit
        pass 

    # Ensure no triple dots
    result_summary = result_summary.replace("...", ".")
    if not result_summary.endswith(('.', '।', '!', '|')):
        result_summary += "."
        
    return result_summary

import trafilatura
import concurrent.futures
import nltk

# Ensure the grammar tools are downloaded for summarizing
try:
    nltk.download('punkt', quiet=True)
except:
    pass

executor = concurrent.futures.ThreadPoolExecutor(max_workers=10)

def scrape_with_trafilatura(url):
    """Sync wrapper for trafilatura with a robust User-Agent to avoid 403s"""
    try:
        # We manually fetch with a human-like UA because trafilatura's default is often blocked
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
            "Referer": "https://www.google.com/"
        }
        with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as client:
            response = client.get(url)
            if response.status_code == 200:
                return trafilatura.extract(response.text, include_comments=False)
        
        # Fallback if manual fetch fails
        downloaded = trafilatura.fetch_url(url)
        if downloaded:
            return trafilatura.extract(downloaded)
        return None
    except Exception as e:
        logger.error(f"Scraping failed for {url}: {e}")
        return None

async def fetch_article_body(url):
    """Offloads the heavy scraping to a thread pool for maximum speed."""
    loop = asyncio.get_event_loop()
    try:
        body = await loop.run_in_executor(executor, scrape_with_trafilatura, url)
        if body and len(body.strip()) > 100:
            # Check for junk keywords
            junk = ["cookie", "consent", "accept all", "reject all", "privacy policy", "more options", "g.co/", "privacytools"]
            if any(j in body.lower()[:300] for j in junk):
                return None
            return body.strip()
        return None
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

                # --- CONSOLIDATED AI DECISION & SUMMARY ---
                # We do this in one call to save API quota (Free Tier)
                prompt = f"""
                You are a Chief Editor. Analyze this content and follow these steps:
                1. QUALITY CHECK: If the content is technical junk (JSON, CSS), meta-data repetitive lists, or promotional spam, reply ONLY with 'REJECT'.
                2. SUMMARIZE: If it is a good news story, summarize it following these rules:
                   - Length: 60-80 words. Strictly.
                   - Style: Professional Inshorts style.
                   - NO Source names (AajTak, BBC, etc.).
                   - NO Metadata (Authors, reading times).
                
                Content: {clean_content}
                """
                
                response = model.generate_content(prompt)
                ai_result = response.text.strip()
                
                if "REJECT" in ai_result.upper() or len(ai_result) < 100:
                    logger.info(f"⏭️ AI Rejected low-quality or junk article: {entry.get('title')}")
                    continue
                
                short_content = ai_result
                # --- FINAL NUCLEAR Post-processing (Regex clean) ---
                # This deletes BRAND NAMES + AUTHOR/META patterns if AI fails
                patterns_to_remove = [
                    r"(?i)AajTak", r"(?i)News18", r"(?i)BBC", r"(?i)Amar Ujala", 
                    r"(?i)Navbharat Times", r"(?i)DW.com", r"(?i)Bhaskar", r"(?i)Dainik",
                    r"(?i)Author(:)?\s?.*", r"(?i)Written by(:)?\s?.*", r"(?i)By\s?.*",
                    r"(?i)Read more(:)?\s?.*", r"(?i)Learn more(:)?\s?.*", r"(?i)Copy link",
                    r"(?i)Designation(:)?\s?.*", r"(?i)पदनाम(:)?\s?.*", r"(?i)असद सुहैब",
                    r"(?i)पढ़ने का समय(:)?\s?\d+\s?मिनट"
                ]
                
                for pattern in patterns_to_remove:
                    short_content = re.sub(pattern, "", short_content).strip()

                # Fix punctuation and whitespace after removals
                short_content = re.sub(r'\s+', ' ', short_content)
                short_content = re.sub(r'\.\s*\.', '.', short_content).strip()

                # Rate limit protection (Free Tier)
                await asyncio.sleep(6)
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
