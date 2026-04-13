import asyncio
import httpx
import feedparser
import os
import google.generativeai as genai
from dotenv import load_dotenv
import trafilatura
from bs4 import BeautifulSoup

# No emojis, no unicode, safe for Windows console
load_dotenv()

async def test_full_pipeline():
    print("\n--- [1/5] Checking Gemini API ---")
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("CRITICAL: GEMINI_API_KEY missing!")
        return
    
    try:
        genai.configure(api_key=api_key)
        models = [m.name for m in genai.list_models()]
        print(f"Found {len(models)} models.")
        
        # Select first working model
        selected = models[0] if models else "models/gemini-1.5-flash"
        print(f"Using model: {selected}")
        model = genai.GenerativeModel(selected)
        response = model.generate_content("Ping")
        if response.text:
            print("Gemini Generation Working.")
    except Exception as e:
        print(f"Gemini Error: {str(e)[:100]}")

    print("\n--- [2/5] Checking English RSS (Google News) ---")
    url = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=10.0) as client:
            resp = await client.get(url)
            print(f"RSS Status: {resp.status_code}")
            feed = feedparser.parse(resp.text)
            print(f"Found {len(feed.entries)} entries.")
            if len(feed.entries) > 0:
                print(f"First Item: {feed.entries[0].title[:50]}...")
    except Exception as e:
        print(f"RSS Error: {e}")

    print("\n--- [3/5] Checking Scraping ---")
    if len(feed.entries) > 0:
        target_url = feed.entries[0].link
        print(f"Testing URL: {target_url}")
        try:
            headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/118.0.0.0 Safari/537.36"}
            async with httpx.AsyncClient(headers=headers, follow_redirects=True, timeout=15.0) as client:
                resp = await client.get(target_url)
                print(f"Resolved URL: {resp.url}")
                
                content = trafilatura.extract(resp.text)
                if content:
                    print(f"Trafilatura Scraped: {len(content)} chars.")
                else:
                    print("Trafilatura FAILED. Checking BS4...")
                    soup = BeautifulSoup(resp.text, 'html.parser')
                    ps = soup.find_all('p')
                    text = " ".join([p.text for p in ps if len(p.text) > 40])
                    print(f"BS4 Scraped: {len(text)} chars.")
                    if len(text) < 200:
                        print("BS4 also failed to get enough content.")
        except Exception as e:
            print(f"Scraping Error: {e}")

    print("\n--- [4/5] Checking DB Counts ---")
    import sqlite3
    try:
        conn = sqlite3.connect('news.db')
        cursor = conn.cursor()
        cursor.execute("SELECT language, COUNT(*) FROM articles GROUP BY language")
        print(f"DB Counts: {dict(cursor.fetchall())}")
        conn.close()
    except Exception as e:
        print(f"DB Error: {e}")

if __name__ == "__main__":
    asyncio.run(test_full_pipeline())
