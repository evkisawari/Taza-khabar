import feedparser
import httpx
import asyncio
import re
import html as html_parser

def clean_html(raw_html):
    if not raw_html: return ""
    cleanr = re.compile('<.*?>|&([a-z0-9]+|#[0-9]{1,6}|#x[0-9a-f]{1,6});')
    cleantext = re.sub(cleanr, '', raw_html)
    return html_parser.unescape(cleantext).strip()

async def check_rss():
    url = "https://news.google.com/rss?hl=en-IN&gl=IN&ceid=IN:en"
    async with httpx.AsyncClient(follow_redirects=True) as client:
        resp = await client.get(url)
        feed = feedparser.parse(resp.text)
        print(f"Found {len(feed.entries)} entries")
        for entry in feed.entries[:5]:
            summary = entry.get('summary', '')
            cleaned = clean_html(summary)
            print(f"Title: {entry.get('title')}")
            print(f"Cleaned Summary Len: {len(cleaned)}")
            print(f"Cleaned Summary: {cleaned}")
            print("-" * 20)

if __name__ == "__main__":
    asyncio.run(check_rss())
